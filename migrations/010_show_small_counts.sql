-- 010: show facility counts and distances, flagged when small (1 to 4).
--
-- Replaces the withholding rule from 007. Reasons for the change:
--   * FSIS establishment names and addresses are public, so a county count of
--     1 to 4 discloses nothing the directory does not already show.
--   * Small counts are unstable, which is a reason to flag them, not hide them.
--
-- NASS suppression (the (D) marker) is unchanged; those values stay NULL.
-- The cluster publication threshold (min_facilities_published) is a separate rule
-- and is not changed here.

CREATE OR REPLACE VIEW county_facility_published AS
SELECT
  geoid,
  name,
  nearest_cattle_km,
  cattle_within_10km,
  cattle_within_25km,
  nearest_dairy_cow_km,
  dairy_cow_within_25km,
  (cattle_within_10km   BETWEEN 1 AND 4) AS cattle_10km_small_count,
  (cattle_within_25km   BETWEEN 1 AND 4) AS cattle_25km_small_count,
  (dairy_cow_within_25km BETWEEN 1 AND 4) AS dairy_25km_small_count
FROM county_facility_metrics;

CREATE OR REPLACE VIEW county_summary AS
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
    AS facility_proximity_rank,
  fp.cattle_25km_small_count,
  fp.dairy_25km_small_count
FROM tx_county c
CROSS JOIN latest l
LEFT JOIN county_cattle ci
  ON ci.geoid = c.geoid AND ci.source_program = 'SURVEY' AND ci.year = l.yr
LEFT JOIN county_facility_published fp ON fp.geoid = c.geoid
LEFT JOIN county_cluster_published cl ON cl.geoid = c.geoid;
