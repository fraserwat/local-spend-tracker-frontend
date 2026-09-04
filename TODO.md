# Roadmap

Each phase is independently buildable and has a concrete verification step — see `docs/ARCHITECTURE.md` for full design rationale.

**Target scope is all of England** (~300 local authorities, Wales/Scotland/Northern Ireland excluded — see `docs/ARCHITECTURE.md`). Phases 0–10 below build and verify the whole pipeline against London's 32 boroughs as a pilot batch, not the final scope; England-wide expansion follows once the sibling data repo has ported the rest of England's councils and the pilot-scale assumptions flagged in `docs/ARCHITECTURE.md`'s Open risks are revisited.

- [x] **Phase 0 — Project skeleton.** Django scaffold, `accounts.User` wired before any other migration, Postgres via docker-compose, DRF installed, this file committed.
  *Verify:* clean `migrate` from empty DB, `/admin/` loads, `/healthz` returns 200, `check --deploy` against prod settings shows only expected warnings.
- [x] **Phase 1 — Council reference data.** `Council`/`CouncilCoverage` models + `councils/selectors.py`; import a hand-verified 32-row London borough fixture (pilot batch — models are England-wide, not London-specific); expose `GET /api/v1/councils/`.
  *Verify:* count is 32, spot-check 3 GSS codes against ONS's current register, API endpoint matches `Council.objects.all()`.
- [x] **Phase 2 — One-council ETL vertical slice.** `SpendTransaction`/`DataLoadRun` + loader, tested against Haringey.
  *Verify:* loaded row count matches parquet's true count exactly; spot-check 3 rows against Polars directly; re-run loader, confirm identical count and no duplicates.
- [x] **Phase 3 — One boundary + minimal map.** Fetch Haringey's boundary, bare Leaflet page with UK-locked bounds.
  *Verify:* polygon sits correctly in north London at correct scale; click-inside fires, click-outside doesn't; can't pan/zoom off the UK.
- [x] **Phase 4 — One council's Spend View + API, end-to-end.** `spend/selectors.py`, server-rendered sortable/filterable table for Haringey, Category filter disabled, `GET /api/v1/councils/haringey/transactions/`.
  *Verify:* filtered counts/totals cross-checked against an equivalent Polars query; sort columns toggle correctly on both HTML and API; `connection.queries` confirms parameterized queries; `EXPLAIN ANALYZE` confirms index usage, not sequential scan.
- [x] **Phase 5 — CSV export.** Streaming, filtered, rate-limited; one `services/export.py` used by both the HTML view and the API export action.
  *Verify:* unfiltered export row count matches DB/parquet exactly; process memory stays flat across a ~275K-row export; 6th rapid request gets throttled.
- [x] **Phase 6 — Hover badge, two councils.** Haringey (no issue) and Redbridge (real issue: 1,121 pre-coverage rows / £24.68M) side by side; `GET /api/v1/councils/<slug>/coverage/`. Also loaded Barnet and Newham (each a real neighbour of Haringey and Redbridge respectively) to exercise adjacent-boundary rendering ahead of Phase 7's full 32-borough map.
  *Verify:* badge appears only for Redbridge with matching detail text; Haringey shows none.
- [ ] **Phase 7 — Scale to all 32 London boroughs (pilot completion).** Repeat reference/boundary/load/coverage for the rest. England-wide expansion beyond London is future work — see `docs/ARCHITECTURE.md`'s "Recommended sequencing" and Open risks #7–8 — and isn't phased out here yet, pending the sibling data repo porting the rest of England's councils.
  *Verify:* reconciliation script comparing DB row counts against each parquet file for all 32, exact match; full map renders 32 gap-free, hoverable/clickable polygons.
- [x] **Phase 8 — Shared sidebar/navigation.** Search-first typeahead (GOV.UK `accessible-autocomplete` against a static `council-index.json`) plus a collapsed-by-default, region-grouped `<details>` browse list as a sidebar fragment, not a standalone page; a dormant `view=consultancy` query-param hook (recognized-but-unimplemented).
  *Verify:* typing a partial name filters live and keyboard selection navigates to the right council; region groups stay collapsed until clicked and degrade to plain links with JS disabled; sidebar navigation jumps council-to-council without returning to the map.
- [x] **Phase 9 — Security hardening pass.** Checklist pass over `docs/ARCHITECTURE.md`'s security plan, including DRF-specific items. Also bumped Django 5.1.15 (EOL Dec 2025) → 5.2.17 LTS and DRF 3.15.2 → 3.17.2 (pip-audit found 9 known CVEs across both, none exploitable against this app's actual surface, but the pins were stale); added a 120/min baseline `AnonRateThrottle` across every `/api/v1/` endpoint, not just export.
  *Verify:* `check --deploy` clean; grep for `|safe`/`mark_safe`/raw SQL returns nothing unexpected (one sanctioned parameterized `cursor.execute()` documented in `docs/ARCHITECTURE.md`); manual XSS smoke test (`apps/spend/test_views.py::test_scraped_beneficiary_name_is_escaped_in_html`); rate limit still holds (export's 5/min plus the new baseline, both tested); `/api/v1/` in prod returns JSON only; `pip-audit` clean.
- [ ] **Phase 10 — Deployment & data-refresh runbook.** Dockerfile/gunicorn, managed Postgres with automated backups, documented manual data-refresh runbook, scheduled reconciliation. `GZipMiddleware` + WhiteNoise (hashed, pre-compressed static storage in prod) landed ahead of the rest of this phase, plus self-hosted Leaflet/Inter (no more unpkg/Google Fonts CDN dependency) — done, from a client-performance audit.
  *Verify:* from-scratch deploy runs migrations, ingests all 32, serves both screens and the API with `DEBUG=False`; scheduled reconciliation job reports clean.

## Explicitly parked (not on this roadmap)

- Comparing spend against adjacent councils.
- By-consultancy spend aggregation (no entity resolution exists upstream yet).
- Magic-link (passwordless) login — the `accounts.User` model is in place for this, but no login flow is built.
