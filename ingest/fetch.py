"""Download public source files into data/raw/.

Each download is recorded with its size and SHA-256 so the exact file used
can be reproduced. Files already present are kept; delete one to refetch.

Usage:
    uv run ingest/fetch.py counties
    NASS_API_KEY=... uv run ingest/fetch.py cattle

The NASS Quick Stats API needs a free key: https://quickstats.nass.usda.gov/api
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"

COUNTIES_URL = "https://www2.census.gov/geo/tiger/TIGER2025/COUNTY/tl_2025_us_county.zip"
COUNTIES_FILE = "tl_2025_us_county.zip"

NASS_URL = "https://quickstats.nass.usda.gov/api/api_GET/"
NASS_FILE = "nass_tx_cattle_inventory_county.json"

# Two queries, combined. CENSUS is the 2022 county census; SURVEY covers the
# annual county estimates from 2021 on. Any change to these windows should be
# made here and recorded in DATA_SOURCES.md.
NASS_QUERIES = [
    {"source_desc": "CENSUS", "year": "2022"},
    {"source_desc": "SURVEY", "year__GE": "2021"},
]
# domain_desc/domaincat_desc restrict to the whole-population total. Without
# them NASS also returns size-class breakdowns of the same series, which
# collide on (county, year, series) and inflate counts. Verified cause of
# duplicate keys on the first load attempt.
NASS_BASE_PARAMS = {
    "commodity_desc": "CATTLE",
    "statisticcat_desc": "INVENTORY",
    "agg_level_desc": "COUNTY",
    "state_alpha": "TX",
    "domain_desc": "TOTAL",
    "domaincat_desc": "NOT SPECIFIED",
    "format": "JSON",
}


def _describe(path: Path) -> str:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return f"sha256  {digest}  {path.stat().st_size:,} bytes"


def fetch_counties() -> Path:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    dest = RAW_DIR / COUNTIES_FILE
    if dest.exists():
        print(f"exists  {dest.relative_to(ROOT)}")
    else:
        print(f"fetch   {COUNTIES_URL}")
        resp = requests.get(COUNTIES_URL, timeout=120, stream=True)
        resp.raise_for_status()
        with dest.open("wb") as fh:
            for chunk in resp.iter_content(chunk_size=1 << 20):
                fh.write(chunk)
    print(_describe(dest))
    return dest


def fetch_cattle() -> Path:
    key = os.environ.get("NASS_API_KEY")
    if not key:
        sys.exit("NASS_API_KEY is not set. Register free at https://quickstats.nass.usda.gov/api")

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    dest = RAW_DIR / NASS_FILE
    if dest.exists():
        print(f"exists  {dest.relative_to(ROOT)}")
        print(_describe(dest))
        return dest

    records: list[dict] = []
    query_log = []
    for extra in NASS_QUERIES:
        params = {**NASS_BASE_PARAMS, **extra, "key": key}
        print(f"query   {extra}")
        resp = requests.get(NASS_URL, params=params, timeout=120)
        resp.raise_for_status()
        payload = resp.json()
        if "error" in payload:
            sys.exit(f"NASS returned an error: {payload['error']}")
        rows = payload.get("data", [])
        print(f"        {len(rows)} records")
        records.extend(rows)
        query_log.append({"params": extra, "records": len(rows)})

    envelope = {
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "base_params": {k: v for k, v in NASS_BASE_PARAMS.items() if k != "format"},
        "queries": query_log,
        "data": records,
    }
    dest.write_text(json.dumps(envelope, indent=1))
    print(_describe(dest))
    return dest


if __name__ == "__main__":
    COMMANDS = {"counties": fetch_counties, "cattle": fetch_cattle}
    if len(sys.argv) != 2 or sys.argv[1] not in COMMANDS:
        sys.exit(f"usage: fetch.py {{{' | '.join(COMMANDS)}}}")
    COMMANDS[sys.argv[1]]()
