"""Load NASS county cattle inventory (from fetch.py cattle) into nass_county_cattle.

Steps:
  1. Check the expected fields exist (fails with the actual keys if NASS changed them).
  2. Map state FIPS + county code to GEOID and keep only Texas counties in tx_county.
  3. Parse values. Formatted numbers ('1,234') become integers. Markers such as
     '(D)' (withheld by NASS to protect confidentiality) become NULL with
     suppression_code set.
  4. Replace the table contents in one transaction and report coverage.

Usage:
    uv run ingest/load_cattle.py [path/to/nass_tx_cattle_inventory_county.json]

Environment:
    DATABASE_URL  defaults to postgresql://txcattle:txcattle@localhost:5432/txcattle
"""

from __future__ import annotations

import json
import os
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import psycopg

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_JSON = ROOT / "data" / "raw" / "nass_tx_cattle_inventory_county.json"
DEFAULT_DSN = "postgresql://txcattle:txcattle@localhost:5432/txcattle"

REQUIRED_FIELDS = {
    "state_fips_code", "county_code", "year", "source_desc",
    "short_desc", "class_desc", "unit_desc",
}
NUMERIC = re.compile(r"^-?[\d,]+$")


def parse_value(raw: str | None) -> tuple[int | None, str | None]:
    """Return (value, suppression_code). Exactly one is non-null."""
    text = (raw or "").strip()
    if NUMERIC.match(text):
        return int(text.replace(",", "")), None
    # Markers like '(D)', '(Z)', '(NA)'. Anything else is recorded as-is so
    # nothing is silently dropped.
    return None, text if text else "(BLANK)"


def value_field(rec: dict) -> str | None:
    """NASS has used both 'Value' and 'value'; accept either."""
    for key in ("value", "Value"):
        if key in rec:
            return rec[key]
    return None


def load_records(path: Path) -> list[dict]:
    envelope = json.loads(path.read_text())
    records = envelope["data"] if isinstance(envelope, dict) else envelope
    if not records:
        sys.exit(f"FAIL: no records in {path.name}")
    missing = REQUIRED_FIELDS - set(records[0])
    if missing or value_field(records[0]) is None:
        sys.exit(
            "FAIL: expected NASS fields missing: "
            f"{sorted(missing | ({'value'} if value_field(records[0]) is None else set()))}\n"
            f"      fields present: {sorted(records[0])}"
        )
    print(f"read    {len(records)} NASS records from {path.name}")
    return records


def check_duplicates(records: list[dict]) -> None:
    """Fail before any write if two records share a primary key.

    Shows which fields differ among the colliding records so the cause is
    visible (typically a domain breakdown the query did not filter out).
    """
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for rec in records:
        key = (rec["state_fips_code"] + rec["county_code"], rec["year"],
               rec["source_desc"], rec["short_desc"])
        groups[key].append(rec)
    dupes = {k: v for k, v in groups.items() if len(v) > 1}
    if not dupes:
        print("check   no duplicate keys")
        return
    sample_key, sample = next(iter(dupes.items()))
    varying = sorted(
        f for f in set().union(*sample) if len({str(r.get(f)) for r in sample}) > 1
    )
    print(f"FAIL: {len(dupes)} duplicate keys. Example {sample_key}:")
    for r in sample:
        print("   ", {f: r.get(f) for f in varying})
    sys.exit("Fix the query filters in fetch.py (e.g. domain) and re-fetch.")


def to_rows(records: list[dict], texas_geoids: set[str]) -> tuple[list[dict], Counter]:
    rows, skipped = [], Counter()
    for rec in records:
        geoid = rec["state_fips_code"] + rec["county_code"]
        if geoid not in texas_geoids:
            skipped[geoid] += 1
            continue
        value, suppression = parse_value(value_field(rec))
        rows.append({
            "geoid": geoid,
            "year": int(rec["year"]),
            "source_program": rec["source_desc"],
            "short_desc": rec["short_desc"],
            "class_desc": rec["class_desc"],
            "unit_desc": rec["unit_desc"],
            "raw_value": (value_field(rec) or "").strip(),
            "value": value,
            "suppression_code": suppression,
        })
    return rows, skipped


def report(rows: list[dict], texas_geoids: set[str]) -> None:
    print("\nseries (source / year / short_desc -> counties with a row, suppressed):")
    groups: dict[tuple, dict] = defaultdict(lambda: {"geoids": set(), "suppressed": 0})
    for r in rows:
        g = groups[(r["source_program"], r["year"], r["short_desc"])]
        g["geoids"].add(r["geoid"])
        g["suppressed"] += r["suppression_code"] is not None
    for (src, yr, desc), g in sorted(groups.items()):
        missing = len(texas_geoids) - len(g["geoids"])
        print(f"  {src:7} {yr}  {desc[:60]:60}  "
              f"{len(g['geoids']):3d} counties  suppressed={g['suppressed']:3d}  "
              f"missing={missing:3d}")

    markers = Counter(r["suppression_code"] for r in rows if r["suppression_code"])
    print(f"\nsuppression markers: {dict(markers) or 'none'}")
    print(f"class_desc values:   {sorted({r['class_desc'] for r in rows})}")


def load(rows: list[dict], dsn: str) -> None:
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM nass_county_cattle")
        cur.executemany(
            """
            INSERT INTO nass_county_cattle (
                geoid, year, source_program, short_desc, class_desc, unit_desc,
                raw_value, value, suppression_code
            ) VALUES (
                %(geoid)s, %(year)s, %(source_program)s, %(short_desc)s,
                %(class_desc)s, %(unit_desc)s, %(raw_value)s, %(value)s,
                %(suppression_code)s
            )
            """,
            rows,
        )
        cur.execute("SELECT count(*) FROM nass_county_cattle")
        (count,) = cur.fetchone()
    print(f"\nload    {count} rows in nass_county_cattle")


def main() -> None:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_JSON
    if not path.exists():
        sys.exit(f"missing {path}; run: NASS_API_KEY=... uv run ingest/fetch.py cattle")

    dsn = os.environ.get("DATABASE_URL", DEFAULT_DSN)
    with psycopg.connect(dsn) as conn:
        texas_geoids = {r[0] for r in conn.execute("SELECT geoid FROM tx_county")}
    if not texas_geoids:
        sys.exit("FAIL: tx_county is empty; run load_counties.py first")

    records = load_records(path)
    check_duplicates(records)
    rows, skipped = to_rows(records, texas_geoids)
    if skipped:
        print(f"skip    {sum(skipped.values())} records outside tx_county: {dict(skipped)}")
    report(rows, texas_geoids)
    load(rows, dsn)


if __name__ == "__main__":
    main()
