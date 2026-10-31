# Texas Cattle, Beef, and Dairy: County-Level Facility Proximity with PostGIS

A small spatial analysis of Texas counties using public, aggregated data. It shows
boundary joins, distance queries, and spatial clustering in PostGIS, and it publishes
county-level results and a static map.

**This is descriptive work.** It does not establish causes, attribute outbreaks, or
identify individual premises. See `LIMITATIONS.md` before interpreting any output.

## Setup

Requires Docker, [uv](https://docs.astral.sh/uv/), and `git`.

```bash
git clone <this-repo> txcattle-postgis && cd txcattle-postgis
docker compose up -d                 # start PostGIS 16 / 3.4
uv sync                              # install Python ingestion dependencies
./migrate.sh                         # apply migrations in order
uv run ingest/fetch.py counties      # download TIGER 2025 counties to data/raw/
uv run ingest/load_counties.py       # load Texas county boundaries
uv run pytest                        # loader tests (synthetic fixture; see below)
NASS_API_KEY=... uv run ingest/fetch.py cattle   # NASS county cattle (free key)
uv run ingest/load_cattle.py         # load county cattle inventory
uv run ingest/load_facilities.py     # load Texas FSIS cattle slaughter establishments (staging)
uv run ingest/make_report.py         # write REPORT.md from the published views
uv run ingest/export_geojson.py      # write map/data/texas_counties.geojson
open map/index.html                  # view the static map
```

Only `fetch.py counties`, `load_counties.py`, and `pytest` exist so far. The other
ingest commands are the target workflow and will be added in later steps.

**Tests.** Loader tests run against a separate `txcattle_test` database so the
development database is never touched. Create it once:

```bash
docker exec -it txcattle-db createdb -U txcattle txcattle_test
TEST_DATABASE_URL=postgresql://txcattle:txcattle@localhost:5432/txcattle_test uv run pytest
```

Tests use a clearly labeled synthetic fixture (`tests/make_fixture.py`), never real
data. After loading the real counties, run `tests/test_counties.sql` for the
validation queries against real Texas data.

## Repository layout

- `migrations/`: numbered SQL files, applied in order.
- `ingest/`: Python ingestion scripts. Python is used for loading only.
- `tests/`: validation SQL (boundary joins, distance plausibility).
- `map/`: static MapLibre GL JS page and the GeoJSON it reads.
- `data/`: raw and staging files, git-ignored.
- `DATA_SOURCES.md`: source, vintage, and license for every dataset.
- `LIMITATIONS.md`: reporting lags, small-count rules, boundary issues, and what the data cannot show.

## Status

Steps 0 to 6 written and tested. Steps 1 to 3 loaded on the real data; steps 4 to 6 run on your machine. Remaining: GeoJSON export and static map (Step 7).
