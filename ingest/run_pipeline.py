"""Run the pipeline stages in order and write a public run manifest.

The manifest records each stage's title, description, status, duration, and the
checksums of its outputs. It never records commands, arguments, or environment
variables, so secrets (for example the NASS API key) cannot reach published output.

Usage:
    uv run ingest/run_pipeline.py                 # full build, writes build/manifest.json
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MANIFEST = ROOT / "build" / "manifest.json"
DSN = os.environ.get("DATABASE_URL", "postgresql://txcattle:txcattle@localhost:5432/txcattle")


@dataclass
class Stage:
    name: str
    title: str
    description: str
    cmd: list[str]
    outputs: list[str] = field(default_factory=list)  # paths relative to ROOT


def default_stages() -> list[Stage]:
    return [
        Stage("migrate", "Build the database schema",
              "Apply the numbered SQL migrations in order.", ["./migrate.sh"]),
        Stage("fetch_counties", "Download county boundaries",
              "Census TIGER/Line 2025 county file, Texas filtered later.",
              ["uv", "run", "ingest/fetch.py", "counties"],
              ["data/raw/tl_2025_us_county.zip"]),
        Stage("load_counties", "Load and check county boundaries",
              "Load 254 Texas counties and check geometry and internal points.",
              ["uv", "run", "ingest/load_counties.py"]),
        Stage("check_counties", "Validate the county join",
              "Count, uniqueness, validity, and overlap checks on real data.",
              ["psql", "-v", "ON_ERROR_STOP=1", "-q", "-f", "tests/test_counties.sql", DSN]),
        Stage("fetch_cattle", "Download county cattle inventory",
              "USDA NASS Quick Stats, county totals, census and survey series.",
              ["uv", "run", "ingest/fetch.py", "cattle"],
              ["data/raw/nass_tx_cattle_inventory_county.json"]),
        Stage("load_cattle", "Load and check cattle inventory",
              "Parse values, keep suppression markers, reject duplicate keys.",
              ["uv", "run", "ingest/load_cattle.py"]),
        Stage("check_cattle", "Validate the cattle view",
              "One row per county, year, and program; status consistency.",
              ["psql", "-v", "ON_ERROR_STOP=1", "-q", "-f", "tests/test_cattle_view.sql", DSN]),
        Stage("fetch_fsis", "Download FSIS establishment files",
              "MPI directory and demographic supplement, checked against pinned checksums.",
              ["uv", "run", "ingest/fetch.py", "fsis"],
              ["data/raw/fsis_mpi_directory.csv", "data/raw/fsis_mpi_supplement.csv"]),
        Stage("load_facilities", "Load Texas cattle slaughter plants",
              "Filter to Texas, flag cattle and dairy cow slaughter, assign counties.",
              ["uv", "run", "ingest/load_facilities.py"]),
        Stage("fetch_history", "Download slaughter establishment history",
              "Census County Business Patterns (1986 on) and the NASS all-cattle series.",
              ["uv", "run", "ingest/fetch.py", "history"],
              ["data/raw/nass_tx_all_cattle_history.json"]),
        Stage("load_history", "Load and check the history",
              "County establishment counts must sum to the Texas total in every year.",
              ["uv", "run", "ingest/load_history.py"]),
        Stage("export_history", "Export the history for the map",
              "Establishments by county and year, and the statewide cattle-per-plant series.",
              ["uv", "run", "ingest/export_history.py"],
              ["map/data/texas_history.json"]),
        Stage("export_geojson", "Export county map data",
              "Published county fields only. Facility points are never exported.",
              ["uv", "run", "ingest/export_geojson.py"],
              ["map/data/texas_counties.geojson"]),
        Stage("make_report", "Write the summary report",
              "Generated from the published views, with every number taken from the database.",
              ["uv", "run", "ingest/make_report.py"], ["REPORT.md"]),
    ]


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _output_records(root: Path, outputs: list[str]) -> list[dict]:
    records = []
    for rel in outputs:
        path = root / rel
        if path.exists():
            records.append({"file": rel, "sha256": _sha256(path), "bytes": path.stat().st_size})
        else:
            records.append({"file": rel, "sha256": None, "bytes": None})
    return records


def _build_id() -> str:
    run_id = os.environ.get("GITHUB_RUN_ID")
    if run_id:
        return f"gha-{run_id}"
    return "local-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _git_commit() -> str:
    sha = os.environ.get("GITHUB_SHA")
    if sha:
        return sha[:12]
    try:
        return subprocess.run(["git", "rev-parse", "--short=12", "HEAD"], cwd=ROOT,
                              capture_output=True, text=True, check=True).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"


def run_stages(stages: list[Stage], manifest_path: Path, root: Path = ROOT) -> bool:
    """Run stages in order. Stop at the first failure and mark the rest skipped."""
    started = datetime.now(timezone.utc)
    results, ok = [], True
    for stage in stages:
        if not ok:
            results.append({"name": stage.name, "title": stage.title,
                            "description": stage.description, "status": "skipped",
                            "duration_ms": None, "outputs": []})
            continue
        print(f"\n== {stage.title}", flush=True)
        t0 = time.perf_counter()
        proc = subprocess.run(stage.cmd, cwd=root)
        ms = int((time.perf_counter() - t0) * 1000)
        ok = proc.returncode == 0
        results.append({"name": stage.name, "title": stage.title,
                        "description": stage.description,
                        "status": "ok" if ok else "error",
                        "duration_ms": ms,
                        "outputs": _output_records(root, stage.outputs) if ok else []})

    manifest = {
        "build_id": _build_id(),
        "git_commit": _git_commit(),
        "started_at": started.isoformat(timespec="seconds"),
        "finished_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "status": "ok" if ok else "error",
        "steps": results,
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2))
    print(f"\nmanifest  {manifest_path} ({manifest['status']})")
    return ok


# The page renders the manifest, so it is built after the manifest is written rather
# than as a stage of its own. Its output is the published site, not a data step.
PAGE_CMD = ["uv", "run", "ingest/build_page.py"]


def main() -> None:
    ok = run_stages(default_stages(), DEFAULT_MANIFEST)
    if ok:
        print("\n== Build the public page", flush=True)
        ok = subprocess.run(PAGE_CMD, cwd=ROOT).returncode == 0
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
