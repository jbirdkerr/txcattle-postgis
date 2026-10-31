"""Tests for county facility metrics using SYNTHETIC counties and SYNTHETIC facility points.

Synthetic county 48001 has its internal point at (-97.5, 30.5). Facilities are placed
at known distances north and south of that point. 1 degree of latitude is about
111.2 km, so 0.0899 deg is about 10.0 km and 0.18 deg is about 20.0 km.
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

# (id, lat, lon, cattle, dairy_cow). Coordinates chosen relative to 48001's internal point.
FACILITIES = [
    ("P1", 30.5 + 0.0899, -97.5, True, False),   # ~10.0 km north, cattle only
    ("P2", 30.5 - 0.25, -97.5, True, False),     # ~27.8 km south, cattle only (outside 25 km)
    ("P3", 30.5 + 0.18, -97.5, True, True),      # ~20.0 km north, cattle and dairy cow
]


@pytest.fixture(scope="module")
def db():
    county_zip = build_county_fixture()
    with psycopg.connect(TEST_DSN, autocommit=True) as conn:
        conn.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
        conn.execute("CREATE EXTENSION postgis;")
        for name in ("002_counties.sql", "003_nass_cattle.sql", "004_cattle_views.sql",
                     "005_fsis_facilities.sql", "006_county_facility_metrics.sql",
                     "007_published_distance_rule.sql"):
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
        """SELECT nearest_cattle_km, cattle_within_10km, cattle_within_25km,
                  nearest_dairy_cow_km, dairy_cow_within_25km
           FROM county_facility_metrics WHERE geoid = %s""",
        (geoid,),
    ).fetchone()


def test_nearest_cattle_distance_is_about_10_km(db):
    nearest, *_ = metrics(db, "48001")
    assert 9.9 < nearest < 10.1


def test_radius_counts(db):
    _, within10, within25, _, _ = metrics(db, "48001")
    assert within10 == 1          # P1 only
    assert within25 == 2          # P1 and P3; P2 at ~27.8 km is outside


def test_dairy_cow_distance_and_count(db):
    _, _, _, nearest_dairy, dairy25 = metrics(db, "48001")
    assert 19.9 < nearest_dairy < 20.1   # P3, the only dairy cow plant
    assert dairy25 == 1


def test_every_county_has_a_row(db):
    n = db.execute("SELECT count(*) FROM county_facility_metrics").fetchone()[0]
    assert n == 3


def test_county_with_no_facilities_in_radius_gets_zero_counts(db):
    # County 48005 (synthetic, east) is about 100 km from the facilities: counts are 0, not NULL.
    _, within10, within25, _, dairy25 = metrics(db, "48005")
    assert (within10, within25, dairy25) == (0, 0, 0)


def test_published_view_withholds_counts_1_to_4(db):
    row = db.execute(
        """SELECT cattle_within_10km, cattle_within_25km, dairy_cow_within_25km
           FROM county_facility_published WHERE geoid = '48001'"""
    ).fetchone()
    # 10 km count is 1 (withheld); 25 km cattle count is 2 (withheld); dairy 25 km is 1 (withheld).
    assert row == (None, None, None)


def test_published_view_withholds_nearest_distance_with_small_counts(db):
    """Option 1: nearest distance is withheld when the same type's 25 km count is 1 to 4."""
    row = db.execute(
        """SELECT nearest_cattle_km, nearest_dairy_cow_km
           FROM county_facility_published WHERE geoid = '48001'"""
    ).fetchone()
    assert row == (None, None)


def test_published_view_keeps_distance_when_no_plants_in_radius(db):
    """County 48005 has 0 plants within 25 km, so its nearest distance does not locate a plant inside the radius."""
    row = db.execute(
        """SELECT nearest_cattle_km FROM county_facility_published WHERE geoid = '48005'"""
    ).fetchone()
    assert row[0] is not None and row[0] > 25


def test_published_view_keeps_zero(db):
    row = db.execute(
        """SELECT cattle_within_10km FROM county_facility_published WHERE geoid = '48005'"""
    ).fetchone()
    assert row == (0,)
