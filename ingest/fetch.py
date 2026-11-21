"""Download public source files into data/raw/.

Each download is recorded with its size and SHA-256 so the exact file used
can be reproduced. Files already present are kept; delete one to refetch.

Usage:
    uv run ingest/fetch.py counties
    NASS_API_KEY=... uv run ingest/fetch.py cattle
    FSIS_DIRECTORY_URL=... FSIS_SUPPLEMENT_URL=... uv run ingest/fetch.py fsis

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


FSIS_FILES = {
    # env var holding the download URL, env var holding the pinned SHA-256, local name
    "directory": ("FSIS_DIRECTORY_URL", "FSIS_DIRECTORY_SHA256", "fsis_mpi_directory.csv"),
    "supplement": ("FSIS_SUPPLEMENT_URL", "FSIS_SUPPLEMENT_SHA256", "fsis_mpi_supplement.csv"),
}


def verify_checksum(path: Path, expected: str | None, delete: bool = True) -> None:
    """Stop if the file's SHA-256 does not match the pinned value.

    A fresh download is deleted on mismatch; a file that was already present is kept,
    because it may have been downloaded by hand.
    """
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    if expected and actual != expected.lower():
        if delete:
            path.unlink()
        sys.exit(f"FAIL: {path.name} checksum {actual} does not match pinned {expected}")


def fetch_fsis() -> list[Path]:
    """Download the two FSIS files from URLs supplied by the environment.

    The URLs and expected checksums are repository variables in CI, so no FSIS data is
    committed. A checksum mismatch stops the run, because the file changes weekly and an
    unexpected version should not be loaded silently.
    """
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    paths = []
    for label, (url_var, sha_var, filename) in FSIS_FILES.items():
        dest = RAW_DIR / filename
        if dest.exists():
            # Same rule as the other sources: a file already present is kept, but it is
            # still checked against the pinned checksum when one is set.
            print(f"exists  {dest.relative_to(ROOT)}")
            verify_checksum(dest, os.environ.get(sha_var), delete=False)
            print(_describe(dest))
            paths.append(dest)
            continue
        url = os.environ.get(url_var)
        if not url:
            sys.exit(f"{url_var} is not set and {dest.relative_to(ROOT)} is missing; see README (FSIS files).")
        print(f"fetch   {label}")
        resp = requests.get(url, timeout=300)
        resp.raise_for_status()
        dest.write_bytes(resp.content)
        verify_checksum(dest, os.environ.get(sha_var))
        print(_describe(dest))
        paths.append(dest)
    return paths


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


# --- History: Census County Business Patterns and NASS long series -----------------
#
# CBP publishes yearly establishment counts by county and industry. Slaughter is SIC 2011
# (Meat Packing Plants) to 1997 and NAICS 311611 (Animal, except Poultry, Slaughtering)
# from 1998. Bulk files need no API key and start in 1986.
#
# County years stop at 2016. From 2017 CBP applies a new disclosure method that drops most
# small county-industry cells: Texas slaughter rows fall from 72 counties (2016) to 6
# (2017). State totals continue, so the state files run to the latest year.
CBP_URL = "https://www2.census.gov/programs-surveys/cbp/datasets/{year}/cbp{yy}{level}.zip"
CBP_DIR = RAW_DIR / "cbp"
CBP_COUNTY_YEARS = range(1986, 2017)
CBP_STATE_YEARS = range(1986, 2024)

NASS_HISTORY_FILE = "nass_tx_all_cattle_history.json"
# All-cattle inventory only (the long series). January 1 survey estimates.
NASS_HISTORY_QUERIES = [
    {"agg_level_desc": "COUNTY", "year__GE": "1975"},
    {"agg_level_desc": "STATE", "year__GE": "1986"},
]
NASS_HISTORY_BASE = {
    "commodity_desc": "CATTLE",
    "short_desc": "CATTLE, INCL CALVES - INVENTORY",
    "source_desc": "SURVEY",
    "reference_period_desc": "FIRST OF JAN",
    "state_alpha": "TX",
    "domain_desc": "TOTAL",
    "format": "JSON",
}


def cbp_path(year: int, level: str) -> Path:
    return CBP_DIR / f"cbp{year % 100:02d}{level}.zip"


def fetch_cbp() -> list[Path]:
    """Download the CBP county (1986-2016) and state (1986 on) bulk files."""
    CBP_DIR.mkdir(parents=True, exist_ok=True)
    wanted = [(y, "co") for y in CBP_COUNTY_YEARS] + [(y, "st") for y in CBP_STATE_YEARS]
    paths, fetched = [], 0
    for year, level in wanted:
        dest = cbp_path(year, level)
        if not dest.exists():
            url = CBP_URL.format(year=year, yy=f"{year % 100:02d}", level=level)
            resp = requests.get(url, timeout=300, stream=True)
            resp.raise_for_status()
            tmp = dest.with_suffix(".part")
            with tmp.open("wb") as fh:
                for chunk in resp.iter_content(chunk_size=1 << 20):
                    fh.write(chunk)
            tmp.rename(dest)
            fetched += 1
        paths.append(dest)
    print(f"cbp     {len(paths)} files ({fetched} downloaded, {len(paths) - fetched} already present)")
    for p in paths:
        print(f"        {p.name}  {_describe(p)}")
    return paths


def fetch_nass_history() -> Path:
    key = os.environ.get("NASS_API_KEY")
    if not key:
        sys.exit("NASS_API_KEY is not set. Register free at https://quickstats.nass.usda.gov/api")
    dest = RAW_DIR / NASS_HISTORY_FILE
    if dest.exists():
        print(f"exists  {dest.relative_to(ROOT)}")
        print(_describe(dest))
        return dest
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    records, query_log = [], []
    for extra in NASS_HISTORY_QUERIES:
        print(f"query   {extra}")
        resp = requests.get(NASS_URL, params={**NASS_HISTORY_BASE, **extra, "key": key}, timeout=300)
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
        "base_params": {k: v for k, v in NASS_HISTORY_BASE.items() if k != "format"},
        "queries": query_log,
        "data": records,
    }
    dest.write_text(json.dumps(envelope, indent=1))
    print(_describe(dest))
    return dest


def fetch_history() -> None:
    fetch_cbp()
    fetch_nass_history()


if __name__ == "__main__":
    COMMANDS = {"counties": fetch_counties, "cattle": fetch_cattle, "fsis": fetch_fsis,
                "history": fetch_history}
    if len(sys.argv) != 2 or sys.argv[1] not in COMMANDS:
        sys.exit(f"usage: fetch.py {{{' | '.join(COMMANDS)}}}")
    COMMANDS[sys.argv[1]]()
