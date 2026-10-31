-- Validation for the county_cattle view on the REAL load (run after load_cattle.py).

-- Expect: 0 (exactly one row per county, year, and program)
SELECT count(*) AS duplicate_view_rows FROM (
  SELECT geoid, year, source_program FROM county_cattle
  GROUP BY 1, 2, 3 HAVING count(*) > 1
) d;

-- Expect: 254 per year and program (every Texas county appears)
SELECT year, source_program, count(*) AS counties
FROM county_cattle GROUP BY 1, 2 ORDER BY 1, 2;

-- Milk cow coverage by year: how many counties have a published number.
-- This is the dairy analysis's real sample size.
SELECT year, source_program,
       count(*) FILTER (WHERE milk_cow_status = 'published') AS milk_published,
       count(*) FILTER (WHERE milk_cow_status = 'suppressed') AS milk_suppressed,
       count(*) FILTER (WHERE milk_cow_status = 'no row') AS milk_no_row
FROM county_cattle GROUP BY 1, 2 ORDER BY 1, 2;

-- Expect: 0 published values where status is not 'published'
SELECT count(*) AS status_mismatch FROM county_cattle
WHERE (milk_cow_status = 'published') <> (milk_cow_head IS NOT NULL);
