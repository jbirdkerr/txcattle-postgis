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

### 2. NASS county livestock estimates (annual) and 2022 Census of Agriculture

- **Used for:** cattle inventory as the denominator for county-level rates.
- **Publisher:** USDA National Agricultural Statistics Service (NASS).
- **Source pages:**
  - 2022 Census of Agriculture, Texas county data: https://www.nass.usda.gov/Publications/AgCensus/2022/Full_Report/Volume_1,_Chapter_2_County_Level/Texas/
  - NASS county estimates, Texas: https://data.nass.usda.gov/Statistics_by_State/Texas/Publications/County_Estimates/
- **Vintage:** 2022 Census of Agriculture (issued February 2024); county estimates 2021 to 2023.
- **License:** U.S. government work, public domain. Cite NASS as the source.
- **Status:** Verified that county tables exist for Texas (2022 Census and annual county estimates). Downloadable structured format (CSV or Quick Stats export) to verify before ingestion. Published PDFs will not be used for loading.

### 3. FSIS Meat, Poultry, and Egg Product Inspection (MPI) Directory

- **Used for:** meat and poultry slaughter and processing establishments, filtered to cattle-relevant establishments. Establishment addresses are geocoded in staging; only county-level aggregates are published.
- **Publisher:** USDA Food Safety and Inspection Service (FSIS).
- **Source page:** https://www.fsis.usda.gov/inspection/establishments/meat-poultry-and-egg-product-inspection-directory
- **Vintage:** CSV version dated January 21, 2025 on the page at time of research; catalog record says updated weekly. Re-download at ingest time and record the download date.
- **License:** U.S. government work, public domain.
- **Caveats:** FSIS lists physical addresses, not coordinates. It covers meat and poultry, not dairy processing. Cattle-relevant filtering depends on species fields in the directory or demographic supplement, to verify.
- **Status:** Verified that a public CSV exists. Species fields and geocoding approach to verify.

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
