-- 006: county-level facility proximity.
--
-- Distances run from each county's TIGER internal point to the nearest facility,
-- using geography (metres on the spheroid). Radii: 10 km and 25 km.
--
-- county_facility_metrics is the unsuppressed working view (staging use only).
-- county_facility_published applies the small-count rule before anything is exported.

CREATE VIEW county_facility_metrics AS
SELECT
  c.geoid,
  c.name,
  (SELECT ST_Distance(c.internal_pt, f.geom) / 1000.0
     FROM fsis_establishment f
     WHERE f.cattle_slaughter AND f.geom IS NOT NULL
     ORDER BY f.geom <-> c.internal_pt
     LIMIT 1)                                                    AS nearest_cattle_km,
  (SELECT count(*) FROM fsis_establishment f
     WHERE f.cattle_slaughter AND ST_DWithin(c.internal_pt, f.geom, 10000)) AS cattle_within_10km,
  (SELECT count(*) FROM fsis_establishment f
     WHERE f.cattle_slaughter AND ST_DWithin(c.internal_pt, f.geom, 25000)) AS cattle_within_25km,
  (SELECT ST_Distance(c.internal_pt, f.geom) / 1000.0
     FROM fsis_establishment f
     WHERE f.dairy_cow_slaughter AND f.geom IS NOT NULL
     ORDER BY f.geom <-> c.internal_pt
     LIMIT 1)                                                    AS nearest_dairy_cow_km,
  (SELECT count(*) FROM fsis_establishment f
     WHERE f.dairy_cow_slaughter AND ST_DWithin(c.internal_pt, f.geom, 25000)) AS dairy_cow_within_25km
FROM tx_county c;

-- Small-count rule: any published count of 1 to 4 is withheld (NULL), so a
-- county with a single facility is never shown as one. Zero is not suppressed.
CREATE VIEW county_facility_published AS
SELECT
  geoid,
  name,
  nearest_cattle_km,
  CASE WHEN cattle_within_10km BETWEEN 1 AND 4 THEN NULL ELSE cattle_within_10km END AS cattle_within_10km,
  CASE WHEN cattle_within_25km BETWEEN 1 AND 4 THEN NULL ELSE cattle_within_25km END AS cattle_within_25km,
  nearest_dairy_cow_km,
  CASE WHEN dairy_cow_within_25km BETWEEN 1 AND 4 THEN NULL ELSE dairy_cow_within_25km END AS dairy_cow_within_25km
FROM county_facility_metrics;
