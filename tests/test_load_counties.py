"""Loader tests using the SYNTHETIC fixture from make_fixture.py.

Runs against TEST_DATABASE_URL (default: a separate txcattle_test database)
so the development database is never touched.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import psycopg
import pytest
import shapely.wkt

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "ingest"))

import load_counties as lc  # noqa: E402
from make_fixture import build  # noqa: E402

TEST_DSN = os.environ.get(
    "TEST_DATABASE_URL", "postgresql://txcattle:txcattle@localhost:5432/txcattle_test"
)
MIGRATIONS = Path(__file__).resolve().parent.parent / "migrations"


@pytest.fixture(scope="module")
def fixture_zip() -> Path:
    return build()


@pytest.fixture(scope="module")
def loaded(fixture_zip: Path):
    """Reset the test schema and load the synthetic fixture once."""
    with psycopg.connect(TEST_DSN, autocommit=True) as conn:
        conn.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
        conn.execute("CREATE EXTENSION postgis;")
        conn.execute((MIGRATIONS / "002_counties.sql").read_text())
    rows = lc.read_texas_counties(fixture_zip)
    lc.load(rows, TEST_DSN)
    return rows


def test_filter_keeps_only_texas(loaded):
    geoids = {r["geoid"] for r in loaded}
    assert geoids == {"48001", "48003", "48005"}
    assert not any(g.startswith("40") for g in geoids)


def test_repaired_geometries_are_valid(loaded):
    for r in loaded:
        assert shapely.wkt.loads(r["wkt"]).is_valid, r["geoid"]


def test_validate_passes_on_expected_count(loaded):
    lc.validate(loaded, expected=3)


def test_validate_rejects_wrong_count(loaded):
    with pytest.raises(SystemExit):
        lc.validate(loaded)  # real Texas count is 254; fixture has 3


def test_database_rows_and_srid(loaded):
    with psycopg.connect(TEST_DSN) as conn:
        n, valid, srid = conn.execute(
            """SELECT count(*),
                      count(*) FILTER (WHERE ST_IsValid(geom)),
                      max(ST_SRID(geom))
               FROM tx_county"""
        ).fetchone()
    assert (n, valid, srid) == (3, 3, 4269)


def test_internal_points_fall_inside_their_county(loaded):
    """Census internal points must lie within the county polygon."""
    with psycopg.connect(TEST_DSN) as conn:
        bad = conn.execute(
            """SELECT count(*) FROM tx_county
               WHERE NOT ST_Covers(geom, ST_Transform(internal_pt::geometry, 4269))"""
        ).fetchone()[0]
    assert bad == 0
