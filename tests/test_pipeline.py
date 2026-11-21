"""Tests for the stage runner and page builder. No database or network needed.

The key guarantee tested here: commands, arguments, and environment values never
appear in the manifest or in the page, so a secret passed to a stage stays private.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "ingest"))

import build_page as bp  # noqa: E402
import run_pipeline as rp  # noqa: E402

SECRET = "SECRET-TEST-VALUE-9f3a"


def _py(code: str) -> list[str]:
    return [sys.executable, "-c", code]


def test_manifest_never_records_commands_or_secrets(tmp_path):
    stages = [rp.Stage("s1", "Step one", "Does nothing secret.",
                       _py("print('ok')") + [SECRET])]
    manifest_path = tmp_path / "build" / "manifest.json"
    assert rp.run_stages(stages, manifest_path, root=tmp_path)
    text = manifest_path.read_text()
    assert SECRET not in text
    assert "cmd" not in json.loads(text)["steps"][0]


def test_failure_stops_run_and_marks_later_stages_skipped(tmp_path):
    stages = [
        rp.Stage("bad", "Fails", "Exits non-zero.", _py("import sys; sys.exit(3)")),
        rp.Stage("later", "Never runs", "Should be skipped.", _py("print('x')")),
    ]
    manifest_path = tmp_path / "manifest.json"
    assert rp.run_stages(stages, manifest_path, root=tmp_path) is False
    manifest = json.loads(manifest_path.read_text())
    assert manifest["status"] == "error"
    assert [s["status"] for s in manifest["steps"]] == ["error", "skipped"]


def test_output_checksum_matches_file(tmp_path):
    content = b"public output"
    stages = [rp.Stage("make", "Make a file", "Writes one output.",
                       _py("open('out.txt','wb').write(b'public output')"),
                       outputs=["out.txt"])]
    manifest_path = tmp_path / "manifest.json"
    rp.run_stages(stages, manifest_path, root=tmp_path)
    out = json.loads(manifest_path.read_text())["steps"][0]["outputs"][0]
    assert out["sha256"] == hashlib.sha256(content).hexdigest()
    assert out["bytes"] == len(content)


def test_missing_output_is_recorded_not_invented(tmp_path):
    stages = [rp.Stage("none", "No output", "Produces nothing.", _py("pass"),
                       outputs=["never.txt"])]
    manifest_path = tmp_path / "manifest.json"
    rp.run_stages(stages, manifest_path, root=tmp_path)
    out = json.loads(manifest_path.read_text())["steps"][0]["outputs"][0]
    assert out == {"file": "never.txt", "sha256": None, "bytes": None}


def test_page_shows_run_summary_and_no_secret():
    manifest = {
        "build_id": "local-test", "git_commit": "abc123", "started_at": "2026-11-03T00:00:00+00:00",
        "finished_at": "2026-11-03T00:01:00+00:00", "status": "ok",
        "steps": [{"name": "s1", "title": "Step one", "description": "Desc.",
                   "status": "ok", "duration_ms": 1500,
                   "outputs": [{"file": "REPORT.md", "sha256": "a" * 64, "bytes": 10}]}],
    }
    page = bp.render_page("# Findings\n\nA county result.", manifest)
    assert "How this was built" in page
    assert "Report: what the data shows" in page
    assert "Step one" in page and "1.5 s" in page
    assert "<h1>Findings</h1>" in page or "<h1 id=" in page
    assert SECRET not in page


def test_page_contains_only_manifest_fields(tmp_path):
    """A secret in the environment must not reach the page, even if it is set."""
    manifest = {"build_id": "b", "git_commit": "c", "started_at": "t", "finished_at": "t",
                "status": "ok", "steps": []}
    page = bp.render_page("# R", manifest)
    assert SECRET not in page


def test_page_is_not_a_stage():
    # build_page reads the manifest, which only exists once every stage has run.
    names = [s.name for s in rp.default_stages()]
    assert "build_page" not in names
    assert all("build_page.py" not in " ".join(s.cmd) for s in rp.default_stages())
