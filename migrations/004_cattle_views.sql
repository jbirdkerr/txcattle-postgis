-- 004: analysis view over nass_county_cattle.
--
-- One row per county, year, and program. Each category has its value, and a
-- status that keeps three situations apart:
--   'published'   a number was published
--   'suppressed'  a row exists but NASS withheld the value, e.g. '(D)'
--   'no row'      NASS returned nothing for this county and series
--
-- 'no row' is NOT treated as zero. Whether absence means zero is still being
-- checked against NASS documentation; see LIMITATIONS.md.

CREATE VIEW county_cattle AS
WITH series AS (
  SELECT DISTINCT year, source_program FROM nass_county_cattle
)
SELECT
  c.geoid,
  c.name,
  s.year,
  s.source_program,
  max(n.value) FILTER (WHERE n.short_desc = 'CATTLE, INCL CALVES - INVENTORY') AS all_cattle_head,
  CASE
    WHEN count(*) FILTER (WHERE n.short_desc = 'CATTLE, INCL CALVES - INVENTORY') = 0 THEN 'no row'
    WHEN bool_or(n.short_desc = 'CATTLE, INCL CALVES - INVENTORY' AND n.value IS NULL) THEN 'suppressed'
    ELSE 'published'
  END AS all_cattle_status,
  max(n.value) FILTER (WHERE n.short_desc = 'CATTLE, COWS, BEEF - INVENTORY') AS beef_cow_head,
  CASE
    WHEN count(*) FILTER (WHERE n.short_desc = 'CATTLE, COWS, BEEF - INVENTORY') = 0 THEN 'no row'
    WHEN bool_or(n.short_desc = 'CATTLE, COWS, BEEF - INVENTORY' AND n.value IS NULL) THEN 'suppressed'
    ELSE 'published'
  END AS beef_cow_status,
  max(n.value) FILTER (WHERE n.short_desc = 'CATTLE, COWS, MILK - INVENTORY') AS milk_cow_head,
  CASE
    WHEN count(*) FILTER (WHERE n.short_desc = 'CATTLE, COWS, MILK - INVENTORY') = 0 THEN 'no row'
    WHEN bool_or(n.short_desc = 'CATTLE, COWS, MILK - INVENTORY' AND n.value IS NULL) THEN 'suppressed'
    ELSE 'published'
  END AS milk_cow_status
FROM tx_county c
CROSS JOIN series s
LEFT JOIN nass_county_cattle n
  ON n.geoid = c.geoid
 AND n.year = s.year
 AND n.source_program = s.source_program
GROUP BY c.geoid, c.name, s.year, s.source_program;
