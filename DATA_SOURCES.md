# Data Sources

Every dataset used in the analysis, with its source, vintage, licence, retrieval
details, and verification status. Status values:

- **Loaded and validated:** downloaded, loaded into PostGIS, and checked against the
  validation queries in `tests/`.
- **Considered, not used:** reviewed and excluded, with the reason.

All datasets are U.S. federal government works, which are public domain in the United
States. Cite each publisher as the source.

## 1. Census TIGER/Line county boundaries (2025)

- **Used for:** county polygons, point-in-polygon assignment, and distances from county
  boundaries.
- **Publisher:** U.S. Census Bureau.
- **Source page:** https://www.census.gov/geographies/mapping-files/time-series/geo/tiger-line-file.html
- **Vintage:** 2025 TIGER/Line, boundaries as of 1 January 2025, released 23 September 2025.
- **File:** `tl_2025_us_county.zip` (filtered to state FIPS 48, giving 254 counties).
- **Retrieval:** `ingest/fetch.py counties` prints the SHA-256 and size. Record them from your run.
- **Status:** Loaded and validated. 254 counties, unique GEOIDs, valid geometries, internal
  points inside their counties, no overlaps.

## 2. USDA NASS county cattle inventory

- **Used for:** county cattle inventory as the denominator for rankings and context. Milk
  cow counts are reported where NASS publishes them.
- **Publisher:** USDA National Agricultural Statistics Service (NASS).
- **Source:** Quick Stats API, https://quickstats.nass.usda.gov/api (free key required).
- **Query** (`ingest/fetch.py`): `commodity_desc=CATTLE`, `statisticcat_desc=INVENTORY`,
  `agg_level_desc=COUNTY`, `state_alpha=TX`, `domain_desc=TOTAL`,
  `domaincat_desc=NOT SPECIFIED`. Two windows: `source_desc=CENSUS, year=2022` and
  `source_desc=SURVEY, year__GE=2021`.
- **Vintage:** 2022 Census of Agriculture (issued February 2024). Annual county estimates
  for 2021 to 2026 in the survey series.
- **Retrieval:** 2026-10-31. Results: 2,526 census records and 3,678 survey records (6,204
  after removing 12 records for combined counties, code 998). SHA-256:
  `64d0b4cbf3f4dc7e0f75b29a0bdb63bc8daee6678fab21cdc88073dcad84612c` (7,505,736 bytes).
- **Caveats:**
  - County survey estimates are modelled from census, administrative, and state data.
    They are estimates, not counts.
  - NASS suppresses some values to protect confidentiality, marked `(D)`. These are loaded
    as no value.
  - A county with no row for a series is recorded as "no row" and is not treated as zero.
    The Texas extract contains no explicit zeros and no `(Z)` markers, only `(D)`, so the file
    cannot show what a missing row means.
  - Milk cow counts are published for few Texas counties in any year (27 to 38 in the
    survey series).
  - NASS discontinued some data programs in 2025. Continuity of the county series should
    be confirmed before any future-year analysis.
- **Status:** Loaded and validated. Duplicate-key check passed; 254 counties per series;
  the milk cow status check passed. The 1,184 `(D)` markers match the loader's suppressed count.

## 3. USDA FSIS Meat, Poultry, and Egg Product Inspection Directory

- **Used for:** the locations of Texas meat and poultry establishments that slaughter
  cattle, including the dairy cow slaughter flag.
- **Publisher:** USDA Food Safety and Inspection Service (FSIS).
- **Source page:** https://www.fsis.usda.gov/inspection/establishments/meat-poultry-and-egg-product-inspection-directory
- **Files:**
  - `fsis_mpi_directory.csv`: locations, FIPS codes, coordinates
  - `fsis_mpi_supplement.csv`: Establishment Demographic data, including species slaughtered
  - Joined on `establishment_id`.
- **Retrieval:** 2026-10-31. SHA-256:
  - directory: `76f56c74e2f2caa1b1a392cca19a82a0d310e210d57d84ab8a91991a2a439a20`
  - supplement: `57cd2fd313b75edaa2314b1635e7df96421066fe6cdb0c161d4f73696e752328`
- **Results on this retrieval:** 523 Texas establishments; 70 slaughter cattle; 12 slaughter
  dairy cows; all 523 assigned to a county; no FIPS mismatches.
- **Caveats:**
  - FSIS covers meat and poultry slaughter and processing. It does not cover dairy
    processing, so dairy processors are not in this analysis. The `dairy_cow_slaughter`
    flag marks plants that slaughter dairy cows, not dairy processors.
  - The supplement's slaughter fields include a 360-day lookback. They reflect recent
    activity, not current licensing.
  - Plant counts treat all plants equally. FSIS publishes no throughput data, so a large
    plant counts the same as a small one.
  - One establishment has no FSIS FIPS code. Its county is assigned from its coordinates.
  - Individual plant records are staging data. Only county-level aggregates are published.
- **Status:** Loaded and validated.

## 4. Census County Business Patterns (history of slaughter establishments)

- **Used for:** the number of slaughter establishments by Texas county, 1986 to 2016,
  and for Texas as a whole, 1986 to 2023. Shown as the map's history view and in the
  report's history section.
- **Publisher:** U.S. Census Bureau.
- **Source:** bulk files at
  `https://www2.census.gov/programs-surveys/cbp/datasets/{year}/cbp{yy}co.zip` (county) and
  `.../cbp{yy}st.zip` (state). No API key needed. The Census Data API holds the same data
  but now requires a key for data requests.
- **Industry:** SIC 2011 (Meat Packing Plants) to 1997; NAICS 311611 (Animal, except
  Poultry, Slaughtering) from 1998. The 1998 change added 50 Texas establishments in one
  year, so the two periods are not comparable.
- **Retrieval:** 2026-11-21. 31 county files and 38 state files, 585 MB. `fetch.py history`
  prints the SHA-256 of every file, and the run manifest does not include them (they are
  inputs, not outputs).
- **Checks on this retrieval:** in every county year (1986 to 2016) the county rows sum
  exactly to the Texas total and no establishments are statewide-unallocated, so a county
  with no row has zero employer establishments. The loader repeats this check on every run.
- **Caveats:**
  - Counts every employer establishment in the industry: cattle, hogs, sheep, and game,
    federally inspected or not. Businesses with no employees are excluded. This is a
    different measure from the FSIS plant counts.
  - From 2017, Census applies a new disclosure method that drops most small county cells.
    Texas rows fall from 72 counties (2016) to 6 (2017), so county years stop at 2016.
  - The earliest bulk file is 1986.
- **Status:** Loaded and validated.

## 5. USDA NASS all-cattle history

- **Used for:** cattle inventory in the history view and the statewide cattle-per-
  establishment series.
- **Query:** `CATTLE, INCL CALVES - INVENTORY`, SURVEY, reference period FIRST OF JAN,
  domain TOTAL; county level from 1975 and state level from 1986. Saved as
  `data/raw/nass_tx_all_cattle_history.json`.
- **Retrieval:** 2026-11-21. 11,998 county records (11,938 after dropping combined-county
  code 998) and 41 state years. SHA-256
  `7d2d35ba5eb58aaade8964329daa8b70ed92a9c5599d7370bfd0b64177999dd7`.
- **Coverage:** county estimates for 1975 to 1987 and 1993 to 2026. NASS published no
  Texas county estimates for 1988 to 1992. No county value in this series is suppressed.
- **Status:** Loaded and validated.

## Considered, not used

- **USDA APHIS HPAI confirmed cases in livestock.** Published by state only, not by county,
  so it cannot be used in a county analysis.
- **New World screwworm confirmed cases.** Case counts in Texas are too small for county
  analysis. Not loaded.
- **TAHC bovine tuberculosis and brucellosis reporting.** No county-level tables found;
  reporting is in meeting minutes and narrative PDFs.
- **TAHC chronic wasting disease tables.** Deer disease under TPWD jurisdiction, outside
  livestock scope.
- **Dairy processing plant locations.** FSIS does not cover dairy processing. The FDA
  Interstate Milk Shippers list is city-level and mixes processors with receiving stations.
  No public, address-level Texas list identified.
- **Livestock auction markets.** No public, geocoded list identified.
- **Farm and premises locations.** Excluded by project rule (premises-identifiable data).
