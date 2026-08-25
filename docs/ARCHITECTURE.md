# Local Spend Tracker — Architecture

## Context

`local-spend-tracker-frontend` serves UK council spend-transparency data as a public, map-driven browser: click a council on a map of the UK, see its spend table with filters/sort/CSV export. The sibling repo `local-big-con-nationwide` (read-only from here) scrapes council "spend over £500" disclosures and writes harmonised Parquet files per council, but has no database, API, or web layer — this project is that serving layer.

Decisions locked in:
- **MVP scope: London boroughs only (~32 councils)** — the only councils with documented data-quality caveats in the source repo, and the fastest path to a trustworthy first slice.
- **Map: Leaflet + static GeoJSON**, no PostGIS for MVP. Doesn't block a future PostGIS migration — boundary files and the `gss_code` join key carry over unchanged; only click-hit-testing moves from client to server later.
- **No auth in MVP** — site is fully public/read-only. Screen 0 (future magic-link login) is accounted for by getting the custom `User` model in place now, not by building any login flow.
- **Database: PostgreSQL**, for indexing and future nationwide scale.
- **API-backed frontend, single deploy.** The Django website is a thin wrapper on an internal REST API (Django REST Framework), not a second implementation of the query logic. One repo, one deploy for MVP; a fully separate frontend/backend split was considered and explicitly deferred until a second real client (mobile app, third party) exists, to avoid CORS/token-auth complexity with no current payoff.

There is no transaction ID in the curated schema anywhere, which drives the idempotent full-replace load strategy below. (Earlier drafts of this doc flagged `AMOUNT_GBP_EX_VAT` as a column present on only some councils, driving an optional-column, schema-drift-tolerant loader design. The upstream data repo has since dropped that column entirely — it no longer appears anywhere in the curated schema — so that specific case is moot. The loader should still tolerate sparse/missing optional columns in general, per `directorate`/`category`/`sub_category` below, but there is no `amount_gbp_ex_vat` field to backfill.) The "data quality caveat" table (first-coverage-month, pre-coverage rows, future-dated rows) exists only as hand-written prose in the data repo's README for the 32 London boroughs — it must be hand-transcribed into a fixture in this repo, not parsed, since it's not machine-readable and only covers 32 rows once.

Security is an explicit, non-negotiable requirement — see "Security plan" below.

## Repo topology

Two independent repos, one-way batch hand-off, no runtime coupling in production:

```
local-big-con-nationwide/data/curated/<slug>.parquet   (unchanged, existing repo)
                    │  batch hand-off (dev: read sibling dir directly; prod: --source-dir arg)
                    ▼
local-spend-tracker-frontend/   (this project — owns Postgres, owns serving, owns GeoJSON)
```

## Project layout

```
local-spend-tracker-frontend/
  manage.py
  TODO.md                           # repo-tracked roadmap, checked off as phases land
  pyproject.toml                    # pinned deps + uv lockfile
  .env.example                      # documented, no real secrets
  .gitignore
  docker-compose.yml                # local Postgres
  config/                           # Django project package (deliberately not app-named)
    settings/{base,dev,prod}.py
    urls.py / wsgi.py / asgi.py
  apps/
    accounts/                       # exists from commit #1, no login flows yet
      models.py                     # custom User(AbstractUser)
    councils/
      models.py                     # Council, CouncilCoverage
      selectors.py                  # plain functions: get_councils(), get_coverage(slug) — no HTTP, no template concerns
      views.py                      # Screen 1: map + sidebar, calls selectors.py directly
      management/commands/
        import_council_reference.py
        import_council_coverage.py
      static/councils/geo/          # per-borough simplified GeoJSON + manifest.json
    spend/
      models.py                     # SpendTransaction, DataLoadRun
      selectors.py                  # get_filtered_transactions(council, filters, sort) — single source of truth
      forms.py / views.py           # Screen 2: table, filter, sort, CSV export; calls selectors.py directly
      services/etl.py               # parquet -> Postgres loader
      services/export.py            # streaming CSV
      management/commands/load_council_spend.py
    api/                            # DRF app — the "real" API, thin wrapper around the same selectors
      serializers.py                # CouncilSerializer, CoverageSerializer, TransactionSerializer
      views.py                      # ViewSets calling councils/spend selectors.py — no duplicated query logic
      urls.py                       # /api/v1/councils/, /api/v1/councils/<slug>/coverage/,
                                     # /api/v1/councils/<slug>/transactions/ (filter+sort+pagination),
                                     # /api/v1/councils/<slug>/transactions/export/
      throttling.py                 # DRF throttle classes (mirrors the CSV export rate-limit requirement)
    core/
      templates/core/base.html      # shared chrome, DeepMind-style CSS shell
      static/core/js/{map,filters}.js  # filters.js progressively enhances by calling apps/api endpoints
  scripts/fetch_boundaries.py       # ONS Open Geography -> simplified per-borough GeoJSON
```

## API layer

`apps/api/` is a Django REST Framework app, versioned under `/api/v1/`, exposing councils, coverage, and transactions (list with filter/sort/pagination, plus a CSV export action). It contains **no query logic of its own** — every viewset calls the same `selectors.py` functions the server-rendered views call, so there is exactly one implementation of "what transactions match these filters, in what order" to test and secure, not two.

This gets most of the benefit of a hard frontend/backend split (a real, independently-testable API surface; a codebase future clients — mobile, third-party, a future SPA rewrite — could consume without backend changes) without the cost of running it as two deployed services today: no CORS configuration needed (same origin), no separate token-auth scheme needed yet (MVP has no auth at all), no JS build pipeline. Initial page load stays server-rendered (calls selectors directly, no self-referential HTTP hop) for speed and a no-JS baseline; `filters.js` progressively enhances sort/filter/pagination by calling the public `/api/v1/...` endpoints instead of full page reloads. If a second real client shows up later, it talks to the same API immediately — the migration path to a fully separate frontend deploy is "point a new frontend at the existing API," not a rewrite.

DRF-specific security notes: use `JSONRenderer` only in production (disable the browsable API's HTML form renderer — unnecessary surface for a public data API); apply the same IP-based throttle class to the API's transaction-export action as the template-based export view (ideally they share one `services/export.py` implementation entirely, called from both).

## Data model

**`accounts.User(AbstractUser)`** — empty subclass, wired via `AUTH_USER_MODEL` before any other app's first migration. This is the single highest-leverage item in the plan: swapping the user model after other migrations reference it is genuinely painful in Django, and doing it now costs nothing.

**`councils.Council`** — `name`, `slug` (matches `COUNCIL_NAME` in parquet), `gss_code` (unique, ONS join key for GeoJSON), `is_active`. Reference data only.

**`councils.CouncilCoverage`** — one-to-one with `Council`. `first_coverage_month`, `pre_coverage_row_count`/`amount`, `future_dated_row_count`/`amount`, `has_data_quality_issue` (boolean, computed once at import — precomputed because the hover badge is a hot read path), `detail_text`, denormalized `earliest_transaction_date`/`latest_transaction_date`/`last_loaded_at` (avoids a live MIN/MAX query on every hover). Populated from a hand-transcribed fixture sourced from the data repo's README table — kept separate from `Council` so it stays clearly "derived/curated" data.

**`spend.SpendTransaction`** — `council` (FK), `date`, `beneficiary_name` (verbatim, unresolved — no entity dedup exists upstream), `amount_gbp`, `directorate`/`category`/`sub_category`/`description` (all sparse, blank-default). No `amount_gbp_ex_vat` field — the upstream data repo no longer has that column. Indexes on `(council, date)` and `(council, amount_gbp)`, plus a `pg_trgm` GIN index on `beneficiary_name` for recipient search (added via a static `RunSQL` migration — no user input in the DDL itself). No natural key / `unique_together` — there is no dedup key upstream, so duplicate-prevention lives in the load strategy, not the schema.

Deliberately **no FK to any consultancy table** — `beneficiary_name` stays a plain string so the parked "by-consultancy spend" feature can be added later as a separate `ConsultancyFirm` + `BeneficiaryAlias` lookup table, joined by name at query time, without ever migrating `SpendTransaction`.

**`spend.DataLoadRun`** — audit log per ETL invocation (`council`, `source_file_path`, `started_at`/`finished_at`, `row_count`, `status`, `error_message`). Turns "did the last load work" from a scrollback-grep into a query.

## ETL loader (`spend/services/etl.py`)

- **Read**: Polars `scan_parquet`, inspect `.columns` before selecting; tolerate sparse/optional columns (`directorate`/`category`/`sub_category`/`description`) being absent. Only hard-require `DATE`, `BENEFICIARY_NAME`, `AMOUNT_GBP`.
- **Load strategy: idempotent full-replace per council**, not incremental upsert — the only correct approach given no transaction ID exists upstream. Delete all `SpendTransaction` rows for the council, bulk-insert the new set (`bulk_create(batch_size=5000)`, benchmark against `COPY` via `psycopg` if throughput is inadequate at 275K–415K-row councils), update `CouncilCoverage`'s denormalized date fields. Re-running the loader twice must produce an identical end state with zero duplicates. Because delete+insert commits atomically, Postgres's MVCC guarantees a concurrent reader (someone browsing the Spend View mid-reload) sees either the fully-old or fully-new dataset, never a partial/empty state — this is a designed property, not incidental.
- **Audit log must outlive the transaction it describes.** Write the `DataLoadRun` row as `status="running"` and commit it *before* starting the delete+insert transaction — not inside the same transaction. If the load fails and rolls back, the failure needs to survive to be visible; wrapping the audit row in the same transaction as the payload means a crash erases the only record that a crash happened. Update the same row to `success`/`failed` in its own small transaction afterward.
- **Concurrency guard.** Two loader runs for the same council overlapping (stuck job re-triggered, accidental double-run) would race the delete+insert. Acquire a `pg_advisory_lock` keyed on `council_id` at the start of the load; if already held, exit immediately with a clear error rather than racing.
- **Command**: `python manage.py load_council_spend <slug> [--source-dir PATH] [--dry-run]`.
- **Considered and rejected**: streaming/CDC (e.g. Kafka, change-data-capture off the data repo) — reload is human-triggered and infrequent, so batch reload is the correct fit, not a gap. Also rejected: a JSONB "extra fields" column for the sparse `CATEGORY`/`SUB_CATEGORY`/`DESCRIPTION`/`DIRECTORATE` fields — the data repo's own `harmonise()` step already enforces one fixed nationwide column contract (`TARGET_COLUMNS`), so relational fixed nullable columns are simpler and equally correct.

## GeoJSON boundaries

Source from ONS Open Geography Portal, **Generalised (Clipped)** Local Authority District boundaries (not full resolution) — confirm exact vintage during Phase 1, and do not reuse the data repo's `docs/local-authorities.csv` GSS codes, which are confirmed stale (pre-2023 reorg); pull the current 32 London borough codes from ONS's own register instead. Store one GeoJSON file per borough plus a combined manifest under `apps/councils/static/councils/geo/` — plain static files, no PostGIS. Leaflet renders with a UK-wide `maxBounds` and `minZoom` so the map reads as "map of the UK" while panning/zooming can't leave it; only the 32 London polygons are interactive for MVP, the rest of the UK is plain basemap tiles with no overlay.

## Frontend

Server-rendered Django templates, no SPA framework — interactivity is map-click and table-sort, not app-like. Vanilla CSS with a small set of custom properties (DeepMind-inspired: generous whitespace, restrained 2–3 color palette + one accent, system sans-serif, subtle transitions). Sorting via plain `?sort=amount&dir=desc` links re-rendered server-side (sort field validated against an explicit `{date, beneficiary_name, amount_gbp}` allow-list before `.order_by()` — never a raw string). Filter form works as a plain GET form without JS; JS only adds recipient autocomplete via a debounced `/spend/api/recipients/?q=` endpoint. Category filter renders disabled with "Coming Soon".

**Pagination: keyset (cursor), not offset.** Councils run 275K–415K+ rows; naive `OFFSET n LIMIT m` degrades linearly with page depth. Use DRF's `CursorPagination` (or an equivalent keyset approach for the server-rendered view) keyed on the active sort column + a tiebreaker (e.g. `id`) — constant-time regardless of page depth.

## Security plan

| Concern | Implementation |
|---|---|
| CSRF | Django's default `CsrfViewMiddleware`; MVP is deliberately all-GET (filter/sort/export via query params) so there's minimal POST surface beyond Django admin, which already has CSRF built in. |
| Secure settings | `prod.py`: `DEBUG=False`, `ALLOWED_HOSTS` from env (fail startup if unset), `SECURE_SSL_REDIRECT`, `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`, `SECURE_HSTS_SECONDS`, `X_FRAME_OPTIONS="DENY"`. `manage.py check --deploy` run before every deploy, zero unaddressed warnings. |
| Secrets | `django-environ` reading `.env` (gitignored). `SECRET_KEY` has no dev fallback in `prod.py` — missing env var raises at startup. |
| Untrusted scraped text | `beneficiary_name`/`description`/`directorate`/`category` come from scraped council sources — rely on Django's default auto-escaping, **never** apply `\|safe`/`mark_safe` to any of them. |
| ORM-only queries | All filters via `Q`/`.filter()` kwargs, no `.raw()`/`cursor.execute()`/f-string SQL anywhere in `spend/`, except the one static (no-user-input) trigram-index DDL migration. |
| CSV export abuse | `StreamingHttpResponse` over `queryset.iterator(chunk_size=2000)` — never materialize the queryset. Hard row cap (~250,000). IP-based rate limit on the export endpoint specifically (e.g. `django-ratelimit`, 5/min), since there's no auth to key a limit on otherwise. |
| Dependency hygiene | Pinned `pyproject.toml` + lockfile, periodic `pip-audit`. |
| Future-auth readiness | Custom `User` model exists from commit #1; views stay plain functions/CBVs a future login-gate can wrap without restructuring. |
| API surface | `apps/api/` uses `JSONRenderer` only in prod (browsable-API HTML form UI disabled); every viewset calls the shared `selectors.py` functions, so ORM-only-queries and CSV-export protections apply identically whether a request comes through the HTML view or the API. |

## Recommended sequencing

Build Phases 0–6 (see `TODO.md`) against Haringey (plus Redbridge for the badge check) before touching the other 30 boroughs. This exercises every architectural seam — schema drift, model design, boundary rendering, ORM-safe filtering, streaming export, and the quality flag — on a fully verifiable two-council dataset before Phase 7 fans out.

## Open risks (proceeding with stated defaults; revisit if needed)

1. **GSS code freshness** — London boroughs weren't touched by the April 2023 reorg, but the data repo's CSV is confirmed stale regardless; source the 32 codes fresh from ONS's own register during Phase 1.
2. **Exact ONS boundary dataset vintage** — defaulting to a recent "Generalised, Clipped" LAD product; confirm during Phase 3 and note the one-line OGL attribution requirement.
3. **Data hand-off automation** — the data repo has no scheduling/publishing today; defaulting to a documented manual runbook (Phase 10) rather than building automation, consistent with "lightweight."
4. **Full-replace load strategy** — correct given no transaction ID exists, but means every refresh reloads a whole council rather than an incremental delta; fine at current volumes, worth revisiting only if the data repo ever produces true incremental output.
5. **Recipient autocomplete will look noisy** — `beneficiary_name` is unresolved until the parked consultancy-alias table is built; expected, not a bug.
6. **`pg_trgm` extension** — recipient search needs `CREATE EXTENSION pg_trgm`, which needs admin rights on whatever Postgres host is chosen; confirm the hosting provider allows it before Phase 4.

## Critical files

- `config/settings/base.py` — where `AUTH_USER_MODEL` gets set before anything else exists.
- `apps/accounts/models.py` — custom `User`, must be in the very first migration.
- `apps/spend/services/etl.py` — schema-drift-tolerant loader; correctness of the whole dataset hinges on tolerating sparse optional columns and the idempotent-replace strategy.
- `apps/councils/models.py` — `Council`/`CouncilCoverage`, the join point between reference data, boundaries, and the quality badge.
- `apps/spend/views.py` — where the ORM-only filter/sort contract and streaming CSV export both live.
