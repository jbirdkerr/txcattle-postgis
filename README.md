# Texas Cattle Slaughter Capacity by County: PostGIS

A small spatial analysis of Texas counties using public, aggregated data. It demonstrates
boundary joins, distance queries, and spatial clustering in PostGIS, and it publishes
county-level results, a short report, and a static map.

**This is descriptive work.** It shows where reported cattle and cattle slaughter
facilities are located by county. It does not establish causes, attribute disease to
any facility, or identify outbreak zones. Read `LIMITATIONS.md` before interpreting any output.

## What it produces

- `REPORT.md`: a short written summary generated from the published views.
- `map/data/texas_counties.geojson` and `map/index.html`: a static county map.
- `map/data/texas_history.json`: slaughter establishments by county, 1986 to 2016, and a
  statewide cattle-per-establishment series, 1986 to 2023. The map shows it as a
  "History" view with a year slider.
- SQL views (`county_summary`, `county_facility_published`, `county_cluster_published`) for analysis.

## Requirements

- Docker (for PostGIS 16 with PostGIS 3.4)
- [uv](https://docs.astral.sh/uv/) for Python dependencies
- `git`
- A free NASS Quick Stats API key: https://quickstats.nass.usda.gov/api

## Quick setup

```bash
git clone <this-repo> txcattle-postgis && cd txcattle-postgis
docker compose up -d                  # PostGIS database on localhost:5432
uv sync                               # Python dependencies
./migrate.sh                          # apply migrations 001 to 012 in order
```

## Reproduce the full analysis from a clean clone

Run these in order. Each step shows what to check before moving on.

**1. Tests (optional, recommended first).** Tests use a separate database and
synthetic data only.

```bash
docker exec -it txcattle-db createdb -U txcattle txcattle_test
TEST_DATABASE_URL=postgresql://txcattle:txcattle@localhost:5432/txcattle_test uv run pytest
```

Expect all tests to pass.

**2. Counties (Census TIGER/Line 2025).**

```bash
uv run ingest/fetch.py counties        # downloads and prints SHA-256
uv run ingest/load_counties.py         # loads 254 Texas counties
docker exec -i txcattle-db psql -U txcattle -d txcattle < tests/test_counties.sql
```

Check: 254 counties, 0 duplicate GEOIDs, 0 invalid geometries, 0 internal points outside
their county, 0 overlapping pairs.

**3. Cattle inventory (USDA NASS).**

```bash
NASS_API_KEY=your_key uv run ingest/fetch.py cattle
uv run ingest/load_cattle.py
docker exec -i txcattle-db psql -U txcattle -d txcattle < tests/test_cattle_view.sql
```

Check: no duplicate keys, 254 counties per series, and the milk cow coverage table.
Milk cow counts are published for few counties, which is a finding in its own right.

**4. Facilities (USDA FSIS).** Download two CSV files from the FSIS directory page
(https://www.fsis.usda.gov/inspection/establishments/meat-poultry-and-egg-product-inspection-directory):

- the MPI Directory (locations, FIPS codes), saved as `data/raw/fsis_mpi_directory.csv`
- the Establishment Demographic supplement (species slaughtered), saved as `data/raw/fsis_mpi_supplement.csv`

```bash
uv run ingest/load_facilities.py
```

Check: Texas establishments loaded, cattle and dairy cow slaughter counts, and
county-assignment mismatches (expected 0). FSIS covers beef and poultry slaughter, not
dairy processing.

**5. History (Census County Business Patterns and NASS).** Downloads about 600 MB of
Census bulk files once; files already present are kept.

```bash
NASS_API_KEY=your_key uv run ingest/fetch.py history
uv run ingest/load_history.py
uv run ingest/export_history.py        # writes map/data/texas_history.json
```

Check: the loader reports that county establishment counts sum to the Texas total in
every year. A mismatch stops the load.

**6. Outputs.**

```bash
uv run ingest/export_geojson.py        # writes map/data/texas_counties.geojson
uv run ingest/make_report.py           # writes REPORT.md
cd map && python3 -m http.server 8000  # then open http://localhost:8000
```

The map must be served over HTTP. Opening `index.html` directly will not load the data.

**Record your downloads.** Each download's retrieval date and SHA-256 checksum belong in
`DATA_SOURCES.md`. Results can change if the source files change, so keep the checksums
with the outputs you publish.

## Automated build and publish (GitHub Actions)

`.github/workflows/publish.yml` runs the tests, runs the full pipeline, and publishes the
page to Cloudflare Pages (project `txcattle`, served at https://txcattle.jbirdkerr.net and
https://txcattle.pages.dev) on every push to `main`. A manual run on another branch publishes a preview deployment instead.

Set these once in the repository:

- **Secrets:** `NASS_API_KEY`, `CLOUDFLARE_API_TOKEN` (an API token with Cloudflare
  Pages: Edit), and `CLOUDFLARE_ACCOUNT_ID`
- **Variables:** `FSIS_DIRECTORY_URL`, `FSIS_DIRECTORY_SHA256`, `FSIS_SUPPLEMENT_URL`,
  `FSIS_SUPPLEMENT_SHA256`. The URLs point at the FSIS files attached to a GitHub release
  in this repository (see below); the checksums match those files. A file whose checksum
  changes stops the run, so an unexpected version is never published silently.

### FSIS files: why a release, and how to refresh them

The FSIS website refuses automated downloads (it returned 403 Forbidden to a scripted
request), so the workflow cannot fetch the files from FSIS directly. Instead, an
unmodified copy of the two CSVs is attached to a release in this repository, and the
workflow downloads that copy. FSIS data is a U.S. government work in the public domain.

To publish newer FSIS data:

1. Download the MPI Directory and the Establishment Demographic supplement from the FSIS
   page in a browser, saved as `data/raw/fsis_mpi_directory.csv` and
   `data/raw/fsis_mpi_supplement.csv`.
2. Run the pipeline locally and review the report.
3. Attach the files to a new release, named for the download date:

   ```bash
   gh release create fsis-YYYY-MM-DD data/raw/fsis_mpi_directory.csv data/raw/fsis_mpi_supplement.csv \
     --title "FSIS files, YYYY-MM-DD" --notes "Unmodified FSIS MPI Directory and supplement, downloaded YYYY-MM-DD."
   ```

4. Point the four variables at the new release and its checksums:

   ```bash
   TAG=fsis-YYYY-MM-DD; BASE=https://github.com/jbirdkerr/txcattle-postgis/releases/download/$TAG
   gh variable set FSIS_DIRECTORY_URL  --body "$BASE/fsis_mpi_directory.csv"
   gh variable set FSIS_SUPPLEMENT_URL --body "$BASE/fsis_mpi_supplement.csv"
   gh variable set FSIS_DIRECTORY_SHA256  --body "$(sha256sum data/raw/fsis_mpi_directory.csv | cut -d' ' -f1)"
   gh variable set FSIS_SUPPLEMENT_SHA256 --body "$(sha256sum data/raw/fsis_mpi_supplement.csv | cut -d' ' -f1)"
   ```

5. Record the retrieval date and checksums in `DATA_SOURCES.md`, then rerun the workflow.

The pipeline runs as named stages (`ingest/run_pipeline.py`). It writes
`build/manifest.json` with each stage's title, status, duration, and output checksums.
The manifest never records commands, arguments, or environment values, so the API key
cannot reach the published page. `ingest/build_page.py` turns the report and manifest into
`site/index.html`, with the report and run summary in expandable sections above the map.

Run the same build locally with `uv run ingest/run_pipeline.py`, after setting the
environment variables above.

## Repository layout

- `migrations/`: numbered SQL files, applied in order by `migrate.sh`. Applied files are
  never edited; changes go in a new numbered file.
- `ingest/`: Python loading, export, and page-building scripts. Python is used for loading
  and presentation only; all analysis is in SQL.
- `.github/workflows/`: the automated build and Cloudflare Pages deploy.
- `tests/`: pytest tests (synthetic data only) and validation SQL for the real data.
- `map/`: static MapLibre page, its favicon, and the data files it reads.
- `assets/make_favicon.py`: draws the cow favicon (`uv run --with pillow python assets/make_favicon.py`).
- `data/`: raw and staging files. Git-ignored.
- `DATA_SOURCES.md`: source, vintage, licence, and checksum for every dataset.
- `LIMITATIONS.md`: what the data can and cannot show, and every judgement call made.

## Publishing checklist

Before sharing outputs, confirm:

- [ ] `git ls-files` shows no files under `data/`, no CSV or ZIP downloads, and no test fixtures.
- [ ] The GeoJSON contains only county polygons and the published fields. It never contains facility points.
- [ ] `REPORT.md` and the map use miles and describe results as descriptive only.
- [ ] `LIMITATIONS.md` lists every pending item (see below) that is still open.

Audit result for this version: all of the above were checked against the repository.
The GeoJSON and report are generated on your machine and should be checked there.

## Open items

- **Dairy processors:** no public Texas list identified. The facility layer covers beef
  and poultry slaughter only. Dairy is out of scope for the current version.

## Checks completed

- **NASS zero check:** the county extract contains no explicit zeros. A missing row is
  treated as "no row", not zero. See `LIMITATIONS.md`.
- **Land area check:** the 254 county land areas sum to the Texas state ALAND (676,660 km²).
- **Map check:** reviewed in a browser.
