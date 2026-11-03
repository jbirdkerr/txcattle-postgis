"""Export Texas county polygons with published summary fields as GeoJSON.

Only fields from county_summary are exported. Facility points are never exported.
Null means NASS suppressed the value or published no row. Facility counts of 1 to 4
are exported with a small-count flag. Geometry is simplified (about 0.0005 degrees,
roughly 50 m) and rounded to 5 decimal places to keep the file small.

Usage:
    uv run ingest/export_geojson.py                      # writes map/data/texas_counties.geojson
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import psycopg

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT = ROOT / "map" / "data" / "texas_counties.geojson"
DEFAULT_DSN = "postgresql://txcattle:txcattle@localhost:5432/txcattle"

PROPERTIES = [
    "geoid", "name", "all_cattle_head", "all_cattle_status", "beef_cow_head",
    "milk_cow_head", "milk_cow_status", "nearest_cattle_mi", "cattle_within_25mi",
    "nearest_dairy_cow_mi", "dairy_cow_within_25mi", "cluster_id", "cattle_rank",
    "facility_proximity_rank", "cattle_25mi_small_count", "dairy_25mi_small_count",
    "nearest_cattle_mi_centre",
]
SIMPLIFY_DEG = 0.0005


def export(dsn: str, out: Path) -> int:
    cols = ", ".join(f"s.{c}" for c in PROPERTIES)
    sql = f"""
        SELECT {cols},
               ST_AsGeoJSON(
                 ST_Multi(ST_SimplifyPreserveTopology(ST_Transform(c.geom, 4326), {SIMPLIFY_DEG})),
                 5) AS geometry
        FROM county_summary s
        JOIN tx_county c ON c.geoid = s.geoid
        ORDER BY s.geoid
    """
    features = []
    with psycopg.connect(dsn) as conn:
        generated = datetime.now(timezone.utc).isoformat(timespec="seconds")
        for row in conn.execute(sql):
            *values, geometry = row
            props = {}
            for key, val in zip(PROPERTIES, values):
                if isinstance(val, float):
                    val = round(val, 2)
                props[key] = val
            features.append({
                "type": "Feature",
                "properties": props,
                "geometry": json.loads(geometry),
            })

    if len(features) == 0:
        sys.exit("FAIL: county_summary is empty; run the earlier steps first")

    collection = {
        "type": "FeatureCollection",
        "metadata": {
            "generated_at": generated,
            "source": "county_summary (published fields only)",
            "withheld": "null means no published value (NASS suppressed or no row)",
            "small_count": "facility counts of 1 to 4 are shown and flagged, not hidden",
            "geometry": "Census TIGER/Line 2025 counties, simplified and rounded",
            "descriptive_only": True,
        },
        "features": features,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(collection, separators=(",", ":")))
    print(f"wrote   {out} ({len(features)} counties, {out.stat().st_size:,} bytes)")
    return len(features)


if __name__ == "__main__":
    out_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_OUT
    export(os.environ.get("DATABASE_URL", DEFAULT_DSN), out_path)
