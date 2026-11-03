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

**5. Outputs.**

```bash
uv run ingest/export_geojson.py        # writes map/data/texas_counties.geojson
uv run ingest/make_report.py           # writes REPORT.md
cd map && python3 -m http.server 8000  # then open http://localhost:8000
```

The map must be served over HTTP. Opening `index.html` directly will not load the data.

**Record your downloads.** Each download's retrieval date and SHA-256 checksum belong in
`DATA_SOURCES.md`. Results can change if the source files change, so keep the checksums
with the outputs you publish.

## Repository layout

- `migrations/`: numbered SQL files, applied in order by `migrate.sh`. Applied files are
  never edited; changes go in a new numbered file.
- `ingest/`: Python loading and export scripts. Python is used for loading only; all
  analysis is in SQL.
- `tests/`: pytest tests (synthetic data only) and validation SQL for the real data.
- `map/`: static MapLibre page and the GeoJSON it reads.
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
