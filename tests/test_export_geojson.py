"""Tests for the GeoJSON export, using SYNTHETIC counties and facilities.

Checks that the export contains only published fields, no facility points,
and nulls wherever a value is withheld.
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

import export_geojson as eg  # noqa: E402
import load_counties as lcty  # noqa: E402
from make_fixture import build as build_county_fixture  # noqa: E402
from test_county_summary import MIGRATION_ORDER, MIGRATIONS  # noqa: E402

TEST_DSN = os.environ.get(
    "TEST_DATABASE_URL", "postgresql://txcattle:txcattle@localhost:5432/txcattle_test"
)


@pytest.fixture(scope="module")
def exported(tmp_path_factory):
    county_zip = build_county_fixture()
    with psycopg.connect(TEST_DSN, autocommit=True) as conn:
        conn.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
        conn.execute("CREATE EXTENSION postgis;")
        for name in MIGRATION_ORDER:
            conn.execute((MIGRATIONS / name).read_text())
    lcty.load(lcty.read_texas_counties(county_zip), TEST_DSN)
    with psycopg.connect(TEST_DSN, autocommit=True) as conn:
        conn.execute(
            """INSERT INTO fsis_establishment
               (establishment_id, establishment_number, name, geom, cattle_slaughter, dairy_cow_slaughter)
               VALUES ('P1', 'EP1', 'SYNTH P1',
                       ST_SetSRID(ST_MakePoint(-97.5, 30.5899), 4326)::geography, true, false)"""
        )
    out = tmp_path_factory.mktemp("geo") / "counties.geojson"
    eg.export(TEST_DSN, out)
    return json.loads(out.read_text())


ALLOWED = set(eg.PROPERTIES)


def test_feature_collection_with_one_feature_per_county(exported):
    assert exported["type"] == "FeatureCollection"
    ids = [f["properties"]["geoid"] for f in exported["features"]]
    assert sorted(ids) == ["48001", "48003", "48005"]


def test_only_published_properties_are_exported(exported):
    for f in exported["features"]:
        assert set(f["properties"]) == ALLOWED


def test_no_point_geometries(exported):
    types = {f["geometry"]["type"] for f in exported["features"]}
    assert types <= {"Polygon", "MultiPolygon"}


def test_coordinates_are_lon_lat(exported):
    for f in exported["features"]:
        coords = f["geometry"]["coordinates"]
        flat = [p for poly in coords for ring in poly for p in ring]
        lons = [p[0] for p in flat]
        lats = [p[1] for p in flat]
        assert all(-106.7 <= x <= -93.5 for x in lons)
        assert all(25.8 <= y <= 36.6 for y in lats)


def test_small_counts_are_shown_and_flagged(exported):
    props = {f["properties"]["geoid"]: f["properties"] for f in exported["features"]}
    # 48001 has one plant inside it in this fixture: shown as 1, flagged as a small count.
    assert props["48001"]["cattle_within_25mi"] == 1
    assert props["48001"]["cattle_25mi_small_count"] is True
    assert props["48001"]["nearest_cattle_mi"] is not None
    # 48005 has no plant within 25 miles: zero, not flagged.
    assert props["48005"]["cattle_within_25mi"] == 0
    assert props["48005"]["cattle_25mi_small_count"] is False


def test_metadata_marks_descriptive_and_withheld(exported):
    meta = exported["metadata"]
    assert meta["descriptive_only"] is True
    assert "NASS" in meta["withheld"]
    assert "flagged" in meta["small_count"]
