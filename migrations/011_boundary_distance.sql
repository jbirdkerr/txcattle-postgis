-- 011: distance from the county BOUNDARY is now the primary measure.
--
-- Why: a county's internal point can sit far from where facilities are in a large
-- county. Boundary distance is 0 for any plant inside the county and otherwise the
-- shortest distance to the county's edge. It uses no new data.
--
-- The internal-point distance is kept as nearest_cattle_km_centre, labelled as a
-- reference only.
--
-- Clusters now use county boundaries (polygon-to-polygon distance) rather than
-- internal points, so the cluster and distance measures agree.
--
-- Columns are only appended, never renamed, so dependent views still work.

CREATE OR REPLACE VIEW county_facility_metrics AS
WITH cg AS (
  SELECT c.geoid, c.name,
         ST_Transform(c.geom, 4326)::geography AS geog,
         c.internal_pt
  FROM tx_county c
)
SELECT
  cg.geoid,
  cg.name,
  (SELECT min(ST_Distance(cg.geog, f.geom)) / 1000.0
     FROM fsis_establishment f
     WHERE f.cattle_slaughter AND f.geom IS NOT NULL)            AS nearest_cattle_km,
  (SELECT count(*) FROM fsis_establishment f
     WHERE f.cattle_slaughter AND ST_DWithin(cg.geog, f.geom, 10000)) AS cattle_within_10km,
  (SELECT count(*) FROM fsis_establishment f
     WHERE f.cattle_slaughter AND ST_DWithin(cg.geog, f.geom, 25000)) AS cattle_within_25km,
  (SELECT min(ST_Distance(cg.geog, f.geom)) / 1000.0
     FROM fsis_establishment f
     WHERE f.dairy_cow_slaughter AND f.geom IS NOT NULL)         AS nearest_dairy_cow_km,
  (SELECT count(*) FROM fsis_establishment f
     WHERE f.dairy_cow_slaughter AND ST_DWithin(cg.geog, f.geom, 25000)) AS dairy_cow_within_25km,
  (SELECT min(ST_Distance(cg.internal_pt, f.geom)) / 1000.0
     FROM fsis_establishment f
     WHERE f.cattle_slaughter AND f.geom IS NOT NULL)            AS nearest_cattle_km_centre
FROM cg;

CREATE OR REPLACE VIEW county_facility_published AS
SELECT
  geoid,
  name,
  nearest_cattle_km,
  cattle_within_10km,
  cattle_within_25km,
  nearest_dairy_cow_km,
  dairy_cow_within_25km,
  (cattle_within_10km    BETWEEN 1 AND 4) AS cattle_10km_small_count,
  (cattle_within_25km    BETWEEN 1 AND 4) AS cattle_25km_small_count,
  (dairy_cow_within_25km BETWEEN 1 AND 4) AS dairy_25km_small_count,
  nearest_cattle_km_centre
FROM county_facility_metrics;

-- Clusters: polygon-to-polygon DBSCAN on county boundaries (EPSG:3083, metres).
CREATE OR REPLACE VIEW county_cluster_assignment AS
WITH inputs AS (
  SELECT c.geoid, c.name, ST_Transform(c.geom, 3083) AS shape
  FROM tx_county c
  JOIN county_facility_metrics m USING (geoid)
  WHERE m.cattle_within_25km > 0
),
labelled AS (
  SELECT geoid, name,
         ST_ClusterDBSCAN(
           shape,
           (SELECT value FROM cluster_params WHERE name = 'eps_m'),
           (SELECT value::int FROM cluster_params WHERE name = 'min_counties')
         ) OVER () AS cluster_id
  FROM inputs
)
SELECT geoid, name, cluster_id FROM labelled;

CREATE OR REPLACE VIEW county_cluster_sizes AS
SELECT
  a.cluster_id,
  count(DISTINCT a.geoid)            AS n_counties,
  count(DISTINCT f.establishment_id) AS n_facilities
FROM county_cluster_assignment a
JOIN tx_county c USING (geoid)
JOIN fsis_establishment f
  ON f.cattle_slaughter
 AND ST_DWithin(ST_Transform(c.geom, 4326)::geography, f.geom, 25000)
WHERE a.cluster_id IS NOT NULL
GROUP BY a.cluster_id;

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
  fp.dairy_25km_small_count,
  fp.nearest_cattle_km_centre
FROM tx_county c
CROSS JOIN latest l
LEFT JOIN county_cattle ci
  ON ci.geoid = c.geoid AND ci.source_program = 'SURVEY' AND ci.year = l.yr
LEFT JOIN county_facility_published fp ON fp.geoid = c.geoid
LEFT JOIN county_cluster_published cl ON cl.geoid = c.geoid;
