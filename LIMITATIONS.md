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
  is not treated as zero. The Texas county extract (6,204 records) contains no explicit
  zeros and no `(Z)` markers, only `(D)` suppression markers. The file therefore cannot
  show whether a missing row means zero or an unreported value, so 'no row' is kept.
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
- **Distances are from the county boundary.** A plant inside a county is at distance 0.
  Otherwise the distance is the shortest distance to the county's edge. This is the
  least distorted measure available from public data: a large county is not penalised
  for its size.
- **Boundary distance is optimistic for cattle far from the edge.** Cattle can sit well
  inside a large county, so the true distance to them can exceed the boundary distance.
  Cattle location within a county is not published, so no measure can show it.
- **Reference distance from the county centre.** The Census internal point is kept as
  `nearest_cattle_km_centre` for comparison only. It can overstate distance in large
  counties, for example Deaf Smith, where Hereford is inside the county but about 14 miles
  from the centre.
- **Plant counts treat all plants equally.** A plant slaughtering around 2,600 head a
  day counts the same as a much smaller one. FSIS publishes no throughput data.

## Small counts and disclosure
- **Counts of 1 to 4 are flagged, not hidden.** The FSIS directory is public and lists
  every establishment's name and address, so a county count adds no disclosure. Small
  counts are unstable, so they are shown with a small-count flag.
- **Clusters keep a separate threshold.** A cluster is shown only with at least five
  distinct plants. A cluster is a grouping, and a two-plant grouping is too weak to
  describe as a pattern.
- **NASS suppression is kept.** Values NASS withholds with `(D)` are not published by
  this project. Those counties show "no value".
- **Small-count instability.** Flagged counts can change a lot from year to year. Read
  single-year results with caution.

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
  25 miles of their boundary. The county disease data is too thin to cluster, so disease
  is not an input.
- **Clusters are boundary to boundary.** Counties join a cluster when their edges are
  within the neighbourhood distance (31 miles, about 50 km, by default), not when their centres are.
- **Parameters are judgment calls.** A 31-mile neighbourhood and a minimum of two counties
  are stored in `cluster_params`. Changing them changes the clusters, so report them.
- **Labels are arbitrary.** Cluster IDs can change when the input changes. Compare
  clusters by membership, not by ID.
- **Publication threshold.** A cluster is shown only when at least 5 distinct cattle
  plants lie within 25 miles of its member counties. Smaller clusters are withheld.

## Rankings (Step 6)
- **Two separate ranks, not one score.** Cattle rank measures inventory. Facility
  proximity rank measures nearby slaughter plants. Neither is a risk measure, and they
  should not be combined.
- **Counties without a published inventory have no cattle rank.** A county with no
  published NASS value is never placed in the cattle ranking, so a missing rank does not
  mean a low value. Facility ranks cover every county.
- **Ties.** Counties with equal plant counts are ordered by nearest distance. Equal
  values still share a rank, so rank order can skip numbers.

## Map and GeoJSON (Step 7)
- **Simplified boundaries.** County outlines are simplified to about 50 m and rounded to
  five decimal places to keep the file small. Boundaries near county lines may differ
  slightly from the Census file.
- **No value is not zero.** The map shows counties with no published value in grey,
  labelled "No value (NASS suppressed or no row)". Legend and tooltips never show 0 for
  these.
- **Quantile colour classes.** Colour breaks are computed from the data, so the classes
  change when the data changes. Compare maps only when their legends match.
- **No basemap.** The map shows counties only, with no roads, cities, or landmarks, so
  locations are harder to judge precisely. This is intentional: it reduces the chance of
  reading facility locations from street-level detail.

## Units
- **Miles throughout.** Distances and radii are in miles. The 10 and 25 mile rings are
  larger than the 10 and 25 km rings used before (16 and 40 km), so counts are higher than
  in earlier runs. Earlier drafts of the report, if any, should be regenerated.
