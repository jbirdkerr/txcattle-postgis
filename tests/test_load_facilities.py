"""Tests for the FSIS facility loader.

Uses SYNTHETIC directory and supplement CSVs written to a temp folder, and the
SYNTHETIC counties from make_fixture.py. No FSIS data is used. Runs against
TEST_DATABASE_URL, never the development database.
"""

from __future__ import annotations

import csv
import os
import sys
from pathlib import Path

import psycopg
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "ingest"))

import load_counties as lcty  # noqa: E402
import load_facilities as lf  # noqa: E402
from make_fixture import build as build_county_fixture  # noqa: E402

TEST_DSN = os.environ.get(
    "TEST_DATABASE_URL", "postgresql://txcattle:txcattle@localhost:5432/txcattle_test"
)
MIGRATIONS = ROOT / "migrations"

DIRECTORY_HEADER = [
    "establishment_id", "establishment_number", "establishment_name", "duns_number",
    "street", "city", "state", "zip", "phone", "grant_date", "activities", "dbas",
    "district", "circuit", "size", "latitude", "longitude", "county", "fips_code",
]
# Same columns as the real supplement's cattle block; the loader requires all of them.
SUPPLEMENT_HEADER = ["establishment_number", "establishment_id", "establishment_name"] + lf.CATTLE_FLAGS


def directory_row(est_id, name, state, lat, lon, fips):
    row = dict.fromkeys(DIRECTORY_HEADER, "")
    row.update({
        "establishment_id": est_id, "establishment_number": f"E{est_id}",
        "establishment_name": name, "street": "1 SYNTH ST", "city": "SYNTHVILLE",
        "state": state, "zip": "00000", "activities": "Slaughter", "size": "Small",
        "latitude": lat, "longitude": lon, "fips_code": fips,
    })
    return row


def write_inputs(tmp: Path):
    """SYNTHETIC plants. Points placed inside the synthetic counties on purpose."""
    dirs = [
        # Inside synthetic 48001 (lon -98..-97, lat 30..31), FIPS agrees.
        directory_row("1", "SYNTH BEEF A", "TX", "30.5", "-97.5", "48001"),
        # Inside synthetic 48003 (lon -97..-96), but FSIS says 48999: mismatch.
        directory_row("2", "SYNTH DAIRY B", "TX", "30.5", "-96.5", "48999"),
        # Texas, valid coordinates, outside every synthetic county: unassigned.
        directory_row("3", "SYNTH OUTSIDE C", "TX", "33.0", "-100.0", "48001"),
        # Coordinates outside the Texas box: rejected, point stays NULL.
        directory_row("4", "SYNTH BADCOORD D", "TX", "45.0", "-120.0", "48001"),
        # Not Texas: excluded entirely.
        directory_row("5", "SYNTH OKLAHOMA E", "OK", "35.5", "-98.5", "40001"),
    ]
    sups = [
        {"establishment_number": "E1", "establishment_id": "1", "establishment_name": "A",
         "beef_cow_slaughter": "X", "dairy_cow_slaughter": "", "steer_slaughter": "X"},
        {"establishment_number": "E2", "establishment_id": "2", "establishment_name": "B",
         "beef_cow_slaughter": "", "dairy_cow_slaughter": "X", "steer_slaughter": ""},
        {"establishment_number": "E3", "establishment_id": "3", "establishment_name": "C",
         "beef_cow_slaughter": "", "dairy_cow_slaughter": "", "steer_slaughter": ""},
        # Plant 4 has no supplement row: must be counted, not dropped.
    ]
    dpath, spath = tmp / "directory.csv", tmp / "supplement.csv"
    for path, header, data in ((dpath, DIRECTORY_HEADER, dirs), (spath, SUPPLEMENT_HEADER, sups)):
        with path.open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=header, restval="")
            w.writeheader()
            w.writerows(data)
    return dpath, spath


@pytest.fixture(scope="module")
def loaded(tmp_path_factory):
    county_zip = build_county_fixture()
    with psycopg.connect(TEST_DSN, autocommit=True) as conn:
        conn.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
        conn.execute("CREATE EXTENSION postgis;")
        for name in ("002_counties.sql", "003_nass_cattle.sql",
                     "004_cattle_views.sql", "005_fsis_facilities.sql"):
            conn.execute((MIGRATIONS / name).read_text())
    lcty.load(lcty.read_texas_counties(county_zip), TEST_DSN)

    tmp = tmp_path_factory.mktemp("fsis")
    dpath, spath = write_inputs(tmp)
    directory, _ = lf.read_csv(dpath, lf.DIRECTORY_COLUMNS, "directory")
    supplement, _ = lf.read_csv(spath, lf.SUPPLEMENT_COLUMNS, "supplement")
    rows, stats = lf.build_rows(directory, supplement)
    result = lf.load(rows, TEST_DSN)
    return rows, stats, result


def test_only_texas_rows_loaded(loaded):
    rows, stats, _ = loaded
    assert stats["directory_texas"] == 4
    assert {r["establishment_id"] for r in rows} == {"1", "2", "3", "4"}


def test_cattle_and_dairy_flags(loaded):
    rows, stats, _ = loaded
    by_id = {r["establishment_id"]: r for r in rows}
    assert by_id["1"]["cattle_slaughter"] and not by_id["1"]["dairy_cow_slaughter"]
    assert by_id["2"]["dairy_cow_slaughter"] and by_id["2"]["cattle_slaughter"]
    assert not by_id["3"]["cattle_slaughter"]
    assert stats["cattle_slaughter"] == 2
    assert stats["dairy_cow_slaughter"] == 1


def test_missing_supplement_counted_not_dropped(loaded):
    _, stats, _ = loaded
    assert stats["no_supplement_row"] == 1


def test_coordinates_outside_texas_rejected(loaded):
    _, stats, _ = loaded
    assert stats["no_valid_coordinates"] == 1


def test_county_assignment_and_fips_mismatch(loaded):
    _, _, result = loaded
    assert result["total"] == 4
    assert result["assigned"] == 2            # plants 1 and 2
    assert result["no_point"] == 1            # plant 4
    assert result["outside_counties"] == 1    # plant 3
    assert result["fips_mismatch"] == 1       # plant 2: county 48003 vs FSIS 48999
    assert result["mismatch_sample"][0][0] == "2"


def test_database_geography_and_county_codes(loaded):
    with psycopg.connect(TEST_DSN) as conn:
        got = dict(conn.execute(
            "SELECT establishment_id, county_geoid FROM fsis_establishment"
        ).fetchall())
    assert got == {"1": "48001", "2": "48003", "3": None, "4": None}


def test_unknown_flag_value_fails(tmp_path):
    rows = [{"establishment_id": "9", "establishment_number": "E9",
             "establishment_name": "X", "street": "", "city": "", "state": "TX",
             "zip": "", "activities": "", "fips_code": "48001",
             "latitude": "30.5", "longitude": "-97.5"}]
    sup = [{"establishment_id": "9", "beef_cow_slaughter": "MAYBE"}]
    with pytest.raises(SystemExit) as exc:
        lf.build_rows(rows, sup)
    assert "unrecognized values" in str(exc.value)


def test_missing_header_fails(tmp_path):
    path = tmp_path / "bad.csv"
    path.write_text("establishment_id,name\n1,x\n", encoding="utf-8")
    with pytest.raises(SystemExit) as exc:
        lf.read_csv(path, lf.DIRECTORY_COLUMNS, "directory")
    assert "missing columns" in str(exc.value)
