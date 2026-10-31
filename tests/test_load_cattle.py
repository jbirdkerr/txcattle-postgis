"""Tests for the NASS cattle loader.

Uses SYNTHETIC counties and SYNTHETIC NASS-shaped records. No real
values are used. Runs against TEST_DATABASE_URL, never the development database.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import psycopg
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "ingest"))

import load_cattle as lc  # noqa: E402
import load_counties as lcty  # noqa: E402
from make_fixture import build as build_county_fixture  # noqa: E402

TEST_DSN = os.environ.get(
    "TEST_DATABASE_URL", "postgresql://txcattle:txcattle@localhost:5432/txcattle_test"
)
MIGRATIONS = ROOT / "migrations"
FIXTURE_JSON = ROOT / "tests" / "fixtures" / "SYNTHETIC_nass_cattle.json"


def _record(county_code, value, year=2022, program="CENSUS", desc="CATTLE, INVENTORY"):
    return {
        "state_fips_code": "48",
        "county_code": county_code,
        "county_name": f"SYNTH{county_code}",
        "year": str(year),
        "source_desc": program,
        "short_desc": desc,
        "class_desc": "ALL CLASSES",
        "unit_desc": "HEAD",
        "Value": value,
    }


def write_fixture() -> Path:
    """SYNTHETIC records for the three synthetic counties, plus one unmatched code."""
    records = [
        _record("001", "1,234"),         # formatted number
        _record("003", "(D)"),           # suppressed
        _record("005", "567"),           # plain number
        _record("999", "42"),            # not a Texas county in tx_county: skipped
        # Milk cow series, which the view reports on: 001 published, 003 suppressed,
        # 005 absent (no row).
        _record("001", "300", desc="CATTLE, COWS, MILK - INVENTORY"),
        _record("003", "(D)", desc="CATTLE, COWS, MILK - INVENTORY"),
    ]
    FIXTURE_JSON.parent.mkdir(parents=True, exist_ok=True)
    FIXTURE_JSON.write_text(json.dumps({"data": records}))
    return FIXTURE_JSON


@pytest.fixture(scope="module")
def loaded():
    county_zip = build_county_fixture()
    with psycopg.connect(TEST_DSN, autocommit=True) as conn:
        conn.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
        conn.execute("CREATE EXTENSION postgis;")
        conn.execute((MIGRATIONS / "002_counties.sql").read_text())
        conn.execute((MIGRATIONS / "003_nass_cattle.sql").read_text())
        conn.execute((MIGRATIONS / "004_cattle_views.sql").read_text())
    lcty.load(lcty.read_texas_counties(county_zip), TEST_DSN)
    path = write_fixture()
    with psycopg.connect(TEST_DSN) as conn:
        texas = {r[0] for r in conn.execute("SELECT geoid FROM tx_county")}
    rows, skipped = lc.to_rows(lc.load_records(path), texas)
    lc.load(rows, TEST_DSN)
    return rows, skipped


@pytest.mark.parametrize("raw,expected", [
    ("1,234", (1234, None)),
    ("567", (567, None)),
    ("(D)", (None, "(D)")),
    ("(Z)", (None, "(Z)")),
    ("", (None, "(BLANK)")),
])
def test_parse_value(raw, expected):
    assert lc.parse_value(raw) == expected


def test_unmatched_county_is_skipped_and_reported(loaded):
    rows, skipped = loaded
    assert skipped == {"48999": 1}
    assert all(r["geoid"] != "48999" for r in rows)


def test_database_values_and_markers(loaded):
    with psycopg.connect(TEST_DSN) as conn:
        got = dict(conn.execute(
            """SELECT geoid, value FROM nass_county_cattle
               WHERE short_desc = 'CATTLE, INVENTORY' ORDER BY geoid"""
        ).fetchall())
        suppressed = conn.execute(
            """SELECT geoid, suppression_code FROM nass_county_cattle
               WHERE value IS NULL AND short_desc = 'CATTLE, INVENTORY'"""
        ).fetchall()
    assert got == {"48001": 1234, "48003": None, "48005": 567}
    assert suppressed == [("48003", "(D)")]


def test_foreign_key_rejects_unknown_county():
    with psycopg.connect(TEST_DSN) as conn:
        with pytest.raises(psycopg.errors.ForeignKeyViolation):
            conn.execute(
                """INSERT INTO nass_county_cattle
                   (geoid, year, source_program, short_desc, class_desc, unit_desc,
                    raw_value, value, suppression_code)
                   VALUES ('48999', 2022, 'CENSUS', 'X', 'ALL CLASSES', 'HEAD', '1', 1, NULL)"""
            )


def test_duplicate_keys_are_detected(tmp_path, capsys):
    """Two records with the same county/year/series must stop the load."""
    dup = [_record("001", "10"), _record("001", "20")]
    with pytest.raises(SystemExit):
        lc.check_duplicates(dup)
    assert "duplicate keys" in capsys.readouterr().out


def test_no_duplicates_passes(capsys):
    lc.check_duplicates([_record("001", "10"), _record("003", "20")])
    assert "no duplicate keys" in capsys.readouterr().out


def test_view_keeps_absent_counties_as_no_row(loaded):
    """County 48005 has no milk row, so its milk status must be 'no row', not zero."""
    with psycopg.connect(TEST_DSN) as conn:
        status, head = conn.execute(
            """SELECT milk_cow_status, milk_cow_head FROM county_cattle
               WHERE geoid = '48005' AND year = 2022 AND source_program = 'CENSUS'"""
        ).fetchone()
    assert (status, head) == ("no row", None)


def test_view_marks_published_suppressed_and_absent(loaded):
    with psycopg.connect(TEST_DSN) as conn:
        rows = dict(conn.execute(
            """SELECT geoid, milk_cow_status FROM county_cattle
               WHERE year = 2022 AND source_program = 'CENSUS'"""
        ).fetchall())
    assert rows == {"48001": "published", "48003": "suppressed", "48005": "no row"}
