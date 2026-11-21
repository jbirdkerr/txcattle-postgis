"""Export the slaughter-establishment history for the map's year slider.

Writes map/data/texas_history.json, keyed by county GEOID so the map can reuse the
county shapes already in texas_counties.geojson. Only published view fields are
exported: establishment counts by county and year (CBP, 1986-2016), county cattle
inventory where NASS published it, and the Texas-wide series (1986 on).

Usage:
    uv run ingest/export_history.py
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import psycopg

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT = ROOT / "map" / "data" / "texas_history.json"
DEFAULT_DSN = "postgresql://txcattle:txcattle@localhost:5432/txcattle"


def export(dsn: str, out: Path) -> dict:
    with psycopg.connect(dsn) as conn:
        county = conn.execute("""
            SELECT year, geoid, code_system, slaughter_estab, all_cattle_head, all_cattle_status
            FROM county_history_published ORDER BY geoid, year
        """).fetchall()
        state = conn.execute("""
            SELECT year, code_system, slaughter_estab, all_cattle_head, cattle_per_estab
            FROM state_history_published ORDER BY year
        """).fetchall()
    if not county or not state:
        sys.exit("FAIL: history views are empty; run load_history.py first")

    years = sorted({r[0] for r in county})
    code_system = {str(r[0]): r[2] for r in county}
    no_county_cattle = sorted({r[0] for r in county if r[5] == "no county estimates"})
    counties: dict[str, dict] = {}
    for year, geoid, _, estab, head, _status in county:
        c = counties.setdefault(geoid, {"estab": [], "cattle": []})
        c["estab"].append(estab)
        c["cattle"].append(head)
    for c in counties.values():
        if len(c["estab"]) != len(years):
            sys.exit("FAIL: a county is missing years in county_history_published")

    doc = {
        "metadata": {
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "source": "county_history_published and state_history_published",
            "measure": "Census County Business Patterns employer establishments in the "
                       "slaughter industry (all livestock except poultry). Not the FSIS count.",
            "code_break": "SIC 2011 to 1997, NAICS 311611 from 1998; the two are not comparable",
            "cattle": "NASS all-cattle inventory, January 1; null where not published",
            "descriptive_only": True,
        },
        "years": years,
        "code_system": code_system,
        "no_county_cattle_years": no_county_cattle,
        "counties": counties,
        "state": [
            {"year": y, "code_system": cs, "slaughter_estab": e,
             "all_cattle_head": h, "cattle_per_estab": int(r) if r is not None else None}
            for y, cs, e, h, r in state
        ],
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, separators=(",", ":")))
    print(f"wrote   {out.relative_to(ROOT) if out.is_relative_to(ROOT) else out} "
          f"({len(counties)} counties x {len(years)} years, {len(state)} state years, "
          f"{out.stat().st_size:,} bytes)")
    return doc


if __name__ == "__main__":
    out_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_OUT
    export(os.environ.get("DATABASE_URL", DEFAULT_DSN), out_path)
