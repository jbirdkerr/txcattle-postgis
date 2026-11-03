"""Write REPORT.md from the published views. Every number comes from the database.

Usage:
    uv run ingest/make_report.py            # writes REPORT.md at the repo root

Environment:
    DATABASE_URL  defaults to postgresql://txcattle:txcattle@localhost:5432/txcattle
"""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path

import psycopg

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "REPORT.md"
DEFAULT_DSN = "postgresql://txcattle:txcattle@localhost:5432/txcattle"


def fetch(conn, sql: str, params=()):
    return conn.execute(sql, params).fetchall()


def table(headers: list[str], rows: list[tuple]) -> str:
    def cell(v):
        if v is None:
            return "withheld"
        if isinstance(v, float):
            return f"{v:,.1f}"
        if isinstance(v, int):
            return f"{v:,}"
        return str(v)
    lines = ["| " + " | ".join(headers) + " |",
             "|" + "|".join("---" for _ in headers) + "|"]
    lines += ["| " + " | ".join(cell(v) for v in r) + " |" for r in rows]
    return "\n".join(lines)


def main() -> None:
    dsn = os.environ.get("DATABASE_URL", DEFAULT_DSN)
    with psycopg.connect(dsn) as conn:
        counties = fetch(conn, "SELECT count(*) FROM tx_county")[0][0]
        plants = fetch(conn, "SELECT count(*) FROM fsis_establishment WHERE cattle_slaughter")[0][0]
        dairy_plants = fetch(conn, "SELECT count(*) FROM fsis_establishment WHERE dairy_cow_slaughter")[0][0]
        latest_year = fetch(conn, "SELECT max(year) FROM nass_county_cattle WHERE source_program='SURVEY'")[0][0]

        coverage = fetch(conn, """
            SELECT year, source_program,
                   count(*) FILTER (WHERE milk_cow_status = 'published'),
                   count(*) FILTER (WHERE milk_cow_status = 'suppressed'),
                   count(*) FILTER (WHERE milk_cow_status = 'no row')
            FROM county_cattle GROUP BY 1, 2 ORDER BY 1, 2""")

        small_counts = fetch(conn, """
            SELECT count(*) FILTER (WHERE cattle_25mi_small_count),
                   count(*) FILTER (WHERE dairy_25mi_small_count)
            FROM county_facility_published""")[0]

        clusters = fetch(conn, """
            SELECT cluster_id, n_counties, n_facilities
            FROM county_cluster_summary ORDER BY n_facilities DESC""")
        cluster_members = fetch(conn, """
            SELECT cluster_id, string_agg(name, ', ' ORDER BY name)
            FROM county_cluster_published GROUP BY cluster_id ORDER BY cluster_id""")

        top_cattle = fetch(conn, """
            SELECT cattle_rank, name, all_cattle_head FROM county_summary
            WHERE cattle_rank IS NOT NULL ORDER BY cattle_rank LIMIT 10""")
        top_facility = fetch(conn, """
            SELECT facility_proximity_rank, name, cattle_within_25mi, nearest_cattle_mi
            FROM county_summary WHERE facility_proximity_rank IS NOT NULL
            ORDER BY facility_proximity_rank LIMIT 10""")

    cluster_lines = "\n".join(
        f"- Cluster {cid}: {n_c} counties, {n_f} cattle plants within 25 miles of its counties."
        for cid, n_c, n_f in clusters
    ) or "- No cluster met the publication threshold."
    member_lines = "\n".join(
        f"- Cluster {cid}: {names}" for cid, names in cluster_members
    ) or "- None published."

    text = f"""# Texas Cattle Slaughter Capacity by County: Summary

*Generated {date.today().isoformat()} from the project database. Descriptive only:
these results show where facilities and reported cattle are located. They do not
show causes, do not attribute any disease to any facility, and do not identify outbreak zones.*

## What the data covers

- {counties} Texas counties (2025 Census boundaries).
- {plants} Texas establishments that slaughter cattle, from FSIS. {dairy_plants} of them
  slaughter dairy cows. FSIS does not cover dairy processing, so dairy processors are not in this analysis.
- County cattle inventories from USDA NASS, latest survey year {latest_year}.

## Dairy coverage

Milk cow counts are published for few counties. Coverage by year:

{table(["Year", "Source", "Published", "Suppressed", "No row"], coverage)}

Any dairy result rests on this sample. Counts are withheld where NASS suppresses them
and where NASS published no row, which is not treated as zero.

## Facility proximity

Counts of 1 to 4 are shown and flagged as small counts, because they are unstable,
not because they are confidential: the FSIS directory is public. There are
{small_counts[0]} counties flagged for cattle plant counts and {small_counts[1]} for dairy
cow plant counts. NASS suppressed values are shown as "withheld".

## Clusters

Clusters group counties that sit close to cattle slaughter capacity. They describe
facility density, not disease.

{cluster_lines}

{member_lines}

## Rankings

Two separate rankings. They measure different things and should not be combined.

**Largest all-cattle inventory (NASS {latest_year}):**

{table(["Rank", "County", "All cattle (head)"], top_cattle)}

**Closest cattle slaughter capacity (most plants within 25 miles, then nearest distance):**

{table(["Rank", "County", "Plants within 25 miles", "Nearest plant to county boundary (miles)"], top_facility)}

Distances are from the county boundary: 0 means a plant is inside the county.

## Limitations

See `LIMITATIONS.md`. The most important points for reading this summary:

- Facility counts and distances describe location, not activity or exposure.
- Counts of 1 to 4 are flagged as small counts and can swing widely.
- Inventories are modelled county estimates, not counts.
- Dairy results rest on the small milk cow sample shown above.
- Clusters are descriptive groupings with arbitrary labels.
"""
    OUT.write_text(text)
    print(f"wrote   {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
