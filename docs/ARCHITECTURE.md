# Local Spend Tracker — Architecture

## Context

`local-spend-tracker-frontend` serves English council spend-transparency data as a public, map-driven browser: click a council on a map of the UK, see its spend table with filters/sort/CSV export. The sibling repo `local-big-con-nationwide` (read-only from here) scrapes council "spend over £500" disclosures and writes harmonised Parquet files per council, but has no database, API, or web layer — this project is that serving layer.

Decisions locked in:
- **Target scope: all of England (~300 local authorities — exact count moves with ongoing local-government reorganisation)**. Wales, Scotland, and Northern Ireland are out of scope, matching the sibling data repo's actual coverage today: NI has no equivalent statutory duty, and the Wales/Scotland councils it surveyed were later dropped as too thin to carry. **London's 32 boroughs are the pilot batch, not the final scope** — the only councils with documented data-quality caveats in the source repo, and the fastest path to a trustworthy first slice before scaling out to the rest of England.
- **Map: Leaflet + static GeoJSON**, no PostGIS for MVP. Doesn't block a future PostGIS migration — boundary files and the `gss_code` join key carry over unchanged; only click-hit-testing moves from client to server later.
- **No auth in MVP** — site is fully public/read-only. Screen 0 (future magic-link login) is accounted for by getting the custom `User` model in place now, not by building any login flow.
- **Database: PostgreSQL**, for indexing and England-wide scale.
- **API-backed frontend, single deploy.** The Django website is a thin wrapper on an internal REST API (Django REST Framework), not a second implementation of the query logic. One repo, one deploy for MVP; a fully separate frontend/backend split was considered and explicitly deferred until a second real client (mobile app, third party) exists, to avoid CORS/token-auth complexity with no current payoff.

There is no transaction ID in the curated schema anywhere, which drives the idempotent full-replace load strategy below. The "data quality caveat" table (first-coverage-month, pre-coverage rows, future-dated rows) exists only as hand-written prose in the data repo's README for the London pilot boroughs — it must be hand-transcribed into a fixture in this repo, not parsed, since it's not machine-readable and only covers 32 rows once. This hand-transcription approach is pilot-scale only; see Open risks for what it means once the rest of England's ~300 councils are in play.

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
      static/councils/geo/          # per-council simplified GeoJSON + manifest.json
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
  scripts/fetch_boundaries.py       # ONS Open Geography -> simplified per-council GeoJSON
  scripts/reconcile_spend.py        # per-council row-count/amount check: DB vs source parquet
```

## API layer

`apps/api/` is a Django REST Framework app, versioned under `/api/v1/`, exposing councils, coverage, and transactions (list with filter/sort/pagination, plus a CSV export action). It contains **no query logic of its own** — every viewset calls the same `selectors.py` functions the server-rendered views call, so there is exactly one implementation of "what transactions match these filters, in what order" to test and secure, not two.

This gets most of the benefit of a hard frontend/backend split (a real, independently-testable API surface; a codebase future clients — mobile, third-party, a future SPA rewrite — could consume without backend changes) without the cost of running it as two deployed services today: no CORS configuration needed (same origin), no separate token-auth scheme needed yet (MVP has no auth at all), no JS build pipeline. Initial page load stays server-rendered (calls selectors directly, no self-referential HTTP hop) for speed and a no-JS baseline; `filters.js` progressively enhances sort/filter/pagination by calling the public `/api/v1/...` endpoints instead of full page reloads. If a second real client shows up later, it talks to the same API immediately — the migration path to a fully separate frontend deploy is "point a new frontend at the existing API," not a rewrite.

DRF-specific security notes: use `JSONRenderer` only in production (disable the browsable API's HTML form renderer — unnecessary surface for a public data API); apply the same IP-based throttle class to the API's transaction-export action as the template-based export view (ideally they share one `services/export.py` implementation entirely, called from both).

## Data model

**`accounts.User(AbstractUser)`** — empty subclass, wired via `AUTH_USER_MODEL` before any other app's first migration. This is the single highest-leverage item in the plan: swapping the user model after other migrations reference it is genuinely painful in Django, and doing it now costs nothing.

**`councils.Council`** — `name`, `slug` (matches `COUNCIL_NAME` in parquet), `gss_code` (unique, ONS join key for GeoJSON), `is_active`. Reference data only.

**`councils.CouncilCoverage`** — one-to-one with `Council`. `first_coverage_month`, `pre_coverage_row_count`/`amount`, `future_dated_row_count`/`amount`, `has_data_quality_issue` (boolean, computed once at import — precomputed because the hover badge is a hot read path), `detail_text`, denormalized `earliest_transaction_date`/`latest_transaction_date`/`last_loaded_at` (avoids a live MIN/MAX query on every hover). Populated from a hand-transcribed fixture sourced from the data repo's README table — kept separate from `Council` so it stays clearly "derived/curated" data.

**`spend.SpendTransaction`** — `council` (FK), `date`, `beneficiary_name` (verbatim, unresolved — no entity dedup exists upstream), `amount_gbp`, `directorate`/`category`/`sub_category`/`description` (all sparse, blank-default). Indexes on `(council, date)` and `(council, amount_gbp)`, plus a `pg_trgm` GIN index on `beneficiary_name` for recipient search (added via a static `RunSQL` migration — no user input in the DDL itself). No natural key / `unique_together` — there is no dedup key upstream, so duplicate-prevention lives in the load strategy, not the schema.

Deliberately **no FK to any consultancy table** — `beneficiary_name` stays a plain string so the parked "by-consultancy spend" feature can be added later as a separate `ConsultancyFirm` + `BeneficiaryAlias` lookup table, joined by name at query time, without ever migrating `SpendTransaction`.

**`spend.DataLoadRun`** — audit log per ETL invocation (`council`, `source_file_path`, `started_at`/`finished_at`, `row_count`, `status`, `error_message`). Turns "did the last load work" from a scrollback-grep into a query.

## ETL loader (`spend/services/etl.py`, `spend/services/r2.py`)

- **Fetch (R2 path)**: `spend/services/r2.py` is a read-only Cloudflare R2 client, credentials via `R2_ACCOUNT_ID`/`R2_ACCESS_KEY_ID`/`R2_SECRET_ACCESS_KEY`/`R2_BUCKET` settings (a separate, read-only-scoped token — never the sibling repo's write-scoped publishing credentials). `list_councils()` discovers the published council list via `ListObjectsV2` on the `manifest/` prefix (there is no aggregate manifest index). `fetch_manifest(slug)` downloads and parses `manifest/{slug}.json` only — no parquet download — cheap enough to call once per council on every diff check. `fetch_council(slug, dest_dir)` downloads `manifest/{slug}.json` + `curated/{slug}.parquet`, verifies the parquet's sha256 against the manifest's `curated.sha256` before returning — a mismatch raises `R2Error` and nothing gets loaded. `r2.py` has no Django model dependency, so it stays independently usable by future callers beyond the management commands.
- **Weekly reload (`reload_from_r2`)**: `python manage.py reload_from_r2 [--slug SLUG] [--dry-run]`. For each `Council` already in Django (no new-council onboarding — that's Phase 2's structured hand-off, not this command's job), skips anything not yet published to R2, then diffs the manifest's `curated.sha256` against `DataLoadRun.source_sha256` from the last successful load for that council — `RELOADED` only when it's genuinely different (or never loaded), `UNCHANGED` otherwise. `updated_at` is deliberately *not* the diff key: `nightly.yml` republishes every validated council on every run regardless of whether the data changed, so it bumps unconditionally and would trigger a reload every week for every council. Never aborts the batch on one council's failure — continues to the rest, exits non-zero if any failed.
- **Read**: Polars `scan_parquet`, inspect `.columns` before selecting; tolerate sparse/optional columns (`directorate`/`category`/`sub_category`/`description`) being absent. Only hard-require `DATE`, `BENEFICIARY_NAME`, `AMOUNT_GBP`.
- **Load strategy: idempotent full-replace per council**, not incremental upsert — the only correct approach given no transaction ID exists upstream. Delete all `SpendTransaction` rows for the council, bulk-insert the new set (`bulk_create(batch_size=5000)`), update `CouncilCoverage`'s denormalized date fields. Re-running the loader twice must produce an identical end state with zero duplicates. Because delete+insert commits atomically, Postgres's MVCC guarantees a concurrent reader (someone browsing the Spend View mid-reload) sees either the fully-old or fully-new dataset, never a partial/empty state — this is a designed property, not incidental.
  - **Benchmarked against Croydon's real ~1.05M-row parquet** (`scripts/benchmark_bulk_load.py`): `bulk_create(batch_size=5000)` ran at ~20,600 rows/sec; a `COPY`-into-unlogged-staging-table + `INSERT...SELECT` approach ran at ~30,200 rows/sec (1.47x). Decision: **keep `bulk_create`** for now — a 1.5x speedup doesn't justify the added write-path complexity at pilot scale (32 councils); revisit if per-council load time becomes a real operational pain point at full England scale (~150–200M rows, where the aggregate time saved across reload cycles is larger).
- **Audit log must outlive the transaction it describes.** Write the `DataLoadRun` row as `status="running"` and commit it *before* starting the delete+insert transaction — not inside the same transaction. If the load fails and rolls back, the failure needs to survive to be visible; wrapping the audit row in the same transaction as the payload means a crash erases the only record that a crash happened. Update the same row to `success`/`failed` in its own small transaction afterward. Note: an R2 fetch-layer failure (missing manifest, sha256 mismatch) is caught *before* `load_council_spend` is ever called, so no `DataLoadRun` row exists for it — see Open risks.
- **Concurrency guard.** Two loader runs for the same council overlapping (stuck job re-triggered, accidental double-run) would race the delete+insert. Acquire a `pg_advisory_lock` keyed on `council_id` at the start of the load; if already held, exit immediately with a clear error rather than racing.
- **Command**: `python manage.py load_council_spend <slug> [--source-dir PATH | --from-r2] [--dry-run]` — `--source-dir` and `--from-r2` are mutually exclusive.
- **Considered and rejected**: streaming/CDC (e.g. Kafka, change-data-capture off the data repo) — reload is human-triggered and infrequent, so batch reload is the correct fit, not a gap. Also rejected: a JSONB "extra fields" column for the sparse `CATEGORY`/`SUB_CATEGORY`/`DESCRIPTION`/`DIRECTORATE` fields — the data repo's own `harmonise()` step already enforces one fixed nationwide column contract (`TARGET_COLUMNS`), so relational fixed nullable columns are simpler and equally correct.

## GeoJSON boundaries

Source from ONS Open Geography Portal, **Generalised (Clipped)** Local Authority District boundaries (not full resolution) — confirmed during Phase 3 as `LAD_MAY_2025_UK_BGC_V2`, queryable directly as EPSG:4326 GeoJSON by GSS code, no shapefile/reprojection step needed. Do not reuse the data repo's `docs/local-authorities.csv` GSS codes, which are confirmed stale (pre-2023 reorg); pull codes fresh from ONS's own register instead — this holds for every council added, not just the London pilot. Store one GeoJSON file per council plus a combined manifest under `apps/councils/static/councils/geo/` — plain static files, no PostGIS. Leaflet renders with a UK-wide `maxBounds` and `minZoom` so the map reads as "map of the UK" while panning/zooming can't leave it; only councils with data loaded are interactive (the 32 London boroughs for the pilot, growing toward all of England), the rest of the UK is plain basemap tiles with no overlay.

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
| ORM-only queries | All filters via `Q`/`.filter()` kwargs, no `.raw()`/f-string SQL anywhere in `spend/`, except two static, no-user-input exceptions: the trigram-index DDL migration, and `etl.py`'s `pg_try_advisory_xact_lock` call (a single parameterized integer, never user input). |
| CSV export abuse | `StreamingHttpResponse` over `queryset.iterator(chunk_size=2000)` — never materialize the queryset. Hard row cap (500,000 — confirmed above every pilot council's real count, e.g. Haringey's 275,116; a true abuse backstop, not a normal-operation limit). IP-based rate limit on the export endpoint specifically, 5/min via a shared DRF throttle class, since there's no auth to key a limit on otherwise. |
| API abuse baseline | Every other `/api/v1/` endpoint (councils list, coverage, transactions) gets a generous 120/min `AnonRateThrottle` default, on top of export's own tighter 5/min scope — the public API has no auth to key a limit on, so nothing should be fully unthrottled. |
| Dependency hygiene | Pinned `pyproject.toml` + lockfile, periodic `pip-audit`. |
| Future-auth readiness | Custom `User` model exists from commit #1; views stay plain functions/CBVs a future login-gate can wrap without restructuring. |
| API surface | `apps/api/` uses `JSONRenderer` only in prod (browsable-API HTML form UI disabled); every viewset calls the shared `selectors.py` functions, so ORM-only-queries and CSV-export protections apply identically whether a request comes through the HTML view or the API. |

## Recommended sequencing

Build Phases 0–6 (see `TODO.md`) against Haringey (plus Redbridge for the badge check) before touching the other 30 boroughs. This exercises every architectural seam — schema drift, model design, boundary rendering, ORM-safe filtering, streaming export, and the quality flag — on a fully verifiable two-council dataset before Phase 7 fans out.

London (Phases 0–7) is the pilot batch, not the finish line: it validates every architectural seam above on a real, verifiable ~32-council dataset before the same pipeline is pointed at the rest of England's ~300 councils. That England-wide expansion isn't phased out in `TODO.md` yet — it depends on the sibling data repo actually porting England's remaining councils first (its own roadmap has this as pending "v2.0 Nationwide Expansion" work), and on revisiting the pilot-scale assumptions flagged in Open risks below.

## Open risks (proceeding with stated defaults; revisit if needed)

1. **GSS code freshness** — London boroughs weren't touched by the April 2023 reorg, but the data repo's CSV is confirmed stale regardless; source codes fresh from ONS's own register for every council, London or otherwise.
2. **Exact ONS boundary dataset vintage** — confirmed during Phase 3 as `LAD_MAY_2025_UK_BGC_V2` ("Generalised, Clipped"); note the one-line OGL attribution requirement, and that ONS reissues this periodically (the vintage is pinned by name in `scripts/fetch_boundaries.py`, so bumping it later is a one-line change).
3. **Data hand-off automation** — the data repo has no scheduling/publishing today; defaulting to a documented manual runbook (Phase 10) rather than building automation, consistent with "lightweight." At ~300 councils this may need revisiting even for London-pilot-era manual cadence.
4. **Full-replace load strategy** — correct given no transaction ID exists, but means every refresh reloads a whole council rather than an incremental delta; fine at pilot volumes, worth revisiting only if the data repo ever produces true incremental output.
5. **Recipient autocomplete will look noisy** — `beneficiary_name` is unresolved until the parked consultancy-alias table is built; expected, not a bug.
6. ~~**`pg_trgm` extension**~~ — **Resolved.** Neon (chosen as the Postgres host, Step 5) applied the `CREATE EXTENSION pg_trgm` migration cleanly with no admin-rights issue.
7. **Hand-transcribed data-quality caveat table doesn't scale past the pilot.** The `CouncilCoverage` fixture is manually transcribed from hand-written README prose per council (see Data model) — workable for 32 London boroughs, not for ~300 English councils. Revisit before England-wide expansion: either get the sibling data repo to emit this as structured output per council, or accept a slower, batched manual-transcription cadence as councils are added.
8. ~~**`DataLoadRun` doesn't cover R2-fetch-layer failures.**~~ — **Resolved.** `reload_from_r2` (the weekly manifest-diff job) now writes a `DataLoadRun(status=FAILED, ...)` row directly whenever `fetch_manifest()`/`fetch_council()` raises `R2Error`, before `load_council_spend()` would ever be reached — a fetch-layer failure lands in the same audit trail as a load failure, not just job logs.
9. ~~**`list_councils()` exists now, unused until Phase 2's weekly reload job.**~~ — **Resolved.** `reload_from_r2` calls it to discover which councils are actually published in R2, skipping any `Council` row not yet there.
10. **Boundary/GeoJSON file count at England scale.** The current one-file-per-council approach (~2.8KB minified per council after Phase 3) scales to low-single-digit MB in total across ~300 councils — fine for the per-council boundary fetch itself, but a future "whole of England" map view loading all files at once should reconsider bundling (combined file, or TopoJSON to dedupe shared borough/district borders) rather than ~300 individual HTTP requests. Not needed for the London pilot; worth deciding before Phase 7 (32 files) grows toward the full set.
11. **Session-scoped advisory locks don't survive Neon's pooled connection.** `apps/spend/test_etl.py::test_concurrent_load_rejected` simulates a stuck load by holding `pg_advisory_lock` (session-scoped) outside a transaction; Neon's transaction-mode pooler resets session state between transactions, releasing that lock immediately, so the test fails when run against Neon's pooled connection string. The real concurrency guard in `etl.py` uses `pg_try_advisory_xact_lock` (transaction-scoped), which is correctly held for exactly the duration of one pooled transaction and is unaffected. CI runs against local docker-compose Postgres (no pooler), so this doesn't touch the actual gate — it only surfaces when running the suite locally with `DATABASE_URL` pointed at Neon, which is now the local dev default (see `TODO.md`'s parked "separate a Neon dev branch" item).
12. ~~**`pg_trgm` GIN index untuned for bursty delete+bulk-insert writes.**~~ — **Resolved.** The same write pattern (bursty delete-then-bulk-insert per council) caused a real GitLab outage via GIN pending-list overflow. Migration `0003_beneficiary_name_trgm_fastupdate_off` sets `fastupdate = off` on `spend_spendtransaction_beneficiary_name_trgm`, forcing every insert straight into the main index structure and removing the pending list (and its overflow failure mode) entirely — at the cost of marginally slower per-row insert during bulk loads, acceptable given `bulk_create` was already kept over `COPY`-staging for only a 1.47x difference (see above).

## Deployment

Django runs on Fly.io (`fly.toml`, region `lhr` — closest to Neon's `eu-west-2` and to UK traffic) behind Fly's edge TLS terminator, `gunicorn` serving `config.wsgi:application`. `[deploy] release_command` runs `migrate --noinput` before new machines take traffic. `/healthz` checks real Postgres connectivity (`connection.ensure_connection()`, 503 on failure) — Fly's `http_service.checks` hits it directly over the internal network, bypassing the edge, so `SECURE_REDIRECT_EXEMPT` exempts it from `SECURE_SSL_REDIRECT` (else the internal, unforwarded check would see a 301 instead of the 200 it wants). `SECURE_PROXY_SSL_HEADER` trusts Fly's `X-Forwarded-Proto` for real (edge-forwarded) traffic — without it, `SECURE_SSL_REDIRECT` can't recognize an already-HTTPS request and redirect-loops forever. Static files are WhiteNoise-served from within the Django process (`collectstatic` runs at Docker build time), not Fly's own `[[statics]]` file-serving, to keep the content-hashed/gzip-precompressed manifest storage already configured in `prod.py`.

The weekly reload job (`.github/workflows/weekly-reload.yml`, Monday 04:00 UTC) runs `python manage.py reload_from_r2` via `flyctl ssh console` against the live app, authenticated with a scoped `FLY_API_TOKEN` — no in-container cron daemon, matching the sibling repo's own GitHub-Actions-cron convention for `nightly.yml`/`backfill.yml`.

## Critical files

- `config/settings/base.py` — where `AUTH_USER_MODEL` gets set before anything else exists.
- `apps/accounts/models.py` — custom `User`, must be in the very first migration.
- `apps/spend/services/etl.py` — schema-drift-tolerant loader; correctness of the whole dataset hinges on tolerating sparse optional columns and the idempotent-replace strategy.
- `apps/spend/services/r2.py` — read-only R2 client; sha256 verification here is what stands between a corrupted/partial R2 object and bad data reaching Postgres.
- `apps/councils/models.py` — `Council`/`CouncilCoverage`, the join point between reference data, boundaries, and the quality badge.
- `apps/spend/views.py` — where the ORM-only filter/sort contract and streaming CSV export both live.
