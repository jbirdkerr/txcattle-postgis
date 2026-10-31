-- 009: county summary with two ranks, built only from published values.
--
-- cattle_rank           : ranked by all-cattle inventory (latest NASS survey year).
-- facility_proximity_rank: ranked by cattle slaughter plants within 25 km (most
--                         first), then by nearest distance. Ties on plant count
--                         are broken by the nearer plant.
--
-- Ranks are NULL where the underlying value is withheld, so a withheld county
-- is never placed in a ranking. Ranks describe position on each measure only.
-- They are not a risk score and must not be combined into one.

CREATE VIEW county_summary AS
WITH latest AS (
  SELECT max(year) AS yr FROM nass_county_cattle WHERE source_program = 'SURVEY'
)
SELECT
  c.geoid,
  c.name,
  ci.all_cattle_head,
  ci.all_cattle_status,
  ci.beef_cow_head,
  ci.milk_cow_head,
  ci.milk_cow_status,
  fp.nearest_cattle_km,
  fp.cattle_within_25km,
  fp.nearest_dairy_cow_km,
  fp.dairy_cow_within_25km,
  cl.cluster_id,
  CASE WHEN ci.all_cattle_head IS NULL THEN NULL
       ELSE rank() OVER (ORDER BY ci.all_cattle_head DESC NULLS LAST) END
    AS cattle_rank,
  CASE WHEN fp.cattle_within_25km IS NULL THEN NULL
       ELSE rank() OVER (ORDER BY fp.cattle_within_25km DESC NULLS LAST,
                                  fp.nearest_cattle_km ASC NULLS LAST) END
    AS facility_proximity_rank
FROM tx_county c
CROSS JOIN latest l
LEFT JOIN county_cattle ci
  ON ci.geoid = c.geoid AND ci.source_program = 'SURVEY' AND ci.year = l.yr
LEFT JOIN county_facility_published fp ON fp.geoid = c.geoid
LEFT JOIN county_cluster_published cl ON cl.geoid = c.geoid;
