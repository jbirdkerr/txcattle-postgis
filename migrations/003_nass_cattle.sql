-- 003: NASS county cattle inventory (Quick Stats), keyed to tx_county.
--
-- One row per county, year, program, and published series. Values are stored
-- as published: `raw_value` keeps the original string, `value` is the parsed
-- integer, and NULL where NASS suppressed the estimate. `suppression_code`
-- records the marker (for example '(D)' = withheld to avoid disclosure).
--
-- Series names (short_desc, class_desc) are kept as NASS publishes them. They
-- are mapped to analysis categories (all cattle, beef cows, milk cows) in a
-- view after the loaded names are checked against the real data.

CREATE TABLE nass_county_cattle (
  geoid            char(5) NOT NULL REFERENCES tx_county(geoid),
  year             integer NOT NULL,
  source_program   text    NOT NULL CHECK (source_program IN ('CENSUS', 'SURVEY')),
  short_desc       text    NOT NULL,
  class_desc       text    NOT NULL,
  unit_desc        text    NOT NULL,
  raw_value        text    NOT NULL,
  value            integer,
  suppression_code text,
  PRIMARY KEY (geoid, year, source_program, short_desc),
  CONSTRAINT value_or_suppressed CHECK (
    (value IS NOT NULL AND suppression_code IS NULL)
    OR (value IS NULL AND suppression_code IS NOT NULL)
  )
);

CREATE INDEX nass_county_cattle_geoid_ix ON nass_county_cattle (geoid);
