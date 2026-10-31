"""Load Texas county boundaries from the Census TIGER/Line national county file.

Reads the zipped shapefile directly (no GDAL dependency), keeps state FIPS 48,
repairs invalid geometries, and replaces tx_county in one transaction.

Usage:
    uv run ingest/load_counties.py [path/to/tl_2025_us_county.zip]

Environment:
    DATABASE_URL  defaults to postgresql://txcattle:txcattle@localhost:5432/txcattle
"""

from __future__ import annotations

import io
import os
import sys
import zipfile
from pathlib import Path

import psycopg
import shapefile  # pyshp
from shapely import make_valid
from shapely.geometry import MultiPolygon, shape
from shapely.geometry.base import BaseGeometry

RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"
DEFAULT_ZIP = RAW_DIR / "tl_2025_us_county.zip"
TEXAS_FIPS = "48"
EXPECTED_TX_COUNTIES = 254  # Texas has 254 counties; a mismatch means a bad input.
DEFAULT_DSN = "postgresql://txcattle:txcattle@localhost:5432/txcattle"


def read_texas_counties(zip_path: Path) -> list[dict]:
    """Return one record per Texas county with WKT geometry and attributes."""
    with zipfile.ZipFile(zip_path) as zf:
        stem = next(n[:-4] for n in zf.namelist() if n.endswith(".shp"))
        reader = shapefile.Reader(
            shp=io.BytesIO(zf.read(f"{stem}.shp")),
            shx=io.BytesIO(zf.read(f"{stem}.shx")),
            dbf=io.BytesIO(zf.read(f"{stem}.dbf")),
        )

        rows = []
        repaired = 0
        for sr in reader.iterShapeRecords():
            rec = sr.record.as_dict()
            if rec["STATEFP"] != TEXAS_FIPS:
                continue

            geom: BaseGeometry = shape(sr.shape.__geo_interface__)
            if not geom.is_valid:
                geom = make_valid(geom)
                repaired += 1
            if geom.geom_type == "Polygon":
                geom = MultiPolygon([geom])

            rows.append(
                {
                    "geoid": rec["GEOID"],
                    "county_fips": rec["COUNTYFP"],
                    "name": rec["NAME"],
                    "name_long": rec["NAMELSAD"],
                    "land_area_m2": float(rec["ALAND"]),
                    "water_area_m2": float(rec["AWATER"]),
                    "lat": float(rec["INTPTLAT"]),
                    "lon": float(rec["INTPTLON"]),
                    "wkt": geom.wkt,
                }
            )

    print(f"read    {len(rows)} Texas counties from {zip_path.name}")
    print(f"repair  {repaired} invalid geometries made valid")
    return rows


def validate(rows: list[dict], expected: int = EXPECTED_TX_COUNTIES) -> None:
    """Fail loudly on anything that would make the join unreliable.

    `expected` is a parameter so tests can run on small fixtures; the CLI always
    uses the real count.
    """
    if len(rows) != expected:
        sys.exit(f"FAIL: expected {expected} Texas counties, got {len(rows)}")

    geoids = [r["geoid"] for r in rows]
    if len(set(geoids)) != len(geoids):
        dupes = sorted({g for g in geoids if geoids.count(g) > 1})
        sys.exit(f"FAIL: duplicate GEOIDs: {dupes}")

    if any(not g.startswith(TEXAS_FIPS) for g in geoids):
        sys.exit("FAIL: non-Texas GEOID present")

    print(f"check   {len(rows)} counties, unique GEOIDs, all Texas")


def load(rows: list[dict], dsn: str) -> None:
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM tx_county")
        cur.executemany(
            """
            INSERT INTO tx_county (
                geoid, county_fips, name, name_long,
                land_area_m2, water_area_m2, geom, internal_pt
            )
            VALUES (
                %(geoid)s, %(county_fips)s, %(name)s, %(name_long)s,
                %(land_area_m2)s, %(water_area_m2)s,
                ST_GeomFromText(%(wkt)s, 4269),
                ST_SetSRID(ST_MakePoint(%(lon)s, %(lat)s), 4326)::geography
            )
            """,
            rows,
        )
        cur.execute("SELECT count(*) FROM tx_county")
        (count,) = cur.fetchone()
    print(f"load    {count} rows in tx_county")


def main() -> None:
    zip_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_ZIP
    if not zip_path.exists():
        sys.exit(f"missing {zip_path}; run: uv run ingest/fetch.py counties")

    rows = read_texas_counties(zip_path)
    validate(rows)
    load(rows, os.environ.get("DATABASE_URL", DEFAULT_DSN))


if __name__ == "__main__":
    main()
