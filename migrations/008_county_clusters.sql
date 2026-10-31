-- 008: descriptive clusters of counties with nearby cattle slaughter capacity.
--
-- Input: counties with at least one cattle slaughter plant within 25 km (from
-- county_facility_metrics). Points are county internal points, projected to
-- NAD83 / Texas Centric Albers (EPSG:3083) so eps is in metres.
--
-- This is a DESCRIPTIVE grouping of facility density. It is not a disease cluster,
-- an outbreak zone, or evidence of any causal link. Cluster labels are arbitrary
-- and can change if the input changes.
--
-- Publication rule: a cluster is shown only if at least min_facilities_published
-- distinct cattle plants lie within 25 km of its member counties. Smaller clusters
-- are withheld: their members appear with no cluster label.

CREATE TABLE cluster_params (
  name  text PRIMARY KEY,
  value double precision NOT NULL
);

INSERT INTO cluster_params (name, value) VALUES
  ('eps_m',                      50000),   -- counties within 50 km can join a cluster
  ('min_counties',                   2),   -- a cluster needs at least 2 counties
  ('min_facilities_published',       5);   -- publication threshold, distinct plants

-- Working view (unsuppressed): every input county with its DBSCAN label.
-- Noise counties (not in any cluster) have cluster_id NULL.
CREATE VIEW county_cluster_assignment AS
WITH inputs AS (
  SELECT c.geoid, c.name, ST_Transform(c.internal_pt::geometry, 3083) AS pt
  FROM tx_county c
  JOIN county_facility_metrics m USING (geoid)
  WHERE m.cattle_within_25km > 0
),
labelled AS (
  SELECT geoid, name,
         ST_ClusterDBSCAN(
           pt,
           (SELECT value FROM cluster_params WHERE name = 'eps_m'),
           (SELECT value::int FROM cluster_params WHERE name = 'min_counties')
         ) OVER () AS cluster_id
  FROM inputs
)
SELECT geoid, name, cluster_id FROM labelled;

-- Distinct cattle plants within 25 km of any member county, per cluster.
CREATE VIEW county_cluster_sizes AS
SELECT
  a.cluster_id,
  count(DISTINCT a.geoid)                AS n_counties,
  count(DISTINCT f.establishment_id)     AS n_facilities
FROM county_cluster_assignment a
JOIN tx_county c USING (geoid)
JOIN fsis_establishment f
  ON f.cattle_slaughter
 AND ST_DWithin(c.internal_pt, f.geom, 25000)
WHERE a.cluster_id IS NOT NULL
GROUP BY a.cluster_id;

-- Published view: only clusters that meet the threshold. Other members are unlabelled.
CREATE VIEW county_cluster_published AS
SELECT a.geoid, a.name, a.cluster_id
FROM county_cluster_assignment a
JOIN county_cluster_sizes s USING (cluster_id)
WHERE s.n_facilities >= (SELECT value FROM cluster_params WHERE name = 'min_facilities_published');

CREATE VIEW county_cluster_summary AS
SELECT s.cluster_id, s.n_counties, s.n_facilities
FROM county_cluster_sizes s
WHERE s.n_facilities >= (SELECT value FROM cluster_params WHERE name = 'min_facilities_published');
