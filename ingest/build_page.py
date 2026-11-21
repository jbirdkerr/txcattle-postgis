"""Build the public site: report, run summary, and map, as static files in site/.

Inputs:
    REPORT.md                 written by make_report.py
    build/manifest.json       written by run_pipeline.py
    map/index.html, map/data  the static map and its GeoJSON

Output:
    site/index.html           report and run summary in <details> sections
    site/map/                 the map, copied as-is

Only fields from the manifest are shown, so no commands, arguments, or environment
values appear on the page.
"""

from __future__ import annotations

import html
import json
import shutil
import sys
from pathlib import Path

import markdown

ROOT = Path(__file__).resolve().parent.parent
REPORT = ROOT / "REPORT.md"
MANIFEST = ROOT / "build" / "manifest.json"
MAP_SRC = ROOT / "map"
SITE = ROOT / "site"

STYLE = """
body { margin: 0; font-family: system-ui, sans-serif; color: #1a1a1a; background: #fff; }
main { max-width: 56rem; margin: 0 auto; padding: 1.5rem 1rem 4rem; }
h1 { font-size: 1.6rem; margin-bottom: .25rem; }
.lede { color: #555; margin-top: 0; }
.map-frame { width: 100%; height: 70vh; border: 1px solid #ddd; border-radius: 6px; }
details.section { border: 1px solid #ddd; border-radius: 6px; margin: 1rem 0; padding: .75rem 1rem; }
details.section > summary { cursor: pointer; font-weight: 600; font-size: 1.1rem; }
details.section[open] > summary { margin-bottom: .75rem; }
table { border-collapse: collapse; width: 100%; font-size: .9rem; margin: .75rem 0; }
th, td { border-bottom: 1px solid #eee; padding: .35rem .5rem; text-align: left; vertical-align: top; }
th { background: #fafafa; }
code { font-size: .85em; background: #f5f5f5; padding: .05rem .3rem; border-radius: 3px; }
.meta { color: #666; font-size: .85rem; }
.status-ok { color: #2a7a4b; }
.status-error { color: #b00020; font-weight: 600; }
.status-skipped { color: #888; }
"""


def render_steps(manifest: dict) -> str:
    rows = []
    for i, step in enumerate(manifest["steps"], 1):
        ms = step["duration_ms"]
        duration = "-" if ms is None else f"{ms / 1000:.1f} s"
        outputs = "".join(
            f"<div><code>{html.escape(o['file'])}</code> "
            + (f"<span class='meta'>sha256 {html.escape(o['sha256'][:16])}&hellip; "
               f"({o['bytes']:,} bytes)</span>" if o["sha256"] else "<span class='meta'>not produced</span>")
            + "</div>"
            for o in step["outputs"]
        ) or "<span class='meta'>&mdash;</span>"
        rows.append(
            f"<tr><td>{i}</td>"
            f"<td><strong>{html.escape(step['title'])}</strong><br>"
            f"<span class='meta'>{html.escape(step['description'])}</span></td>"
            f"<td class='status-{html.escape(step['status'])}'>{html.escape(step['status'])}</td>"
            f"<td>{duration}</td>"
            f"<td>{outputs}</td></tr>"
        )
    ok_count = sum(1 for s in manifest["steps"] if s["status"] == "ok")
    return f"""
<table>
  <thead><tr><th>#</th><th>Step</th><th>Status</th><th>Time</th><th>Outputs</th></tr></thead>
  <tbody>{"".join(rows)}</tbody>
</table>
<p class="meta">{ok_count} of {len(manifest["steps"])} steps completed.
Build <code>{html.escape(manifest["build_id"])}</code> from commit
<code>{html.escape(manifest["git_commit"])}</code>, started {html.escape(manifest["started_at"])}.</p>"""


def render_page(report_md: str, manifest: dict) -> str:
    report_html = markdown.markdown(report_md, extensions=["tables"])
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Texas cattle slaughter capacity by county</title>
<link rel="icon" href="favicon.ico">
<style>{STYLE}</style>
</head>
<body>
<main>
  <h1>Texas cattle slaughter capacity by county</h1>
  <p class="lede">Descriptive only. This shows where reported cattle and cattle slaughter
  plants are located, by county. It does not show causes, attribute disease to any
  facility, or identify outbreak zones.</p>

  <h2>Map</h2>
  <iframe class="map-frame" src="map/index.html" title="Texas county map"></iframe>

  <details class="section" name="page-sections" open>
    <summary>Report: what the data shows</summary>
    {report_html}
  </details>

  <details class="section" name="page-sections">
    <summary>How this was built: pipeline run summary</summary>
    {render_steps(manifest)}
  </details>
</main>
</body>
</html>
"""


def main() -> None:
    for required in (REPORT, MANIFEST):
        if not required.exists():
            sys.exit(f"missing {required.relative_to(ROOT)}; run the earlier pipeline steps first")
    manifest = json.loads(MANIFEST.read_text())
    report_md = REPORT.read_text()

    if SITE.exists():
        shutil.rmtree(SITE)
    (SITE / "map").mkdir(parents=True)
    shutil.copy(MAP_SRC / "index.html", SITE / "map" / "index.html")
    shutil.copytree(MAP_SRC / "data", SITE / "map" / "data")
    for dest in (SITE, SITE / "map"):
        shutil.copy(MAP_SRC / "favicon.ico", dest / "favicon.ico")
    (SITE / ".nojekyll").touch()  # serve files exactly as built on GitHub Pages
    (SITE / "index.html").write_text(render_page(report_md, manifest))
    print(f"wrote   {(SITE / 'index.html').relative_to(ROOT)}")


if __name__ == "__main__":
    main()
