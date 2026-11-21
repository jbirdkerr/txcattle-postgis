"""Tests for the slaughter-establishment history. SYNTHETIC files and rows only.

Covers the CBP reader (code systems, header quirks, legal-form filter), the check that
county rows sum to the state total, the NASS history reader, the published views, and
the map export.
"""

from __future__ import annotations

import io
import json
import os
import sys
import zipfile
from pathlib import Path

import psycopg
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "ingest"))

import export_history as eh  # noqa: E402
import fetch  # noqa: E402
import load_counties as lcty  # noqa: E402
import load_history as lh  # noqa: E402
from make_fixture import build as build_county_fixture  # noqa: E402

TEST_DSN = os.environ.get(
    "TEST_DATABASE_URL", "postgresql://txcattle:txcattle@localhost:5432/txcattle_test"
)
MIGRATIONS = ROOT / "migrations"


def _zip(path: Path, lines: list[str]) -> None:
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr(path.stem + ".txt", "\n".join(lines) + "\n")


def _county_zip(cbp_dir: Path, year: int, rows: list[tuple[str, str, int]]) -> None:
    col = "SIC" if year <= 1997 else "NAICS"
    lines = [f'"FIPSTATE","FIPSCTY","{col}","EST"']
    lines += [f'"{st}","{cty}","{code}",{est}' for st, cty, code, est in rows]
    _zip(cbp_dir / fetch.cbp_path(year, "co").name, lines)


def _state_zip(cbp_dir: Path, year: int, rows: list[tuple[str, str, str, int]]) -> None:
    col = "sic" if year <= 1997 else "naics"
    lines = [f"fipstate,{col},lfo,est"] + [f"{st},{code},{lfo},{est}" for st, code, lfo, est in rows]
    _zip(cbp_dir / fetch.cbp_path(year, "st").name, lines)


@pytest.fixture
def cbp_dir(tmp_path):
    d = tmp_path / "cbp"
    d.mkdir()
    # 1997: SIC 2011. 2 + 1 establishments; a NAICS-looking row and another state are ignored.
    _county_zip(d, 1997, [("48", "001", "2011", 2), ("48", "003", "2011", 1),
                          ("48", "005", "311611", 9), ("40", "001", "2011", 5)])
    _state_zip(d, 1997, [("48", "2011", "-", 3), ("48", "2011", "C", 2)])
    # 1998: NAICS 311611, one county with 5.
    _county_zip(d, 1998, [("48", "001", "311611", 5), ("48", "001", "2011", 7)])
    _state_zip(d, 1998, [("48", "311611", "-", 5)])
    # 1999: state only (county detail not used for this year).
    _state_zip(d, 1999, [("48", "311611", "-", 4)])
    return d


def test_code_system_switches_in_1998():
    assert lh.code_for(1997)[2] == "SIC 2011"
    assert lh.code_for(1998)[2] == "NAICS 311611"


def test_reader_keeps_texas_slaughter_rows_only(cbp_dir):
    rows = lh.read_cbp_zip(cbp_dir / "cbp97co.zip", 1997)
    assert rows == [{"est": 2, "fipscty": "001"}, {"est": 1, "fipscty": "003"}]


def test_state_reader_keeps_all_forms_row(cbp_dir):
    assert lh.read_cbp_zip(cbp_dir / "cbp97st.zip", 1997) == [{"est": 3}]


def test_county_rows_must_sum_to_state_total(cbp_dir):
    county, state = lh.read_cbp(cbp_dir, [1997, 1998], [1997, 1998, 1999])
    assert [(r["year"], r["geoid"], r["estab"], r["code_system"]) for r in county] == [
        (1997, "48001", 2, "SIC 2011"), (1997, "48003", 1, "SIC 2011"),
        (1998, "48001", 5, "NAICS 311611"),
    ]
    assert [s["estab"] for s in state] == [3, 5, 4]


def test_sum_mismatch_stops_the_load(cbp_dir):
    _state_zip(cbp_dir, 1998, [("48", "311611", "-", 6)])
    with pytest.raises(SystemExit, match="no longer holds"):
        lh.read_cbp(cbp_dir, [1998], [1998])


def test_statewide_unallocated_rows_stop_the_load(cbp_dir):
    _county_zip(cbp_dir, 1998, [("48", "001", "311611", 4), ("48", "999", "311611", 1)])
    with pytest.raises(SystemExit, match="statewide"):
        lh.read_cbp(cbp_dir, [1998], [1998])


def _nass(tmp_path) -> Path:
    def rec(level, county, year, value, period="FIRST OF JAN"):
        return {"agg_level_desc": level, "state_fips_code": "48", "county_code": county,
                "year": str(year), "Value": value, "reference_period_desc": period}
    data = [
        rec("COUNTY", "001", 1997, "1,000"), rec("COUNTY", "003", 1997, "(D)"),
        rec("COUNTY", "998", 1997, "50"),                    # combined counties: skipped
        rec("COUNTY", "001", 1998, "1,200"),
        rec("STATE", "", 1997, "30,000"), rec("STATE", "", 1997, "31,000", "FIRST OF JUL"),
        rec("STATE", "", 1998, "40,000"), rec("STATE", "", 1999, "36,000"),
    ]
    path = tmp_path / "nass.json"
    path.write_text(json.dumps({"data": data}))
    return path


def test_nass_history_reader(tmp_path):
    county, state = lh.read_nass_history(_nass(tmp_path), {"48001", "48003", "48005"})
    assert {(r["year"], r["geoid"]): (r["head"], r["suppression_code"]) for r in county} == {
        (1997, "48001"): (1000, None), (1997, "48003"): (None, "(D)"), (1998, "48001"): (1200, None),
    }
    assert state == [{"year": 1997, "head": 30000}, {"year": 1998, "head": 40000},
                     {"year": 1999, "head": 36000}]


@pytest.fixture(scope="module")
def db(tmp_path_factory):
    county_zip = build_county_fixture()
    with psycopg.connect(TEST_DSN, autocommit=True) as conn:
        conn.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
        conn.execute("CREATE EXTENSION postgis;")
        conn.execute((MIGRATIONS / "002_counties.sql").read_text())
        conn.execute((MIGRATIONS / "013_history.sql").read_text())
    lcty.load(lcty.read_texas_counties(county_zip), TEST_DSN)
    tmp = tmp_path_factory.mktemp("hist")
    d = tmp / "cbp"
    d.mkdir()
    _county_zip(d, 1997, [("48", "001", "2011", 2), ("48", "003", "2011", 1)])
    _state_zip(d, 1997, [("48", "2011", "-", 3)])
    _county_zip(d, 1998, [("48", "001", "311611", 5)])
    _state_zip(d, 1998, [("48", "311611", "-", 5)])
    _state_zip(d, 1999, [("48", "311611", "-", 4)])
    county_cbp, state_cbp = lh.read_cbp(d, [1997, 1998], [1997, 1998, 1999])
    # NASS county rows for 1997 only, so 1998 is a year with no county estimates.
    county_nass, state_nass = lh.read_nass_history(_nass(tmp), {"48001", "48003", "48005"})
    county_nass = [r for r in county_nass if r["year"] == 1997]
    lh.load(TEST_DSN, county_cbp, state_cbp, county_nass, state_nass)
    with psycopg.connect(TEST_DSN) as conn:
        yield conn


def _view(db, year):
    return {r[0]: r[1:] for r in db.execute(
        "SELECT geoid, slaughter_estab, estab_small_count, all_cattle_head, all_cattle_status "
        "FROM county_history_published WHERE year = %s", (year,))}


def test_every_county_every_year_and_no_row_is_zero(db):
    (n,) = db.execute("SELECT count(*) FROM county_history_published").fetchone()
    assert n == 3 * 2          # 3 synthetic counties x 2 county years
    assert _view(db, 1997)["48005"][:2] == (0, False)


def test_small_counts_flagged(db):
    v = _view(db, 1998)
    assert v["48001"][:2] == (5, False)
    assert _view(db, 1997)["48001"][:2] == (2, True)


def test_cattle_status(db):
    v97, v98 = _view(db, 1997), _view(db, 1998)
    assert v97["48001"][2:] == (1000, "published")
    assert v97["48003"][2:] == (None, "suppressed")
    assert v97["48005"][2:] == (None, "no row")
    assert v98["48001"][2:] == (None, "no county estimates")


def test_state_ratio(db):
    rows = db.execute("SELECT year, code_system, slaughter_estab, all_cattle_head, cattle_per_estab "
                      "FROM state_history_published ORDER BY year").fetchall()
    assert rows == [(1997, "SIC 2011", 3, 30000, 10000), (1998, "NAICS 311611", 5, 40000, 8000),
                    (1999, "NAICS 311611", 4, 36000, 9000)]


def test_export_shape(db, tmp_path):
    doc = eh.export(TEST_DSN, tmp_path / "history.json")
    assert doc["years"] == [1997, 1998]
    assert doc["no_county_cattle_years"] == [1998]
    assert doc["counties"]["48001"] == {"estab": [2, 5], "cattle": [1000, None]}
    assert [s["year"] for s in doc["state"]] == [1997, 1998, 1999]
    assert doc["metadata"]["descriptive_only"] is True
    # Only published fields: no raw suppression codes, no facility data.
    text = (tmp_path / "history.json").read_text()
    assert "(D)" not in text and "establishment_id" not in text
