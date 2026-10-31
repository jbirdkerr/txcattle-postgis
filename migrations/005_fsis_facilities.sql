-- 005: Texas FSIS meat and poultry establishments with cattle slaughter flags.
--
-- Source: FSIS MPI Directory (locations) joined to the Establishment Demographic
-- supplement (species slaughtered). Joined on establishment_id.
--
-- county_geoid is assigned by point-in-polygon against tx_county, then checked
-- against the FSIS-published FIPS code (see the loader report). Points are staging
-- data: publish county-level aggregates only, never these rows.
--
-- Scope: FSIS covers meat and poultry, not dairy processing. The dairy_cow_slaughter
-- flag marks plants that slaughter dairy cows; it is not a dairy processor list.

CREATE TABLE fsis_establishment (
  establishment_id        text PRIMARY KEY,
  establishment_number    text NOT NULL,
  name                    text NOT NULL,
  street                  text,
  city                    text,
  zip                     text,
  activities              text,
  fsis_fips               char(5),               -- as published; NULL if unparseable
  county_geoid            char(5) REFERENCES tx_county(geoid),  -- point-in-polygon
  geom                    geography(Point, 4326),                -- NULL if no valid coordinates
  cattle_slaughter        boolean NOT NULL,
  dairy_cow_slaughter     boolean NOT NULL,
  cattle_species_flags    text[]  NOT NULL DEFAULT '{}',         -- which cattle columns were set
  CONSTRAINT dairy_implies_cattle CHECK (NOT dairy_cow_slaughter OR cattle_slaughter)
);

CREATE INDEX fsis_establishment_geom_gix ON fsis_establishment USING GIST (geom);
CREATE INDEX fsis_establishment_county_ix ON fsis_establishment (county_geoid);
