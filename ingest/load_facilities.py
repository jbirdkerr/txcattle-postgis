"""Load Texas FSIS meat and poultry establishments into fsis_establishment.

Inputs (from data/raw/, downloaded from the FSIS MPI Directory page):
    fsis_mpi_directory.csv   locations and FIPS codes
    fsis_mpi_supplement.csv  species slaughtered (Establishment Demographic data)

Steps:
  1. Check required headers exist; stop with the actual headers if not.
  2. Keep Texas establishments; join supplement on establishment_id.
  3. Read cattle slaughter flags. Any value outside the known set stops the load.
  4. Validate coordinates against a Texas bounding box.
  5. Replace the table in one transaction, then assign each point to a county by
     point-in-polygon and compare with the FSIS FIPS code.

Usage:
    uv run ingest/load_facilities.py [directory.csv] [supplement.csv]

Environment:
    DATABASE_URL  defaults to postgresql://txcattle:txcattle@localhost:5432/txcattle
"""

from __future__ import annotations

import csv
import os
import sys
from collections import Counter
from pathlib import Path

import psycopg

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DIRECTORY = ROOT / "data" / "raw" / "fsis_mpi_directory.csv"
DEFAULT_SUPPLEMENT = ROOT / "data" / "raw" / "fsis_mpi_supplement.csv"
DEFAULT_DSN = "postgresql://txcattle:txcattle@localhost:5432/txcattle"

DIRECTORY_COLUMNS = {
    "establishment_id", "establishment_number", "establishment_name", "street",
    "city", "state", "zip", "activities", "fips_code", "latitude", "longitude",
}

# Cattle slaughter columns from the supplement. dairy_cow_slaughter is kept
# separately because it is the dairy-relevant flag.
CATTLE_FLAGS = [
    "beef_cow_slaughter", "steer_slaughter", "heifer_slaughter", "bull_stag_slaughter",
    "dairy_cow_slaughter", "heavy_calf_slaughter", "bob_veal_slaughter",
    "formula_fed_veal_slaughter", "non_formula_fed_veal_slaughter",
]
SUPPLEMENT_COLUMNS = {"establishment_id"} | set(CATTLE_FLAGS)

TRUTHY = {"X", "Y", "YES", "TRUE", "1"}
FALSY = {""}

# Texas bounding box (approximate). Points outside it are treated as invalid.
TX_LAT = (25.8, 36.6)
TX_LON = (-106.7, -93.5)


def read_csv(path: Path, required: set[str], label: str) -> tuple[list[dict], list[str]]:
    with path.open(encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        headers = reader.fieldnames or []
        missing = required - set(headers)
        if missing:
            sys.exit(
                f"FAIL: {label} is missing columns {sorted(missing)}\n"
                f"      headers present: {headers}"
            )
        return list(reader), headers


def parse_flag(value: str, column: str, unknown: Counter) -> bool:
    v = (value or "").strip().upper()
    if v in TRUTHY:
        return True
    if v in FALSY:
        return False
    unknown[(column, v)] += 1
    return False


def parse_coord(value: str, lo: float, hi: float) -> float | None:
    try:
        x = float(value)
    except (TypeError, ValueError):
        return None
    return x if lo <= x <= hi else None


def normalize_fips(value: str) -> str | None:
    digits = "".join(ch for ch in (value or "") if ch.isdigit())
    if len(digits) == 3:          # county only; prefix Texas state FIPS
        return "48" + digits
    if len(digits) == 5 and digits.startswith("48"):
        return digits
    return None


def build_rows(directory: list[dict], supplement: list[dict]) -> tuple[list[dict], dict]:
    sup_by_id = {r["establishment_id"]: r for r in supplement}
    stats: Counter = Counter()
    unknown_flags: Counter = Counter()
    rows = []

    tx = [r for r in directory if (r.get("state") or "").strip().upper() == "TX"]
    stats["directory_total"] = len(directory)
    stats["directory_texas"] = len(tx)
    if not tx:
        sys.exit("FAIL: no Texas rows found in the directory file")

    for r in tx:
        est_id = r["establishment_id"].strip()
        sup = sup_by_id.get(est_id)
        if sup is None:
            stats["no_supplement_row"] += 1
            sup = {}

        flags = {c: parse_flag(sup.get(c, ""), c, unknown_flags) for c in CATTLE_FLAGS}
        set_flags = [c for c, on in flags.items() if on]
        if set_flags:
            stats["cattle_slaughter"] += 1
        if flags["dairy_cow_slaughter"]:
            stats["dairy_cow_slaughter"] += 1

        lat = parse_coord(r.get("latitude", ""), *TX_LAT)
        lon = parse_coord(r.get("longitude", ""), *TX_LON)
        if lat is None or lon is None:
            stats["no_valid_coordinates"] += 1
            lat = lon = None

        rows.append({
            "establishment_id": est_id,
            "establishment_number": r["establishment_number"].strip(),
            "name": r["establishment_name"].strip(),
            "street": r.get("street", "").strip() or None,
            "city": r.get("city", "").strip() or None,
            "zip": r.get("zip", "").strip() or None,
            "activities": r.get("activities", "").strip() or None,
            "fsis_fips": normalize_fips(r.get("fips_code", "")),
            "lat": lat,
            "lon": lon,
            "cattle_slaughter": bool(set_flags),
            "dairy_cow_slaughter": flags["dairy_cow_slaughter"],
            "cattle_species_flags": set_flags,
        })

    if unknown_flags:
        sys.exit(f"FAIL: unrecognized values in cattle flag columns: {dict(unknown_flags)}")

    stats["texas_rows_loaded"] = len(rows)
    return rows, dict(stats)


def load(rows: list[dict], dsn: str) -> dict:
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM fsis_establishment")
        cur.executemany(
            """
            INSERT INTO fsis_establishment (
                establishment_id, establishment_number, name, street, city, zip,
                activities, fsis_fips, geom, cattle_slaughter, dairy_cow_slaughter,
                cattle_species_flags
            ) VALUES (
                %(establishment_id)s, %(establishment_number)s, %(name)s, %(street)s,
                %(city)s, %(zip)s, %(activities)s, %(fsis_fips)s,
                CASE WHEN %(lat)s::float8 IS NULL THEN NULL
                     ELSE ST_SetSRID(ST_MakePoint(%(lon)s::float8, %(lat)s::float8), 4326)::geography
                END,
                %(cattle_slaughter)s, %(dairy_cow_slaughter)s, %(cattle_species_flags)s
            )
            """,
            rows,
        )
        # Point-in-polygon against tx_county (boundaries are NAD83, so transform).
        cur.execute("""
            UPDATE fsis_establishment f
            SET county_geoid = c.geoid
            FROM tx_county c
            WHERE f.geom IS NOT NULL
              AND ST_Covers(c.geom, ST_Transform(f.geom::geometry, 4269))
        """)

        cur.execute("""
            SELECT
              count(*) AS total,
              count(*) FILTER (WHERE geom IS NULL) AS no_point,
              count(*) FILTER (WHERE geom IS NOT NULL AND county_geoid IS NULL) AS outside_counties,
              count(*) FILTER (WHERE county_geoid IS NOT NULL) AS assigned,
              count(*) FILTER (WHERE county_geoid IS NOT NULL AND fsis_fips IS NOT NULL
                                AND county_geoid <> fsis_fips) AS fips_mismatch,
              count(*) FILTER (WHERE fsis_fips IS NULL) AS no_fsis_fips
            FROM fsis_establishment
        """)
        total, no_point, outside, assigned, mismatch, no_fips = cur.fetchone()

        cur.execute("""
            SELECT establishment_id, name, city, county_geoid, fsis_fips
            FROM fsis_establishment
            WHERE county_geoid IS NOT NULL AND fsis_fips IS NOT NULL
              AND county_geoid <> fsis_fips
            LIMIT 5
        """)
        mismatch_sample = cur.fetchall()

    return {
        "total": total, "no_point": no_point, "outside_counties": outside,
        "assigned": assigned, "fips_mismatch": mismatch, "no_fsis_fips": no_fips,
        "mismatch_sample": mismatch_sample,
    }


def main() -> None:
    directory_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_DIRECTORY
    supplement_path = Path(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_SUPPLEMENT
    for p in (directory_path, supplement_path):
        if not p.exists():
            sys.exit(f"missing {p}; download the FSIS CSVs into data/raw/")

    directory, dir_headers = read_csv(directory_path, DIRECTORY_COLUMNS, "directory")
    supplement, _ = read_csv(supplement_path, SUPPLEMENT_COLUMNS, "supplement")
    print(f"read    {len(directory)} directory rows, {len(supplement)} supplement rows")

    rows, stats = build_rows(directory, supplement)
    print("\nTexas establishments")
    for key in ("directory_texas", "texas_rows_loaded", "cattle_slaughter",
                "dairy_cow_slaughter", "no_supplement_row", "no_valid_coordinates"):
        print(f"  {key:22} {stats.get(key, 0):5d}")

    dsn = os.environ.get("DATABASE_URL", DEFAULT_DSN)
    result = load(rows, dsn)
    print("\ncounty assignment (point-in-polygon)")
    for key in ("total", "assigned", "no_point", "outside_counties",
                "fips_mismatch", "no_fsis_fips"):
        print(f"  {key:18} {result[key]:5d}")
    if result["mismatch_sample"]:
        print("  sample mismatches (establishment, name, city, assigned, FSIS):")
        for row in result["mismatch_sample"]:
            print("   ", row)
    print(f"\nload    {result['total']} rows in fsis_establishment")


if __name__ == "__main__":
    main()
