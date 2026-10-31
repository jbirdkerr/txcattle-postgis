# Limitations

This project is descriptive. It describes where reported cattle activity and cattle
slaughter facilities are located by county. It does not establish causes, attribute
disease to any facility, or identify outbreak zones.

## Disease reporting
- **Reporting lags.** NASS and FSIS data are annual or updated on their own schedules.
  Recent months may be incomplete.
- **Surveillance bias.** Counties with more testing report more detections. Counts are
  not rates of disease.
- **Few usable disease sources at county level.** The HPAI livestock data is published
  by state only, so it is not used in county analysis. New World screwworm case lists
  are too small to analyse as rates.

## Cattle inventory (NASS)
- **Modelled estimates.** County survey estimates are built from census, administrative
  records, and state-level estimates. They are model outputs, not counts.
- **Dairy coverage is thin.** Milk cow counts are published for only about 27 to 38
  Texas counties in any given year. Many others are suppressed or absent. Dairy results
  rest on this sample and are reported with the coverage shown.
- **Suppression.** NASS withholds values to protect confidentiality, marked `(D)`.
  Combined-county aggregates (code 998) are excluded.
- **Absent is not zero.** A county with no row for a series is recorded as 'no row'. It
  is not treated as zero, because the reason for absence is not confirmed. (Pending the
  NASS zero check.)
- **Program changes.** NASS has discontinued some data programs. Continuity of the
  county series should be confirmed before any future-year analysis.

## Facilities (FSIS)
- **Beef and poultry slaughter only.** FSIS covers meat and poultry. It does not cover
  dairy processing, so the facility layer does not include dairy processors. The
  `dairy_cow_slaughter` flag marks plants that slaughter dairy cows, not dairy processors.
- **Lookback window.** The slaughter fields include a 360-day lookback. They reflect
  recent activity, not current licensing.
- **Locations.** Coordinates are as published. Plants outside Texas bounds are rejected.
  One establishment has no FSIS FIPS code; its county is assigned from its coordinates.
- **Distances from county internal points.** Each county's distance is measured from its
  Census internal point, not its edge. A large county's nearest plant may be closer to
  its boundary than the distance shown.

## Small counts and disclosure
- **Count suppression.** Any published count of 1 to 4 is withheld.
- **Nearest-distance suppression.** A nearest-facility distance is withheld when the
  same type's 25 km count is 1 to 4. With so few plants nearby, a distance could locate
  a specific plant. Where the 25 km count is 0, the nearest distance is shown, because it
  does not identify a plant inside the radius.
- **Small-count instability.** Even unsuppressed values from small counts swing widely
  from year to year. Read single-year results with caution.

## Boundaries
- **Census boundaries.** County boundaries are 2025 TIGER/Line. Counties may have changed
  for other data sources, and the join is by FIPS code.
- **Point-in-polygon assignment.** Facility counties come from coordinates. A plant near
  a county line may be assigned differently from the county its address names. The
  mismatch check reports these cases.

## What the data cannot show
- Whether any facility, county, or cattle population is related to any disease outcome.
- Movement of animals between counties, or the facility they were sent to.
- Premises-level animal health. Premises data is not public.

## Clustering (Step 5)
- **Descriptive only.** Clusters group counties that sit close to cattle slaughter
  capacity. They do not measure disease, and they are not outbreak zones.
- **Input is facility density.** Clustering uses counties with a slaughter plant within
  25 km. The county disease data is too thin to cluster, so disease is not an input.
- **Parameters are judgment calls.** A 50 km neighbourhood and a minimum of two counties
  are stored in `cluster_params`. Changing them changes the clusters, so report them.
- **Labels are arbitrary.** Cluster IDs can change when the input changes. Compare
  clusters by membership, not by ID.
- **Publication threshold.** A cluster is shown only when at least 5 distinct cattle
  plants lie within 25 km of its member counties. Smaller clusters are withheld.
