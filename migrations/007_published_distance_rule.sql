-- 007: withhold nearest-facility distances that could locate a single plant.
--
-- Rule: a nearest-facility distance is withheld (NULL) when the 25 km count of that
-- same facility type is 1 to 4. Where the 25 km count is 0, the distance is shown,
-- because it does not identify a plant inside the radius. Other small-count rules
-- from migration 006 are unchanged. See LIMITATIONS.md.
--
-- Replaces the view from 006 in place. Same columns, same types, same order.

CREATE OR REPLACE VIEW county_facility_published AS
SELECT
  geoid,
  name,
  CASE WHEN cattle_within_25km BETWEEN 1 AND 4 THEN NULL ELSE nearest_cattle_km END
                                                                 AS nearest_cattle_km,
  CASE WHEN cattle_within_10km BETWEEN 1 AND 4 THEN NULL ELSE cattle_within_10km END
                                                                 AS cattle_within_10km,
  CASE WHEN cattle_within_25km BETWEEN 1 AND 4 THEN NULL ELSE cattle_within_25km END
                                                                 AS cattle_within_25km,
  CASE WHEN dairy_cow_within_25km BETWEEN 1 AND 4 THEN NULL ELSE nearest_dairy_cow_km END
                                                                 AS nearest_dairy_cow_km,
  CASE WHEN dairy_cow_within_25km BETWEEN 1 AND 4 THEN NULL ELSE dairy_cow_within_25km END
                                                                 AS dairy_cow_within_25km
FROM county_facility_metrics;
