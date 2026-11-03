"""Tests for county facility metrics using SYNTHETIC counties and SYNTHETIC facility points.

Distances are from the county BOUNDARY, in miles (migration 012). Synthetic county 48001
spans lat 30 to 31, lon -98 to -97. Facilities placed north of its top edge (lat 31) are
at known distances. 0.1 deg of latitude is about 11.0 km, or 6.8 miles.
"""

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
    "009_county_summary.sql", "010_show_small_counts.sql", "011_boundary_distance.sql", "012_miles.sql",
]

# (id, lat, lon, cattle, dairy_cow). All sit north of 48001's top edge (lat 31).
# At 31 deg N one degree of latitude is about 110.9 km, so 0.1 deg is ~11.0 km (6.8 mi).
# Rings: 10 miles = 16.09 km, 25 miles = 40.23 km.
FACILITIES = [
    ("Q1", 31.0 + 0.10, -97.5, True, False),   # ~11.0 km = 6.8 mi: inside 10 mi
    ("Q2", 31.0 + 0.25, -97.5, True, False),   # ~27.7 km = 17.2 mi: inside 25 mi
    ("Q3", 31.0 + 0.18, -97.5, True, True),    # ~19.9 km = 12.3 mi: cattle and dairy cow
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
        for est_id, lat, lon, cattle, dairy in FACILITIES:
            conn.execute(
                """INSERT INTO fsis_establishment
                   (establishment_id, establishment_number, name, geom,
                    cattle_slaughter, dairy_cow_slaughter)
                   VALUES (%s, %s, %s, ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography,
                           %s, %s)""",
                (est_id, "E" + est_id, "SYNTH " + est_id, lon, lat, cattle, dairy),
            )
    with psycopg.connect(TEST_DSN) as conn:
        yield conn


def metrics(conn, geoid):
    return conn.execute(
        """SELECT nearest_cattle_mi, cattle_within_10mi, cattle_within_25mi,
                  nearest_dairy_cow_mi, dairy_cow_within_25mi, nearest_cattle_mi_centre
           FROM county_facility_metrics WHERE geoid = %s""",
        (geoid,),
    ).fetchone()


def test_nearest_cattle_distance_is_boundary_distance(db):
    nearest, *_ = metrics(db, "48001")
    assert 6.7 < nearest < 6.9


def test_radius_counts_use_boundary_distance(db):
    _, within10, within25, _, _, _ = metrics(db, "48001")
    assert within10 == 1          # Q1 at ~6.8 miles is inside 10 miles
    assert within25 == 3          # Q1, Q2 (~17.2 miles) and Q3 (~12.3 miles)


def test_dairy_cow_distance_and_count(db):
    _, _, _, nearest_dairy, dairy25, _ = metrics(db, "48001")
    assert 12.2 < nearest_dairy < 12.4   # Q3, the only dairy cow plant
    assert dairy25 == 1


def test_centre_distance_kept_as_reference(db):
    *_, centre = metrics(db, "48001")
    # Internal point (-97.5, 30.5) to Q1 (31.1): about 41.4 miles.
    assert 41.2 < centre < 41.7


def test_plant_inside_county_has_zero_boundary_distance(db):
    db.execute(
        """INSERT INTO fsis_establishment
           (establishment_id, establishment_number, name, geom, cattle_slaughter, dairy_cow_slaughter)
           VALUES ('IN1', 'EIN1', 'SYNTH IN1',
                   ST_SetSRID(ST_MakePoint(-97.5, 30.5), 4326)::geography, true, false)"""
    )
    try:
        nearest, within10, *_ = metrics(db, "48001")
        assert nearest == 0
        assert within10 >= 1
    finally:
        db.execute("DELETE FROM fsis_establishment WHERE establishment_id = 'IN1'")


def test_every_county_has_a_row(db):
    n = db.execute("SELECT count(*) FROM county_facility_metrics").fetchone()[0]
    assert n == 3


def test_county_far_from_facilities_gets_zero_counts(db):
    # 48005 is about 90 miles east: no plants within 25 miles, so counts are 0, not NULL.
    _, within10, within25, _, dairy25, _ = metrics(db, "48005")
    assert (within10, within25, dairy25) == (0, 0, 0)


def test_published_view_shows_small_counts_with_flags(db):
    row = db.execute(
        """SELECT cattle_within_10mi, cattle_within_25mi, dairy_cow_within_25mi,
                  cattle_10mi_small_count, cattle_25mi_small_count, dairy_25mi_small_count
           FROM county_facility_published WHERE geoid = '48001'"""
    ).fetchone()
    assert row == (1, 3, 1, True, True, True)


def test_published_view_shows_distances(db):
    row = db.execute(
        """SELECT nearest_cattle_mi, nearest_dairy_cow_mi, nearest_cattle_mi_centre
           FROM county_facility_published WHERE geoid = '48001'"""
    ).fetchone()
    assert 6.7 < row[0] < 6.9
    assert 12.2 < row[1] < 12.4
    assert 41.2 < row[2] < 41.7


def test_published_view_keeps_distance_when_no_plants_in_radius(db):
    row = db.execute(
        """SELECT nearest_cattle_mi FROM county_facility_published WHERE geoid = '48005'"""
    ).fetchone()
    assert row[0] is not None and row[0] > 25   # miles


def test_published_view_keeps_zero(db):
    row = db.execute(
        """SELECT cattle_within_10mi FROM county_facility_published WHERE geoid = '48005'"""
    ).fetchone()
    assert row == (0,)
