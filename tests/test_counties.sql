-- Validation queries for the REAL Texas county load (run after load_counties.py).
-- Each query should return the value shown in the comment. Mismatches mean the
-- join or the source file needs investigation before continuing.

-- Expect: 254
SELECT count(*) AS texas_counties FROM tx_county;

-- Expect: 254 (no duplicate GEOIDs)
SELECT count(DISTINCT geoid) AS distinct_geoids FROM tx_county;

-- Expect: 0 (all geometries valid)
SELECT count(*) AS invalid_geoms FROM tx_county WHERE NOT ST_IsValid(geom);

-- Expect: 0 (every internal point lies inside its own county)
SELECT count(*) AS internal_pt_outside
FROM tx_county
WHERE NOT ST_Covers(geom, ST_Transform(internal_pt::geometry, 4269));

-- Expect: 0 (no county overlaps another; a self-join with a strict-overlap test)
SELECT count(*) AS overlapping_pairs
FROM tx_county a
JOIN tx_county b ON a.geoid < b.geoid
WHERE ST_Area(ST_Intersection(a.geom, b.geom)) > 1e-9;

-- Expect: equal to the Texas STATE ALAND in the 2025 TIGER state file, since
-- county ALAND values sum to the state total. Compare against the state file
-- (tl_2025_us_state.zip, STATEFP 48) rather than a figure from memory.
SELECT round(sum(land_area_m2) / 1e6) AS texas_land_km2 FROM tx_county;
