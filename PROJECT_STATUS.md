# Project status: what's done and what's left

Last updated: 2026-11-21.

This document separates three levels of confidence, because they matter for a portfolio piece:

- **Verified on real data:** run against the actual public sources, with the output checked.
- **Tested on synthetic data:** covered by automated tests using invented data. The code is checked, but the real output hasn't been seen.
- **Not yet verified:** written but not run end to end, or dependent on something outside this environment.

## Done

### Data pipeline (verified on real data)

| Step | What | Level |
|---|---|---|
| 0 | Repository, PostGIS container, migration runner | Verified (PostGIS 3.4.3 confirmed) |
| 1 | 254 Texas counties from Census TIGER/Line 2025 | Verified: validation queries pass; land area sums to state ALAND (676,660 km²) |
| 2 | County cattle inventory from NASS | Verified: 6,204 records loaded; duplicate-key check passed; `(D)` markers match the loader count |
| 3 | 523 Texas FSIS establishments, 70 cattle slaughter, 12 dairy cow slaughter | Verified: all assigned to counties, zero FIPS mismatches |
| 4 | County distances and counts | Verified on Deaf Smith County (plant 23.4 km from centre; inside the county under the boundary measure) |
| 5 | Descriptive clusters | Verified on real data: one cluster of 167 counties and 70 plants. Boundary-to-boundary distances with the 31-mile neighbourhood chain neighbouring counties together. (The earlier two-cluster result used centre points and km.) |
| 6 | Summary ranks and report generator | Verified: report reviewed and judged reasonable by the project owner |
| 7 | History: slaughter establishments 1986-2016 by county, 1986-2023 statewide (Census CBP), with NASS cattle | Verified on real data: county rows sum to the Texas total in all 31 county years; map history view checked in a browser at desktop and phone widths |

### Decisions made and recorded

- Distances measured from the county boundary, in miles (migrations 011 and 012).
- Facility counts of 1 to 4 are flagged, not hidden (migration 010). The FSIS directory is public.
- NASS `(D)` suppression is kept. Missing NASS rows are "no row", never zero. The Texas extract contains no explicit zeros, so the file can't say what a missing row means.
- Dairy processors are out of scope for this version. The facility layer covers beef and poultry slaughter only.
- Farm and premises locations are excluded by project rule.

### Publishing and automation (written, tested on synthetic data)

- `ingest/export_geojson.py`: publishes county fields only. Facility points are never exported.
- `map/index.html`: static MapLibre page. Browser check completed.
- `ingest/run_pipeline.py`: runs the stages in order and writes a manifest with titles, status, timings, and output checksums. The manifest never records commands or environment values.
- `ingest/build_page.py`: builds `site/index.html` with the report and run summary in `<details>` sections above the map.
- `.github/workflows/pages.yml`: tests, pipeline, and GitHub Pages deploy.
- 77 automated tests pass. They use synthetic data only.

## Left to do

### 1. First real end-to-end run (highest priority)

`run_pipeline.py` ran end to end locally on 2026-11-21, on both an empty and an already-loaded database, and the manifest reported `ok`. The run found and fixed two bugs: the page was built as a stage before the manifest existed, and the county loader failed on a rerun because cattle and facility rows reference the counties. The GitHub workflow has not run yet.

- [x] Run `uv run ingest/run_pipeline.py` locally. Every stage reported `ok`. The FSIS files were the 2026-10-31 copies already on disk, checked against the pinned checksums.
- [ ] Review `site/index.html` in a browser. Check that the report and run summary open and close as one group, and that the map loads inside the frame.
- [ ] Run the GitHub workflow once on a branch or `workflow_dispatch`. Expect to fix at least one problem on the first run: action versions, the PostGIS service container, or the `psql` install on the runner.

### 2. Inputs that need setting up

- [x] **FSIS download URLs.** The FSIS site returned 403 to an automated fetch on 2026-11-21, so the workflow downloads an unmodified copy attached to the `fsis-2026-10-31` release instead. Refresh steps are in the README.
- [x] **FSIS checksums.** Pinned as repository variables, matching the October 2026 files in `DATA_SOURCES.md`.
- [x] **NASS key.** Added as a repository secret.
- [x] **GitHub Pages.** Source set to GitHub Actions.

### 3. Content for a non-specialist reader

- [ ] **Rewrite the report framing.** `REPORT.md` is generated from the database and reads like a methods note. It will be the main section of the page, so it needs a plain summary up front: what was measured, the main findings, and what they don't show. The numbers stay the same; the framing changes.
- [ ] **Describe clusters in plain language.** A cluster groups counties that sit near slaughter capacity. The groupings depend on the 31-mile neighbourhood; a different choice gives different groups.
- [ ] **Explain the two rankings.** Cattle inventory and plant proximity are separate. The page should say so in the first paragraph, not only the report.
- [ ] **Move the disclaimer up.** The "descriptive only" statement belongs at the top of the page and in the report summary, not only in `LIMITATIONS.md`.

### 4. Data questions still open

- [ ] **Checksum policy for NASS.** NASS data changes, so pinning a checksum would stop every run. Decide between recording checksums only (current approach) or pinning a data version for reproducibility.
- [ ] **NASS county series continuity.** NASS discontinued some programmes in 2025. Confirm the county survey series is still published for the most recent years.
- [ ] **TIGER checksum.** Record the SHA-256 for `tl_2025_us_county.zip` in `DATA_SOURCES.md`. It's printed by `fetch.py counties` but not yet recorded.
- [ ] **Dairy processors.** Out of scope for now. If this changes, the next step is a public source with street addresses; the FDA Interstate Milk Shippers list isn't enough on its own.

### 5. Optional: durable execution layer (Phase B)

Phase A is a complete portfolio piece without this. Phase B adds a durable workflow to show the machinery.

- [ ] **Choose the use case.** The recommended option is a data release workflow that durably downloads the FSIS and NASS files, with retries and resumption. The project doesn't need it, so it's a demonstration.
- [ ] **Choose the runtime.** DBOS Transact, run in GitHub Actions against Supabase or a local Postgres. DBOS state lives in Postgres, so no separate server is needed.
- [ ] **Verify the DBOS Python API** against the installed version before writing code: workflow and step decorators, the client methods for reading run history, and retry configuration. Checked so far only against third-party mirrors.
- [ ] **Replace the manifest with the DBOS record, or keep both.** Decide once the workflow exists. The manifest is simpler and already works.

### 6. Hosting and scheduling

- [ ] **Add a schedule.** The workflow runs on push only. A scheduled run (for example, monthly) would pick up new NASS and FSIS releases, but it changes published numbers without a code change, so the report should show the build date prominently.
- [ ] **Cloud Run, if ever needed.** Would run as a Job, with raw downloads in a Cloud Storage bucket and the database on Supabase. Not needed while GitHub Actions covers the workflow.

### 7. Documentation and portfolio

- [ ] **Check every reproduction step** in the README on a clean clone, following the text exactly.
- [ ] **Review `LIMITATIONS.md`** as a whole. It was extended in several steps, so the sections may not read as one document.
- [ ] **Write a short portfolio write-up** covering the problem, the method, what was deliberately excluded and why, and what the data can't show. The limitations are the strongest part of the story.

## Suggested order

1. First end-to-end run and the GitHub workflow (section 1). This is the real test.
2. Inputs (section 2), which the workflow depends on.
3. Report framing (section 3). This is what a reader sees first.
4. Remaining data questions (section 4), in parallel with 3.
5. Phase B (section 5), only if still wanted once 1 to 4 are done.
6. Hosting, documentation, and write-up (sections 6 and 7) last.

## Known risks

- **Upstream changes.** FSIS files change weekly and NASS publishes on its own schedule. A rebuild can produce different numbers without any code change. The manifest records checksums so each published version can be traced.
- **Small counts.** Most counties have few facilities, so single-county changes can look large. Readers may over-read the rankings.
- **Milk cow sample.** The dairy analysis rests on a small number of published counties, and that will be true in every future year.
- **Action versions.** The GitHub Actions versions in `pages.yml` weren't checked against current releases. Check them on the first run.
