-- 013: history of slaughter establishments and cattle inventory, 1986 on.
--
-- Sources (see DATA_SOURCES.md):
--   cbp_county_slaughter  Census County Business Patterns, establishments by county,
--                         1986-2016. SIC 2011 to 1997, NAICS 311611 from 1998.
--   cbp_state_slaughter   the same series for Texas as a whole, 1986 to the latest year.
--   nass_cattle_history   NASS all-cattle inventory, January 1, by county (1975 on;
--                         NASS published no county estimates for 1988-1992).
--   nass_state_cattle_history  NASS all-cattle inventory, January 1, Texas.
--
-- This is a DIFFERENT measure from the FSIS layer. CBP counts employer establishments
-- in the slaughter industry: it includes hog, sheep, and game slaughter and plants that
-- are not federally inspected, and excludes businesses with no employees. It is never
-- joined to or compared directly with the FSIS counts.

CREATE TABLE cbp_county_slaughter (
  year        int     NOT NULL,
  geoid       char(5) NOT NULL REFERENCES tx_county(geoid),
  code_system text    NOT NULL CHECK (code_system IN ('SIC 2011', 'NAICS 311611')),
  estab       int     NOT NULL CHECK (estab > 0),
  PRIMARY KEY (year, geoid)
);

CREATE TABLE cbp_state_slaughter (
  year        int  PRIMARY KEY,
  code_system text NOT NULL CHECK (code_system IN ('SIC 2011', 'NAICS 311611')),
  estab       int  NOT NULL CHECK (estab >= 0)
);

CREATE TABLE nass_cattle_history (
  year  int     NOT NULL,
  geoid char(5) NOT NULL REFERENCES tx_county(geoid),
  head  int,                                 -- NULL when suppressed
  suppression_code text,
  PRIMARY KEY (year, geoid),
  CHECK ((head IS NULL) <> (suppression_code IS NULL))
);

CREATE TABLE nass_state_cattle_history (
  year int    PRIMARY KEY,
  head bigint NOT NULL
);

-- One row per county per CBP county year.
--
-- No CBP row means zero employer establishments. This holds for 1986-2016 because CBP
-- did not suppress establishment counts in those years: the loader checks every year that
-- the county rows sum exactly to the state total. Counts of 1 to 4 are flagged as small,
-- like the FSIS counts (migration 010).
CREATE VIEW county_history_published AS
WITH years AS (
  SELECT DISTINCT year FROM cbp_county_slaughter
),
nass_years AS (
  SELECT DISTINCT year FROM nass_cattle_history
)
SELECT
  y.year,
  c.geoid,
  c.name,
  s.code_system,
  coalesce(b.estab, 0)                       AS slaughter_estab,
  (coalesce(b.estab, 0) BETWEEN 1 AND 4)     AS estab_small_count,
  n.head                                     AS all_cattle_head,
  CASE
    WHEN ny.year IS NULL        THEN 'no county estimates'
    WHEN n.head IS NOT NULL     THEN 'published'
    WHEN n.suppression_code IS NOT NULL THEN 'suppressed'
    ELSE 'no row'
  END                                        AS all_cattle_status
FROM years y
CROSS JOIN tx_county c
JOIN cbp_state_slaughter s ON s.year = y.year
LEFT JOIN cbp_county_slaughter b ON b.year = y.year AND b.geoid = c.geoid
LEFT JOIN nass_cattle_history n  ON n.year = y.year AND n.geoid = c.geoid
LEFT JOIN nass_years ny          ON ny.year = y.year;

-- Texas as a whole: cattle per slaughter establishment.
CREATE VIEW state_history_published AS
SELECT
  s.year,
  s.code_system,
  s.estab                                    AS slaughter_estab,
  n.head                                     AS all_cattle_head,
  CASE WHEN s.estab > 0 THEN round(n.head::numeric / s.estab) END AS cattle_per_estab
FROM cbp_state_slaughter s
LEFT JOIN nass_state_cattle_history n USING (year);
