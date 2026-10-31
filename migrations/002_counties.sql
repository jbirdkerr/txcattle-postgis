-- 002: Texas counties from Census TIGER/Line 2025.
--
-- geom       : boundary as published (NAD83, EPSG:4269). Used for joins.
-- internal_pt: TIGER internal point (INTPTLAT/INTPTLON), stored as geography.
--              Census internal points are guaranteed to fall inside the county,
--              unlike centroids of concave shapes. NAD83 and WGS84 differ by
--              about a metre, which is negligible here; treated as WGS84.
--
-- Distances use geography, so results are in metres on the spheroid.

CREATE TABLE tx_county (
  geoid         char(5)  PRIMARY KEY,            -- state FIPS (48) + county FIPS
  county_fips   char(3)  NOT NULL,
  name          text     NOT NULL,               -- e.g. 'Travis'
  name_long     text     NOT NULL,               -- e.g. 'Travis County'
  land_area_m2  double precision NOT NULL,
  water_area_m2 double precision NOT NULL,
  geom          geometry(MultiPolygon, 4269) NOT NULL,
  internal_pt   geography(Point, 4326) NOT NULL,
  CONSTRAINT tx_county_texas_only CHECK (geoid LIKE '48___')
);

CREATE INDEX tx_county_geom_gix ON tx_county USING GIST (geom);
CREATE INDEX tx_county_pt_gix   ON tx_county USING GIST (internal_pt);
