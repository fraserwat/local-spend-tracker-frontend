# UI Design Pass — Screens 1 & 2 (happy path)

Sketched ahead of Phase 3/4 so frontend-driven decisions land in `ARCHITECTURE.md`/`selectors.py`
before they're built, not after. Covers the two MVP screens at happy-path fidelity only (Haringey,
no data-quality badge triggered) — see `ARCHITECTURE.md` for the locked architecture this builds on.

Companion visual wireframe: rendered as an Artifact (see chat), same component inventory below.

## Screen 1 — Map + sidebar (`/`)

| Element | Data source | Notes |
|---|---|---|
| Leaflet map, UK-locked bounds | Static GeoJSON + `manifest.json` under `apps/councils/static/councils/geo/` | `maxBounds`/`minZoom` per `ARCHITECTURE.md` |
| Interactive council polygons | `GET /api/v1/councils/` joined to manifest by `gss_code` | Only `is_active=true` councils are click/hover-able; rest of England renders as basemap only, no overlay |
| Hover tooltip (council name) | Client-side from GeoJSON `properties`, no API call | |
| Click → navigate to Screen 2 | — | `/<slug>/` |
| Alphabetical sidebar | `GET /api/v1/councils/` | Ampersand sort rule (TODO Phase 8): "Barking & Dagenham" sorts under B, not "&" |

**Backend implication found:** the client needs to tell "loaded and interactive" apart from "known
but not yet loaded" purely from `Council.is_active` — confirm the manifest's per-file entries carry
`gss_code` as the join key (implied by `ARCHITECTURE.md`, not stated explicitly) so the map doesn't
need a second round-trip to resolve slug↔gss_code↔geometry.

## Screen 2 — Council spend view (`/<slug>/`)

| Element | Data source | Notes |
|---|---|---|
| Header: council name, "Back to Map" | `GET /api/v1/councils/` | |
| Coverage badge (icon + tooltip) | `GET /api/v1/councils/<slug>/coverage/` | Absent for Haringey (happy path); renders only when `has_data_quality_issue=true` |
| Filter bar: date range | New — see open question below | GET form, no JS required |
| Filter bar: recipient search | `GET /spend/api/recipients/?council=<slug>&q=` (debounced) | **Must be scoped per-council** — see open question |
| Filter bar: category (disabled) | — | Renders disabled, "Coming Soon" per `ARCHITECTURE.md`; no param sent |
| Results summary line | See open question — no confirmed source | "X transactions, total £Y" |
| Table: Date / Beneficiary / Amount | `GET /api/v1/councils/<slug>/transactions/` | Sortable — allow-list is `{date, beneficiary_name, amount_gbp}` only |
| Table: Directorate / Category / Sub-category / Description | Same endpoint | Sparse, blank-default → render as "—"; **not** in the sort allow-list |
| Sort toggle (column headers) | Query params on same endpoint | Default sort: **not specified in `ARCHITECTURE.md`** — recommend `date` desc (most recent first) |
| Pagination: Next / Previous only | `CursorPagination` | No page-number jump, no "of N pages" — inherent to keyset pagination |
| CSV export button | `GET /api/v1/councils/<slug>/transactions/export/` | Same filters/sort applied; plain browser download, not XHR — no progress UI needed |

## Open questions this pass surfaced (need a decision before Phase 4)

1. **Filtered count/total isn't in the current design.** `CursorPagination` doesn't compute a total
   row count cheaply, but the spend-table UX wants "X transactions, total £Y" above the table. Pick
   one before Phase 4:
   - Add a small aggregate query (`count`/`sum` on the same filtered queryset, indexed columns) run
     once per filter change, returned as pagination metadata or a lightweight separate endpoint.
   - Drop the summary line from MVP and revisit later.
2. **Date-range filter param names aren't defined.** Recommend `date_from`/`date_to`, validated the
   same way the sort field is (explicit allow-list before hitting `.filter()`), not left implicit.
3. **Recipient autocomplete needs a council scope.** `ARCHITECTURE.md` describes
   `/spend/api/recipients/?q=` without a council param — unscoped, it returns beneficiary names
   across all loaded councils, which is both noisy and irrelevant to "who did *this* council pay."
   Needs `?council=<slug>&q=`.
4. **CSV export rate-limit (429) needs a user-facing message.** The export endpoint throttles at
   5/min with no auth to key on; the UI needs to surface that as a plain-language error, not a raw
   HTTP 429.
5. **Default sort order isn't locked.** Recommend `date` descending as the default so the table
   opens on the most recent spend, matching how a hover-badge/coverage narrative ("data through
   month X") would read.

None of these require new models — they're query-shape and endpoint-contract decisions inside
`spend/selectors.py` and `apps/api/` that are cheaper to fix now than after Phase 4 ships.
