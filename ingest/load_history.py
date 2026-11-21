"""Load the slaughter-establishment and cattle-inventory history (from fetch.py history).

Steps:
  1. Read Texas slaughter rows from each CBP bulk zip, without unpacking it. The industry
     code is SIC 2011 to 1997 and NAICS 311611 from 1998.
  2. Check, for every county year, that the county rows sum exactly to the Texas total.
     This is what makes "no row" safe to read as zero establishments. A mismatch stops
     the load.
  3. Read the NASS all-cattle history (county and state, January 1).
  4. Replace the four history tables in one transaction.

Usage:
    uv run ingest/load_history.py

Environment:
    DATABASE_URL  defaults to postgresql://txcattle:txcattle@localhost:5432/txcattle
"""

from __future__ import annotations

import csv
import io
import json
import os
import sys
import zipfile
from pathlib import Path

import psycopg

sys.path.insert(0, str(Path(__file__).resolve().parent))

import fetch  # noqa: E402
from load_cattle import parse_value, value_field  # noqa: E402

DEFAULT_DSN = "postgresql://txcattle:txcattle@localhost:5432/txcattle"
TEXAS = "48"
LAST_SIC_YEAR = 1997


def code_for(year: int) -> tuple[str, str, str]:
    """Return (column, code, label) for the slaughter industry in a given year."""
    if year <= LAST_SIC_YEAR:
        return "sic", "2011", "SIC 2011"
    return "naics", "311611", "NAICS 311611"


def read_cbp_zip(path: Path, year: int) -> list[dict]:
    """Return the Texas slaughter rows in a CBP county or state zip.

    Column names are lower-cased and stripped; older files differ only in case and quoting.
    State files from 2008 on break totals out by legal form of organisation (lfo); only the
    all-forms row ('-') is kept.
    """
    col, code, _ = code_for(year)
    with zipfile.ZipFile(path) as zf:
        members = [m for m in zf.namelist() if m.lower().endswith((".txt", ".csv"))]
        if len(members) != 1:
            sys.exit(f"FAIL: expected one data file in {path.name}, found {members}")
        with zf.open(members[0]) as raw:
            reader = csv.reader(io.TextIOWrapper(raw, encoding="latin-1", newline=""))
            header = [h.strip().strip('"').lower() for h in next(reader)]
            missing = {"fipstate", col, "est"} - set(header)
            if missing:
                sys.exit(f"FAIL: {path.name} lacks columns {sorted(missing)}; has {header}")
            idx = {h: i for i, h in enumerate(header)}
            rows = []
            for rec in reader:
                if rec[idx["fipstate"]].strip() != TEXAS or rec[idx[col]].strip() != code:
                    continue
                if "lfo" in idx and rec[idx["lfo"]].strip() not in ("-", ""):
                    continue
                row = {"est": int(rec[idx["est"]])}
                if "fipscty" in idx:
                    row["fipscty"] = rec[idx["fipscty"]].strip()
                rows.append(row)
    return rows


def read_cbp(cbp_dir: Path, county_years, state_years) -> tuple[list[dict], list[dict]]:
    county_rows, state_rows = [], []
    for year in state_years:
        rows = read_cbp_zip(cbp_dir / fetch.cbp_path(year, "st").name, year)
        if len(rows) != 1:
            sys.exit(f"FAIL: {year} state file has {len(rows)} Texas slaughter rows, expected 1")
        state_rows.append({"year": year, "code_system": code_for(year)[2], "estab": rows[0]["est"]})
    state_by_year = {r["year"]: r["estab"] for r in state_rows}

    for year in county_years:
        rows = read_cbp_zip(cbp_dir / fetch.cbp_path(year, "co").name, year)
        unallocated = sum(r["est"] for r in rows if r["fipscty"] == "999")
        counties = [r for r in rows if r["fipscty"] != "999"]
        total = sum(r["est"] for r in counties)
        if unallocated or total != state_by_year.get(year):
            sys.exit(f"FAIL: {year} county establishments sum to {total} "
                     f"(+{unallocated} statewide) but the Texas total is "
                     f"{state_by_year.get(year)}. No-row-means-zero no longer holds.")
        for r in counties:
            county_rows.append({"year": year, "geoid": TEXAS + r["fipscty"],
                                "code_system": code_for(year)[2], "estab": r["est"]})
    print(f"read    CBP: {len(state_rows)} state years, {len(county_years)} county years, "
          f"{len(county_rows)} county rows; county sums match the state total every year")
    return county_rows, state_rows


def read_nass_history(path: Path, texas_geoids: set[str]) -> tuple[list[dict], list[dict]]:
    records = json.loads(path.read_text())["data"]
    county, state, skipped = [], [], 0
    for rec in records:
        if rec.get("reference_period_desc") != "FIRST OF JAN":
            continue
        head, suppression = parse_value(value_field(rec))
        year = int(rec["year"])
        if rec["agg_level_desc"] == "STATE":
            if head is None:
                sys.exit(f"FAIL: Texas state inventory for {year} is {suppression}")
            state.append({"year": year, "head": head})
            continue
        geoid = rec["state_fips_code"] + rec["county_code"]
        if geoid not in texas_geoids:      # 998 = combined counties
            skipped += 1
            continue
        county.append({"year": year, "geoid": geoid, "head": head, "suppression_code": suppression})
    keys = [(r["year"], r["geoid"]) for r in county]
    if len(keys) != len(set(keys)):
        sys.exit("FAIL: duplicate (year, county) in NASS history; check the fetch filters")
    print(f"read    NASS: {len(county)} county rows, {len(state)} state years "
          f"({skipped} combined-county rows skipped)")
    return county, state


def load(dsn: str, county_cbp, state_cbp, county_nass, state_nass) -> None:
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        for table in ("cbp_county_slaughter", "cbp_state_slaughter",
                      "nass_cattle_history", "nass_state_cattle_history"):
            cur.execute(f"DELETE FROM {table}")
        cur.executemany("INSERT INTO cbp_state_slaughter (year, code_system, estab) "
                        "VALUES (%(year)s, %(code_system)s, %(estab)s)", state_cbp)
        cur.executemany("INSERT INTO cbp_county_slaughter (year, geoid, code_system, estab) "
                        "VALUES (%(year)s, %(geoid)s, %(code_system)s, %(estab)s)", county_cbp)
        cur.executemany("INSERT INTO nass_cattle_history (year, geoid, head, suppression_code) "
                        "VALUES (%(year)s, %(geoid)s, %(head)s, %(suppression_code)s)", county_nass)
        cur.executemany("INSERT INTO nass_state_cattle_history (year, head) "
                        "VALUES (%(year)s, %(head)s)", state_nass)
    print(f"load    {len(county_cbp)} county and {len(state_cbp)} state CBP rows; "
          f"{len(county_nass)} county and {len(state_nass)} state NASS rows")


def main() -> None:
    dsn = os.environ.get("DATABASE_URL", DEFAULT_DSN)
    with psycopg.connect(dsn) as conn:
        texas_geoids = {g for (g,) in conn.execute("SELECT geoid FROM tx_county")}
    if len(texas_geoids) != 254:
        sys.exit("FAIL: tx_county is not loaded; run load_counties.py first")
    county_cbp, state_cbp = read_cbp(fetch.CBP_DIR, fetch.CBP_COUNTY_YEARS, fetch.CBP_STATE_YEARS)
    unknown = {r["geoid"] for r in county_cbp} - texas_geoids
    if unknown:
        sys.exit(f"FAIL: CBP county codes not in tx_county: {sorted(unknown)}")
    county_nass, state_nass = read_nass_history(fetch.RAW_DIR / fetch.NASS_HISTORY_FILE, texas_geoids)
    load(dsn, county_cbp, state_cbp, county_nass, state_nass)


if __name__ == "__main__":
    main()
