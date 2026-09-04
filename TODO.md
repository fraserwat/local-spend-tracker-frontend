# Roadmap

Each phase is independently buildable and has a concrete verification step — see `docs/ARCHITECTURE.md` for full design rationale.

**Target scope is all of England** (~300 local authorities, Wales/Scotland/Northern Ireland excluded — see `docs/ARCHITECTURE.md`). Phase 1 builds and verifies the whole pipeline against London's 32 boroughs as a pilot batch. Phases 2–4 are where that pilot becomes the real thing: nationwide scale, entity resolution, and an insourcing feasibility model.

---

## Phase 1 — User Interface

Everything built so far: the pilot-scale map + spend-table serving layer.

- [x] **Step 1 — Project skeleton.** Django scaffold, `accounts.User` wired before any other migration, Postgres via docker-compose, DRF installed.
  *Verify:* clean `migrate` from empty DB, `/admin/` loads, `/healthz` returns 200, `check --deploy` clean.
- [x] **Step 2 — Council reference data.** `Council`/`CouncilCoverage` models + `councils/selectors.py`; 32-row London borough fixture; `GET /api/v1/councils/`.
  *Verify:* count is 32, GSS codes spot-checked against ONS, API matches `Council.objects.all()`.
- [x] **Step 3 — One-council ETL vertical slice.** `SpendTransaction`/`DataLoadRun` + loader, tested against Haringey.
  *Verify:* row count matches parquet exactly; re-run is idempotent, no duplicates.
- [x] **Step 4 — One boundary + minimal map.** Haringey boundary, bare Leaflet page, UK-locked bounds.
  *Verify:* polygon placement/scale correct; click-inside fires, click-outside doesn't; can't pan/zoom off the UK.
- [x] **Step 5 — One council's Spend View + API.** `spend/selectors.py`, sortable/filterable table, `GET /api/v1/councils/haringey/transactions/`.
  *Verify:* filtered counts cross-checked against Polars; parameterized queries only; `EXPLAIN ANALYZE` shows index use, not seq scan.
- [x] **Step 6 — CSV export.** Streaming, filtered, rate-limited; one `services/export.py` for both HTML and API.
  *Verify:* row count matches exactly; flat memory across a ~275K-row export; 6th rapid request throttled.
- [x] **Step 7 — Hover badge, two councils.** Haringey (clean) vs Redbridge (real data-quality issue); `GET /api/v1/councils/<slug>/coverage/`. Barnet/Newham also loaded to exercise adjacent-boundary rendering.
  *Verify:* badge appears only for Redbridge, with matching detail text.
- [x] **Step 8 — Shared sidebar/navigation.** Search typeahead (`accessible-autocomplete` against static `council-index.json`) plus region-grouped `<details>` browse; dormant `view=consultancy` hook.
  *Verify:* live filter + keyboard nav work; region groups degrade to plain links with JS disabled.
- [x] **Step 9 — Security hardening pass.** Full pass over `docs/ARCHITECTURE.md`'s security plan; Django → 5.2.17 LTS, DRF → 3.17.2 (stale pins, 9 known CVEs, none exploitable here); 120/min baseline throttle on every `/api/v1/` endpoint.
  *Verify:* `check --deploy` clean; no unexpected `|safe`/raw SQL; XSS test passes; throttles hold; `pip-audit` clean.
- [ ] **Step 10 — Scale to all 32 London boroughs (pilot completion).** Superseded by Step 11's `reload_from_r2`: this is no longer a manual "wait for the sibling repo, then re-run the loader by hand" process — the frontend now pulls directly from R2 on its own, no local checkout of `local-big-con-nationwide` involved anywhere in the path. Re-checked live against R2 on 2026-09-04 (querying `manifest/{slug}.json` for all 32 boroughs directly, not from this stale list below): only **2 boroughs have no curated parquet in R2 at all** — Barking & Dagenham, Enfield.
  - Fixed two latent bugs hit while loading the first multi-word-slug boroughs (Tower Hamlets, Richmond upon Thames, etc.): `load_council_spend` built its parquet filename straight from Django's hyphenated slug (sibling repo uses underscores), and `etl.py`'s `COUNCIL_NAME` validation had the same mismatch. Both now normalize hyphens to underscores before comparing/building paths.
  *Verify:* reconciliation script matches DB against parquet for every loaded council exactly; full map renders 32 gap-free polygons (interactive for every council with real R2 data, outline-only for the 2 still missing).
- [x] **Step 11 — Deployment & data-refresh runbook.** Dockerfile (`uv`-based, `psycopg[binary]` needs no compiler toolchain) + `gunicorn`, deployed live to Fly.io (`local-spend-tracker-frontend.fly.dev`, region `lhr`) against the already-provisioned Neon Postgres. `/healthz` checks real DB connectivity; `SECURE_PROXY_SSL_HEADER`/`SECURE_REDIRECT_EXEMPT` handle Fly's edge-terminated TLS correctly (health checks bypass the edge entirely, real traffic doesn't). `python manage.py reload_from_r2` is the scheduled refresh: diffs each loaded council's R2 manifest sha256 against its last successful load, reloads only what changed, runs weekly via `.github/workflows/weekly-reload.yml` against the live app over `flyctl ssh console`. Runbook lives in `docs/ARCHITECTURE.md`'s Deployment section.
  - `GZipMiddleware` + WhiteNoise (hashed, pre-compressed static storage in prod) landed ahead of the rest of this phase, plus self-hosted Leaflet/Inter (no more unpkg/Google Fonts CDN dependency) — done, from a client-performance audit. Its vendored `leaflet.css` referenced marker/layer icon images that were never actually vendored alongside `leaflet.js`/`leaflet.css` — invisible under `DEBUG=True` (no manifest-storage validation), only surfaced once `collectstatic` ran for real against prod settings; fixed by adding the matching Leaflet 1.9.4 `images/` assets.
  - Three more bugs only a real deploy against live traffic surfaced, none reproducible from `docker run` alone: Fly's health checker doesn't send a `Host` header matching the public domain by default (`ALLOWED_HOSTS` 400'd every check forever — fixed with an explicit `checks.headers` override); `gunicorn`'s sync worker silently truncated the CSV export past `--timeout` since it only checks in with the arbiter between requests, not mid-response (measured live: Croydon's real 500K-row export cap takes ~340s against Neon — `--timeout 600 --workers 3` now covers it); and scale-to-zero cut the same export short at 198K rows in 40s since Fly's "excess capacity" autostop doesn't count an open stream as active traffic (`min_machines_running=1` now, restoring the architecture doc's own original "small always-on machine" cost assumption).
  *Verify:* live on `local-spend-tracker-frontend.fly.dev` — `/healthz`, council API, Spend View, and static assets all serve correctly with `DEBUG=False`; full 500,000-row Croydon CSV export completes cleanly end to end (5:43, no truncation); `reload_from_r2` verified against the live app over `flyctl ssh console`.
- [ ] **Step 12 — Design refresh.** Current UI is functional, but looks "off". Before Phase 2 puts ~300 councils' worth of load on it:
  - **Colour Palette Overhaul** - I'm not a designer by trade but I could surely do something passable with a bit of research? 
  - **WCAG 2.2 AA audit** — contrast, keyboard nav, screen-reader labels are already partially handled (`prefers-reduced-motion`, `aria-live`) but not formally checked end-to-end.
  - **Consistent empty/error/loading states** across all screens, not handled ad hoc per view.
  *Verify:* Lighthouse/axe pass on all three screens; manual mobile walkthrough; one round of real user feedback before Phase 2 lands.

---

## Phase 2 — Scaling and Infrastructure

Turning the 32-borough pilot into all of England. The sibling `local-big-con-nationwide` repo has moved faster than assumed — 305 council configs exist there already, 44 with curated parquet output — so re-check its actual state before scoping this in detail.

- [ ] **Step 1 — Backend & API scaling.** Bulk council onboarding (reference data + ETL + coverage) instead of one-at-a-time. The hand-transcribed `CouncilCoverage` fixture (ARCHITECTURE Open risk #7) doesn't survive past the pilot — needs a structured hand-off from the sibling repo, not README prose. Benchmark `bulk_create` vs `COPY` at real per-council row counts (275K–415K).
  *Verify:* a batch run onboards N councils in one pass; coverage fixture is generated, not hand-typed; load throughput benchmarked and documented.
- [ ] **Step 2 — Populate the English council map.** GSS codes, boundaries, and reference data for every English local authority. The GeoJSON idle-outline bundling shipped this session (PR #36) is what makes this renderable at scale — was previously one request per council, now one request total regardless of council count.
  *Verify:* map renders every loaded council gap-free; idle-outline bundle stays at 1 request no matter how many councils are loaded.

---

## Phase 3 — Entity Resolution Layer

**The resolver itself — the matcher, the curated alias/group data — is out of scope for this repo.** It ships as its own versioned library + data artefact, most naturally living in or alongside the sibling data repo, with mandatory sourcing on every claim and no ML in v0 (every match has to be explainable in one sentence to a non-technical reviewer). This repo's job is to **consume and serve** that artefact, the same relationship it already has to the sibling repo's curated parquet.

- [ ] **Step 1 — Consume the entity-resolution artefact.** New models: `CorporateGroup`, `GroupMembership` (dated interval — `valid_from`/`valid_to`/`sources[]`, never a scalar), `BeneficiaryAlias` (raw string → Companies House number, confidence tier), `ResellerOf`. Import command loads the artefact's `aliases.csv`/`groups.yaml`/`group_membership.csv`.
  *Verify:* import is idempotent and records the resolver's semantic version per run; rows below a defined low-confidence tier are structurally unreachable from any published query — enforced in code, not convention.
- [ ] **Step 2 — Point-in-time resolution.** `SpendTransaction.beneficiary_name` + transaction date → corporate group. No query path may default to "today". Both **attribution-at-time** (who got paid, honest measure of the procurement decision) and **attribution-to-current-owner** (who owns that revenue stream now) are computable and separately labelled — they diverge meaningfully for anyone acquired mid-series.
  *Verify:* the same transaction resolves to a different group under each view where a real acquisition occurred in between.
- [ ] **Step 3 — Cross-council beneficiary view.** The concrete ask: a beneficiary's transactions in one council's table today, a resolved corporate group's total spend across *every loaded council* once this ships. New screen/endpoint aggregating by group. Resolved-share-of-spend banner at the top (never resolved-share-of-strings), unresolved and retained-duplicate amounts stated alongside, not hidden.
  *Verify:* aggregate total matches the sum of per-council resolved totals exactly.
- [ ] **Step 4 — Cross-borough price dispersion.** Same corporate group, same service class, different councils, different unit price. Blocked on `category`/`sub_category` data quality — currently sparse/blank-default in `SpendTransaction` — a usable service-class signal is a precondition, not a nice-to-have.
  *Verify:* one defensible dispersion figure, with confidence intervals, cross-checked by hand against a direct query.
- [ ] **Step 5 — Data-quality guardrails, end-to-end.** Natural-person payments (foster carers, direct-payment recipients, small landlords) never resolve to or display as a company anywhere in the UI or API. Retained-duplicate counts surface alongside every aggregate; never silently deduplicated.
  *Verify:* an individual-recipient row never appears as a resolved company anywhere in the product.

---

## Phase 4 — Insourcing Feasibility Model

Estimates whether, and when, bringing an outsourced council service back in-house would cost less than continuing to pay a contractor — a break-even year and an exit-readiness ratio, not a blanket "insource everything" recommendation. Depends entirely on Phase 3. Squarely outside "frontend serving layer" as currently scoped; likely a separate analytics module rather than another Django view — flag and re-scope properly before starting, don't back into it.

- [ ] **Step 1 — Spend-to-contract join.** Ingest Find a Tender / Contracts Finder data, join via the resolved entity from Phase 3. Derives renewal horizons, direct-award flags, framework call-off visibility, exit-clause presence (text search for egress/portability/escrow terms in notice bodies). Endpoints and statutory thresholds need independent verification — several changed at the Procurement Act 2023.
  *Verify:* join rate checked against a hand-verified sample.
- [ ] **Step 2 — Insourcing feasibility model.** Inputs: current spend by function (this repo's data), FTE equivalents, salary cost (NJC scales + London weighting), recruitment lead time, transition/dual-running cost, contract exit penalties (Step 1) — and **capability ramp time**, the hardest variable to model and the one most plans skip. Output: break-even year, sensitivity analysis, `exit_readiness = months_to_expiry / months_to_rebuild_capability`, with an explicit "do not attempt exit" when the ratio is below 1.
  *Verify:* model reproduces Barnet's 2022 insourcing attempt directionally — ratio below 1, exit not viable on the timeline actually attempted.

---

## Explicitly parked (not on this roadmap)

- Magic-link (passwordless) login — `accounts.User` is in place for this, but no login flow is built.
- Separate a Neon dev branch from `production`. As of Step 5, local dev's `.env` points `DATABASE_URL` straight at Neon's `production` branch pooled connection — there is no isolated dev/test database yet. Known consequence: `apps/spend/test_etl.py::test_concurrent_load_rejected` fails when run against the pooled connection (Neon's pooler resets session state between transactions, so the test's session-scoped `pg_advisory_lock` simulation doesn't hold — the real production guard, `pg_try_advisory_xact_lock`, is transaction-scoped and unaffected). CI is unaffected (runs against local docker-compose Postgres, no pooler). Do this alongside the passwordless login work at the end of Phase 1/start of Phase 2.

