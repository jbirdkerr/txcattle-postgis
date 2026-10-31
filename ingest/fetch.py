"""Download public source files into data/raw/.

Each download is recorded with its size and SHA-256 so the exact file used
can be reproduced. Files already present are kept; delete one to refetch.

Usage:
    uv run ingest/fetch.py counties
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import requests

RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"

SOURCES = {
    # Census TIGER/Line 2025, national counties. Filename pattern follows
    # other TIGER2025 layers; confirm on first run (a 404 means the path differs).
    "counties": (
        "https://www2.census.gov/geo/tiger/TIGER2025/COUNTY/tl_2025_us_county.zip",
        "tl_2025_us_county.zip",
    ),
}


def fetch(name: str) -> Path:
    url, filename = SOURCES[name]
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    dest = RAW_DIR / filename

    if dest.exists():
        print(f"exists  {dest.relative_to(RAW_DIR.parent.parent)}")
    else:
        print(f"fetch   {url}")
        resp = requests.get(url, timeout=120, stream=True)
        resp.raise_for_status()
        with dest.open("wb") as fh:
            for chunk in resp.iter_content(chunk_size=1 << 20):
                fh.write(chunk)

    digest = hashlib.sha256(dest.read_bytes()).hexdigest()
    print(f"sha256  {digest}  {dest.stat().st_size:,} bytes")
    return dest


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in SOURCES:
        sys.exit(f"usage: fetch.py {{{' | '.join(SOURCES)}}}")
    fetch(sys.argv[1])
