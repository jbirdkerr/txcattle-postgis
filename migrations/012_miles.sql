-- 012: switch distances and radii from kilometres to miles.
--
-- Radii become 10 miles and 25 miles (16.09 km and 40.23 km). Counts will be larger
-- than with the 10 and 25 km rings used before.
-- Cluster neighbourhood: 31 miles, which is about 50 km, so clusters stay close to the
-- previous behaviour.
--
-- Column names change, which PostgreSQL does not allow in place, so the dependent
-- views are dropped and recreated in dependency order.

DROP VIEW IF EXISTS county_summary, county_cluster_summary, county_cluster_published,
                    county_cluster_sizes, county_cluster_assignment,
                    county_facility_published, county_facility_metrics CASCADE;

UPDATE cluster_params SET name = 'eps_mi', value = 31 WHERE name = 'eps_m';

CREATE VIEW county_facility_metrics AS
WITH cg AS (
  SELECT c.geoid, c.name,
         ST_Transform(c.geom, 4326)::geography AS geog,
         c.internal_pt
  FROM tx_county c
)
SELECT
  cg.geoid,
  cg.name,
  (SELECT min(ST_Distance(cg.geog, f.geom)) / 1609.344
     FROM fsis_establishment f
     WHERE f.cattle_slaughter AND f.geom IS NOT NULL)                 AS nearest_cattle_mi,
  (SELECT count(*) FROM fsis_establishment f
     WHERE f.cattle_slaughter AND ST_DWithin(cg.geog, f.geom, 16093.44)) AS cattle_within_10mi,
  (SELECT count(*) FROM fsis_establishment f
     WHERE f.cattle_slaughter AND ST_DWithin(cg.geog, f.geom, 40233.6))  AS cattle_within_25mi,
  (SELECT min(ST_Distance(cg.geog, f.geom)) / 1609.344
     FROM fsis_establishment f
     WHERE f.dairy_cow_slaughter AND f.geom IS NOT NULL)              AS nearest_dairy_cow_mi,
  (SELECT count(*) FROM fsis_establishment f
     WHERE f.dairy_cow_slaughter AND ST_DWithin(cg.geog, f.geom, 40233.6)) AS dairy_cow_within_25mi,
  (SELECT min(ST_Distance(cg.internal_pt, f.geom)) / 1609.344
     FROM fsis_establishment f
     WHERE f.cattle_slaughter AND f.geom IS NOT NULL)                 AS nearest_cattle_mi_centre
FROM cg;

CREATE VIEW county_facility_published AS
SELECT
  geoid,
  name,
  nearest_cattle_mi,
  cattle_within_10mi,
  cattle_within_25mi,
  nearest_dairy_cow_mi,
  dairy_cow_within_25mi,
  (cattle_within_10mi    BETWEEN 1 AND 4) AS cattle_10mi_small_count,
  (cattle_within_25mi    BETWEEN 1 AND 4) AS cattle_25mi_small_count,
  (dairy_cow_within_25mi BETWEEN 1 AND 4) AS dairy_25mi_small_count,
  nearest_cattle_mi_centre
FROM county_facility_metrics;

CREATE VIEW county_cluster_assignment AS
WITH inputs AS (
  SELECT c.geoid, c.name, ST_Transform(c.geom, 3083) AS shape
  FROM tx_county c
  JOIN county_facility_metrics m USING (geoid)
  WHERE m.cattle_within_25mi > 0
),
labelled AS (
  SELECT geoid, name,
         ST_ClusterDBSCAN(
           shape,
           (SELECT value * 1609.344 FROM cluster_params WHERE name = 'eps_mi'),
           (SELECT value::int FROM cluster_params WHERE name = 'min_counties')
         ) OVER () AS cluster_id
  FROM inputs
)
SELECT geoid, name, cluster_id FROM labelled;

CREATE VIEW county_cluster_sizes AS
SELECT
  a.cluster_id,
  count(DISTINCT a.geoid)            AS n_counties,
  count(DISTINCT f.establishment_id) AS n_facilities
FROM county_cluster_assignment a
JOIN tx_county c USING (geoid)
JOIN fsis_establishment f
  ON f.cattle_slaughter
 AND ST_DWithin(ST_Transform(c.geom, 4326)::geography, f.geom, 40233.6)
WHERE a.cluster_id IS NOT NULL
GROUP BY a.cluster_id;

CREATE VIEW county_cluster_published AS
SELECT a.geoid, a.name, a.cluster_id
FROM county_cluster_assignment a
JOIN county_cluster_sizes s USING (cluster_id)
WHERE s.n_facilities >= (SELECT value FROM cluster_params WHERE name = 'min_facilities_published');

CREATE VIEW county_cluster_summary AS
SELECT s.cluster_id, s.n_counties, s.n_facilities
FROM county_cluster_sizes s
WHERE s.n_facilities >= (SELECT value FROM cluster_params WHERE name = 'min_facilities_published');

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
  fp.nearest_cattle_mi,
  fp.cattle_within_25mi,
  fp.nearest_dairy_cow_mi,
  fp.dairy_cow_within_25mi,
  cl.cluster_id,
  CASE WHEN ci.all_cattle_head IS NULL THEN NULL
       ELSE rank() OVER (ORDER BY ci.all_cattle_head DESC NULLS LAST) END
    AS cattle_rank,
  CASE WHEN fp.cattle_within_25mi IS NULL THEN NULL
       ELSE rank() OVER (ORDER BY fp.cattle_within_25mi DESC NULLS LAST,
                                  fp.nearest_cattle_mi ASC NULLS LAST) END
    AS facility_proximity_rank,
  fp.cattle_25mi_small_count,
  fp.dairy_25mi_small_count,
  fp.nearest_cattle_mi_centre
FROM tx_county c
CROSS JOIN latest l
LEFT JOIN county_cattle ci
  ON ci.geoid = c.geoid AND ci.source_program = 'SURVEY' AND ci.year = l.yr
LEFT JOIN county_facility_published fp ON fp.geoid = c.geoid
LEFT JOIN county_cluster_published cl ON cl.geoid = c.geoid;
