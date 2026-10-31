-- 001: extensions
-- Requires the postgis/postgis image (see docker-compose.yml).

CREATE EXTENSION IF NOT EXISTS postgis;

-- Sanity check: fails loudly if PostGIS is missing.
DO $$
BEGIN
  PERFORM PostGIS_Version();
END
$$;
