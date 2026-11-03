"""Tests for county_summary ranks using SYNTHETIC counties, facilities, and NASS rows."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import psycopg
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "ingest"))

import load_counties as lcty  # noqa: E402
from make_fixture import build as build_county_fixture  # noqa: E402

TEST_DSN = os.environ.get(
    "TEST_DATABASE_URL", "postgresql://txcattle:txcattle@localhost:5432/txcattle_test"
)
MIGRATIONS = ROOT / "migrations"
MIGRATION_ORDER = [
    "002_counties.sql", "003_nass_cattle.sql", "004_cattle_views.sql",
    "005_fsis_facilities.sql", "006_county_facility_metrics.sql",
    "007_published_distance_rule.sql", "008_county_clusters.sql",
    "009_county_summary.sql", "010_show_small_counts.sql",
    "011_boundary_distance.sql", "012_miles.sql",
]


@pytest.fixture(scope="module")
def db():
    county_zip = build_county_fixture()
    with psycopg.connect(TEST_DSN, autocommit=True) as conn:
        conn.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
        conn.execute("CREATE EXTENSION postgis;")
        for name in MIGRATION_ORDER:
            conn.execute((MIGRATIONS / name).read_text())
    lcty.load(lcty.read_texas_counties(county_zip), TEST_DSN)
    with psycopg.connect(TEST_DSN, autocommit=True) as conn:
        # Plants: two inside 48001, so 2 within 25 miles: ranked and flagged as a small count.
        for est_id, lat, lon in [("P1", 30.5 + 0.0899, -97.5), ("P3", 30.5 + 0.18, -97.5)]:
            conn.execute(
                """INSERT INTO fsis_establishment
                   (establishment_id, establishment_number, name, geom, cattle_slaughter,
                    dairy_cow_slaughter)
                   VALUES (%s, %s, %s, ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography,
                           true, false)""",
                (est_id, "E" + est_id, "SYNTH " + est_id, lon, lat),
            )
        # SYNTHETIC all-cattle inventory, latest survey year: 48001 higher than 48003.
        for geoid, head in [("48001", 5000), ("48003", 3000)]:
            conn.execute(
                """INSERT INTO nass_county_cattle
                   (geoid, year, source_program, short_desc, class_desc, unit_desc,
                    raw_value, value, suppression_code)
                   VALUES (%s, 2026, 'SURVEY', 'CATTLE, INCL CALVES - INVENTORY',
                           'INCL CALVES', 'HEAD', %s, %s, NULL)""",
                (geoid, f"{head:,}", head),
            )
    with psycopg.connect(TEST_DSN) as conn:
        yield conn


def test_cattle_rank_follows_inventory(db):
    ranks = dict(db.execute(
        "SELECT geoid, cattle_rank FROM county_summary WHERE cattle_rank IS NOT NULL"
    ).fetchall())
    assert ranks == {"48001": 1, "48003": 2}


def test_small_facility_count_is_ranked_and_flagged(db):
    """Migration 010: 48001 has 2 cattle plants within 25 miles. Shown, ranked, and flagged."""
    rank, flag = db.execute(
        """SELECT facility_proximity_rank, cattle_25mi_small_count
           FROM county_summary WHERE geoid = '48001'"""
    ).fetchone()
    assert rank is not None
    assert flag is True


def test_county_without_inventory_gets_no_cattle_rank(db):
    rank = db.execute(
        "SELECT cattle_rank FROM county_summary WHERE geoid = '48005'"
    ).fetchone()[0]
    assert rank is None


def test_one_row_per_county(db):
    n, distinct = db.execute(
        "SELECT count(*), count(DISTINCT geoid) FROM county_summary"
    ).fetchone()
    assert n == distinct == 3
