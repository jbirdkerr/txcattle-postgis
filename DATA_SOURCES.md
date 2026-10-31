# Data Sources

Every dataset used in this project is listed here with its source, vintage, license,
and verification status. Status values:

- **Verified**: source and format checked against the publisher's page.
- **To verify**: source identified; format or download path not yet confirmed.
- **Not used**: considered and excluded, with reason.

## Planned datasets

### 1. Census TIGER/Line county boundaries (2025)

- **Used for:** county polygons, joins, and map geometry.
- **Publisher:** U.S. Census Bureau.
- **Source page:** https://www.census.gov/geographies/mapping-files/time-series/geo/tiger-line-file.html
- **Vintage:** 2025 TIGER/Line; boundaries as of January 1, 2025. Released September 23, 2025.
- **License:** U.S. federal government work, public domain.
- **Expected file:** `tl_2025_us_county.zip` (filter to state FIPS 48). Filename to confirm at download.
- **Status:** Verified for vintage and release date. Filename to verify.

### 2. NASS county cattle inventory (Quick Stats API)

- **Used for:** county cattle inventory as the denominator for rates, split into all cattle, beef cows, and milk cows where NASS publishes the class.
- **Publisher:** USDA National Agricultural Statistics Service (NASS).
- **Source:** Quick Stats API, https://quickstats.nass.usda.gov/api (free key required).
- **Queries** (see `ingest/fetch.py`): `commodity_desc=CATTLE`, `statisticcat_desc=INVENTORY`, `agg_level_desc=COUNTY`, `state_alpha=TX`. Census: `source_desc=CENSUS, year=2022`. Survey: `source_desc=SURVEY, year__GE=2021`.
- **Vintage:** 2022 Census of Agriculture (issued February 2024); annual county estimates 2021 onward. Each download records its retrieval timestamp and the exact query in the JSON envelope.
- **License:** U.S. government work, public domain. Cite NASS as the source.
- **Caveats:**
  - County survey estimates are developed from Census data, administrative records, and state-level estimates, so they are modeled values, not counts.
  - Suppressed cells are published with markers such as `(D)` to protect confidentiality. Loaded as NULL with the marker recorded.
  - NASS announced discontinuation of some data programs in August 2025. Confirm the county cattle series continues for the most recent years before relying on them.
- **Status:** Endpoint and parameter names confirmed against NASS API documentation and published client libraries. Field names (`Value` / `value`) observed in published examples. Class names (`class_desc`) and recent-year coverage are checked on first load and recorded in the loader output.

### 3. FSIS Meat, Poultry, and Egg Product Inspection (MPI) Directory and Establishment Demographic supplement

- **Used for:** Texas meat and poultry establishments, filtered to those that slaughter cattle. The `dairy_cow_slaughter` flag identifies plants that slaughter dairy cows. This is not a dairy processor list (FSIS does not cover dairy processing).
- **Publisher:** USDA Food Safety and Inspection Service (FSIS).
- **Source page:** https://www.fsis.usda.gov/inspection/establishments/meat-poultry-and-egg-product-inspection-directory
- **Files:** `fsis_mpi_directory.csv` (locations, FIPS codes) and `fsis_mpi_supplement.csv` (species slaughtered). Joined on `establishment_id`.
- **Retrieved:** 2026-10-31. SHA-256:
  - directory: `76f56c74e2f2caa1b1a392cca19a82a0d310e210d57d84ab8a91991a2a439a20`
  - supplement: `57cd2fd313b75edaa2314b1635e7df96421066fe6cdb0c161d4f73696e752328`
- **License:** U.S. government work, public domain.
- **Caveats:**
  - The supplement's slaughter fields include a 360-day lookback, so they reflect recent activity rather than the current license status.
  - Coordinates are as published. The loader rejects points outside Texas and checks each point's county against the FSIS FIPS code.
  - Facility points are staging data. Only county-level aggregates are published.
- **Status:** Verified. Column names confirmed from the downloaded headers. Cattle flag values are checked by the loader, which stops on any unrecognized value.

### 4. USDA APHIS HPAI confirmed cases in livestock (state level)

- **Used for:** state-level context note only. Not used in county analysis.
- **Publisher:** USDA APHIS.
- **Source page:** https://www.aphis.usda.gov/livestock-poultry-disease/avian/avian-influenza/hpai-detections/hpai-confirmed-cases-livestock
- **Vintage:** page last modified March 13, 2026; updated each weekday.
- **License:** U.S. government work. See APHIS Map and Data Disclaimer.
- **Status:** Verified that the data is reported by state, not by county. Not used for county-level analysis.

### 5. New World screwworm confirmed U.S. cases (county level, event list)

- **Used for:** a dated, county-level case list in the report. Not a rate, not a clustering input.
- **Publisher:** USDA APHIS. Public reporting also at screwworm.gov.
- **Source page:** https://www.aphis.usda.gov/animals/animal-health/livestock-and-poultry-disease/current-status/us-confirmed-cases-new-world
- **Vintage:** 2026 detections, updated as announced.
- **License:** U.S. government work.
- **Caveats:** Very small counts. Compiled case lists must be transcribed with a source citation and date for each row. Species (cattle, goat, dog) recorded where published.
- **Status:** Source page identified. Structured download not confirmed; if none exists, rows will be transcribed manually with citations.

## Considered and not used

- **TAHC bovine tuberculosis and brucellosis reporting.** County tables not found. TAHC reports in meeting minutes and narrative PDFs. Revisit if structured county tables are published.
- **TAHC chronic wasting disease county tables.** Cervid (deer) disease under TPWD jurisdiction, outside livestock scope.
- **Dairy processing plant locations.** FSIS does not cover dairy processing. No public, geocoded list identified yet; to research (FDA and Texas DSHS milk plant records are candidates).
- **Livestock auction markets.** No public, geocoded list identified yet.
