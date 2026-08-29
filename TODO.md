# Roadmap

Each phase is independently buildable and has a concrete verification step — see `docs/ARCHITECTURE.md` for full design rationale.

**Target scope is all of England** (~300 local authorities, Wales/Scotland/Northern Ireland excluded — see `docs/ARCHITECTURE.md`). Phases 0–10 below build and verify the whole pipeline against London's 32 boroughs as a pilot batch, not the final scope; England-wide expansion follows once the sibling data repo has ported the rest of England's councils and the pilot-scale assumptions flagged in `docs/ARCHITECTURE.md`'s Open risks are revisited.

- [x] **Phase 0 — Project skeleton.** Django scaffold, `accounts.User` wired before any other migration, Postgres via docker-compose, DRF installed, this file committed.
  *Verify:* clean `migrate` from empty DB, `/admin/` loads, `/healthz` returns 200, `check --deploy` against prod settings shows only expected warnings.
- [x] **Phase 1 — Council reference data.** `Council`/`CouncilCoverage` models + `councils/selectors.py`; import a hand-verified 32-row London borough fixture (pilot batch — models are England-wide, not London-specific); expose `GET /api/v1/councils/`.
  *Verify:* count is 32, spot-check 3 GSS codes against ONS's current register, API endpoint matches `Council.objects.all()`.
- [x] **Phase 2 — One-council ETL vertical slice.** `SpendTransaction`/`DataLoadRun` + loader, tested against Haringey.
  *Verify:* loaded row count matches parquet's true count exactly; spot-check 3 rows against Polars directly; re-run loader, confirm identical count and no duplicates.
- [ ] **Phase 3 — One boundary + minimal map.** Fetch Haringey's boundary, bare Leaflet page with UK-locked bounds.
  *Verify:* polygon sits correctly in north London at correct scale; click-inside fires, click-outside doesn't; can't pan/zoom off the UK.
- [ ] **Phase 4 — One council's Spend View + API, end-to-end.** `spend/selectors.py`, server-rendered sortable/filterable table for Haringey, Category filter disabled, `GET /api/v1/councils/haringey/transactions/`.
  *Verify:* filtered counts/totals cross-checked against an equivalent Polars query; sort columns toggle correctly on both HTML and API; `connection.queries` confirms parameterized queries; `EXPLAIN ANALYZE` confirms index usage, not sequential scan.
- [ ] **Phase 5 — CSV export.** Streaming, filtered, rate-limited; one `services/export.py` used by both the HTML view and the API export action.
  *Verify:* unfiltered export row count matches DB/parquet exactly; process memory stays flat across a ~275K-row export; 6th rapid request gets throttled.
- [ ] **Phase 6 — Hover badge, two councils.** Haringey (no issue) and Redbridge (real issue: 1,121 pre-coverage rows / £24.68M) side by side; `GET /api/v1/councils/<slug>/coverage/`.
  *Verify:* badge appears only for Redbridge with matching detail text; Haringey shows none.
- [ ] **Phase 7 — Scale to all 32 London boroughs (pilot completion).** Repeat reference/boundary/load/coverage for the rest. England-wide expansion beyond London is future work — see `docs/ARCHITECTURE.md`'s "Recommended sequencing" and Open risks #7–8 — and isn't phased out here yet, pending the sibling data repo porting the rest of England's councils.
  *Verify:* reconciliation script comparing DB row counts against each parquet file for all 32, exact match; full map renders 32 gap-free, hoverable/clickable polygons.
- [ ] **Phase 8 — Shared sidebar/navigation.** Alphabetical sidebar, "Back to Map", a dormant `view=consultancy` query-param hook (recognized-but-unimplemented).
  *Verify:* ampersands sort correctly ("Barking & Dagenham" under B); sidebar navigation jumps council-to-council without returning to the map.
- [ ] **Phase 9 — Security hardening pass.** Checklist pass over `docs/ARCHITECTURE.md`'s security plan, including DRF-specific items.
  *Verify:* `check --deploy` clean; grep for `|safe`/`mark_safe`/raw SQL returns nothing unexpected; manual XSS smoke test; rate limit still holds; `/api/v1/` in prod returns JSON only.
- [ ] **Phase 10 — Deployment & data-refresh runbook.** Dockerfile/gunicorn, managed Postgres with automated backups, documented manual data-refresh runbook, scheduled reconciliation.
  *Verify:* from-scratch deploy runs migrations, ingests all 32, serves both screens and the API with `DEBUG=False`; scheduled reconciliation job reports clean.

## Explicitly parked (not on this roadmap)

- Comparing spend against adjacent councils.
- By-consultancy spend aggregation (no entity resolution exists upstream yet).
- Magic-link (passwordless) login — the `accounts.User` model is in place for this, but no login flow is built.
