"""Tests for county clustering using SYNTHETIC counties and SYNTHETIC facilities.

Synthetic counties 48001 and 48003 share an edge, so they cluster at any eps. Tests
raise or lower eps in miles to exercise the threshold. Facilities are placed relative
to those points (1 degree of latitude is about 111 km).
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

# (id, lat, lon, cattle). Synthetic plants placed inside 48001 and 48003 (distance 0 from boundary).
FACILITIES = [
    ("P1", 30.5 + 0.0899, -97.5, True),   # inside 48001
    ("P3", 30.5 + 0.18,   -97.5, True),   # inside 48001
    ("P4", 30.5 + 0.10,   -96.5, True),   # inside 48003
    ("P5", 30.5 - 0.10,   -96.5, True),   # inside 48003
    ("P6", 30.5 + 0.20,   -96.5, True),   # inside 48003
]


@pytest.fixture(scope="module")
def db():
    county_zip = build_county_fixture()
    with psycopg.connect(TEST_DSN, autocommit=True) as conn:
        conn.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
        conn.execute("CREATE EXTENSION postgis;")
        for name in ("002_counties.sql", "003_nass_cattle.sql", "004_cattle_views.sql",
                     "005_fsis_facilities.sql", "006_county_facility_metrics.sql",
                     "007_published_distance_rule.sql", "008_county_clusters.sql",
                     "009_county_summary.sql", "010_show_small_counts.sql",
                     "011_boundary_distance.sql", "012_miles.sql"):
            conn.execute((MIGRATIONS / name).read_text())
    lcty.load(lcty.read_texas_counties(county_zip), TEST_DSN)
    with psycopg.connect(TEST_DSN, autocommit=True) as conn:
        for est_id, lat, lon, cattle in FACILITIES:
            conn.execute(
                """INSERT INTO fsis_establishment
                   (establishment_id, establishment_number, name, geom, cattle_slaughter,
                    dairy_cow_slaughter)
                   VALUES (%s, %s, %s, ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography,
                           %s, false)""",
                (est_id, "E" + est_id, "SYNTH " + est_id, lon, lat, cattle),
            )
    with psycopg.connect(TEST_DSN, autocommit=True) as conn:
        yield conn


def set_param(conn, name, value):
    conn.execute("UPDATE cluster_params SET value = %s WHERE name = %s", (value, name))


def reset_params(conn):
    set_param(conn, "eps_mi", 31)
    set_param(conn, "min_counties", 2)
    set_param(conn, "min_facilities_published", 5)


def test_counties_sharing_an_edge_cluster_at_default_eps(db):
    """Boundary distance: 48001 and 48003 share an edge, so their distance is 0."""
    reset_params(db)
    rows = dict(db.execute(
        "SELECT geoid, cluster_id FROM county_cluster_assignment").fetchall())
    assert rows["48001"] is not None and rows["48001"] == rows["48003"]


def test_touching_counties_cluster_even_at_small_eps(db):
    """Polygon distance 0 (shared edge) is within any positive eps."""
    set_param(db, "eps_mi", 1)
    try:
        rows = dict(db.execute(
            "SELECT geoid, cluster_id FROM county_cluster_assignment").fetchall())
        assert rows["48001"] is not None and rows["48001"] == rows["48003"]
    finally:
        reset_params(db)


def test_nearby_counties_cluster_together_and_publish(db):
    set_param(db, "eps_mi", 93)
    try:
        rows = dict(db.execute(
            "SELECT geoid, cluster_id FROM county_cluster_assignment").fetchall())
        assert rows["48001"] is not None and rows["48001"] == rows["48003"]

        pub = dict(db.execute(
            "SELECT geoid, cluster_id FROM county_cluster_published").fetchall())
        assert pub == {"48001": rows["48001"], "48003": rows["48001"]}

        n_counties, n_fac = db.execute(
            "SELECT n_counties, n_facilities FROM county_cluster_summary").fetchone()
        assert (n_counties, n_fac) == (2, 5)   # P1, P3, P4, P5, P6 (P2 not in data)
    finally:
        reset_params(db)


def test_cluster_withheld_below_facility_threshold(db):
    set_param(db, "eps_mi", 93)
    set_param(db, "min_facilities_published", 10)
    try:
        assert db.execute("SELECT count(*) FROM county_cluster_published").fetchone()[0] == 0
        assert db.execute("SELECT count(*) FROM county_cluster_summary").fetchone()[0] == 0
        # The unsuppressed working view still shows the cluster for staging use.
        assert db.execute(
            "SELECT count(*) FROM county_cluster_assignment WHERE cluster_id IS NOT NULL"
        ).fetchone()[0] == 2
    finally:
        reset_params(db)


def test_published_clusters_meet_threshold(db):
    set_param(db, "eps_mi", 93)
    try:
        bad = db.execute(
            """SELECT count(*) FROM county_cluster_summary
               WHERE n_facilities < (SELECT value FROM cluster_params
                                     WHERE name = 'min_facilities_published')"""
        ).fetchone()[0]
        assert bad == 0
    finally:
        reset_params(db)
