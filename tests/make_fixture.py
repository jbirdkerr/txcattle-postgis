"""Generate a SYNTHETIC county shapefile for testing the loader.

THIS IS NOT REAL DATA. It contains invented square 'counties' with made-up
attributes, plus one self-intersecting polygon to exercise geometry repair,
plus one Oklahoma record to exercise the Texas filter. It is used only by
tests and is never loaded into the app database.

Usage:
    uv run tests/make_fixture.py   # writes tests/fixtures/SYNTHETIC_counties.zip
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import shapefile

OUT = Path(__file__).resolve().parent / "fixtures" / "SYNTHETIC_counties.zip"

# (STATEFP, COUNTYFP, GEOID, NAME, NAMELSAD, ring (lon, lat), label)
RECORDS = [
    ("48", "001", "48001", "SynthA", "SynthA County",
     [(-98.0, 30.0), (-97.0, 30.0), (-97.0, 31.0), (-98.0, 31.0), (-98.0, 30.0)]),
    ("48", "003", "48003", "SynthB", "SynthB County",
     [(-97.0, 30.0), (-96.0, 30.0), (-96.0, 31.0), (-97.0, 31.0), (-97.0, 30.0)]),
    # Bowtie: self-intersecting, invalid until repaired.
    ("48", "005", "48005", "SynthC", "SynthC County",
     [(-96.0, 30.0), (-95.0, 31.0), (-95.0, 30.0), (-96.0, 31.0), (-96.0, 30.0)]),
    # Oklahoma (FIPS 40): must be excluded by the Texas filter.
    ("40", "001", "40001", "SynthOK", "SynthOK County",
     [(-99.0, 35.0), (-98.0, 35.0), (-98.0, 36.0), (-99.0, 36.0), (-99.0, 35.0)]),
]


def build() -> Path:
    buf = {k: io.BytesIO() for k in ("shp", "shx", "dbf")}
    w = shapefile.Writer(shp=buf["shp"], shx=buf["shx"], dbf=buf["dbf"],
                         shapeType=shapefile.POLYGON)
    for name, field_len in [("STATEFP", 2), ("COUNTYFP", 3), ("GEOID", 5),
                            ("NAME", 20), ("NAMELSAD", 30)]:
        w.field(name, "C", size=field_len)
    w.field("ALAND", "N", size=14)
    w.field("AWATER", "N", size=14)
    w.field("INTPTLAT", "C", size=12)
    w.field("INTPTLON", "C", size=13)

    for statefp, countyfp, geoid, name, namelsad, ring in RECORDS:
        w.poly([ring])
        cx = sum(x for x, _ in ring[:-1]) / 4
        cy = sum(y for _, y in ring[:-1]) / 4
        w.record(statefp, countyfp, geoid, name, namelsad,
                 1000000, 0, f"{cy:+.7f}", f"{cx:+.7f}")
    w.close()

    OUT.parent.mkdir(parents=True, exist_ok=True)
    stem = "SYNTHETIC_counties"
    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as zf:
        for ext, key in (("shp", "shp"), ("shx", "shx"), ("dbf", "dbf")):
            zf.writestr(f"{stem}.{ext}", buf[key].getvalue())
    print(f"wrote   {OUT} (SYNTHETIC, for tests only)")
    return OUT


if __name__ == "__main__":
    build()
