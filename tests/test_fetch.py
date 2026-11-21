"""Tests for the FSIS fetch rules. No network or database needed; files are synthetic."""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "ingest"))

import fetch  # noqa: E402

ENV_VARS = [v for spec in fetch.FSIS_FILES.values() for v in spec[:2]]


@pytest.fixture
def raw_dir(tmp_path, monkeypatch):
    raw = tmp_path / "data" / "raw"
    monkeypatch.setattr(fetch, "ROOT", tmp_path)
    monkeypatch.setattr(fetch, "RAW_DIR", raw)
    for var in ENV_VARS:
        monkeypatch.delenv(var, raising=False)

    def no_network(*args, **kwargs):
        raise AssertionError("network used")

    monkeypatch.setattr(fetch.requests, "get", no_network)
    return raw


def _write_all(raw: Path) -> dict[str, str]:
    raw.mkdir(parents=True, exist_ok=True)
    digests = {}
    for label, (_, _, filename) in fetch.FSIS_FILES.items():
        data = f"synthetic {label}\n".encode()
        (raw / filename).write_bytes(data)
        digests[label] = hashlib.sha256(data).hexdigest()
    return digests


def test_existing_files_are_kept_without_urls(raw_dir):
    _write_all(raw_dir)
    paths = fetch.fetch_fsis()
    assert [p.name for p in paths] == [spec[2] for spec in fetch.FSIS_FILES.values()]


def test_existing_files_pass_matching_checksums(raw_dir, monkeypatch):
    digests = _write_all(raw_dir)
    for label, (_, sha_var, _) in fetch.FSIS_FILES.items():
        monkeypatch.setenv(sha_var, digests[label].upper())
    assert len(fetch.fetch_fsis()) == 2


def test_existing_file_with_wrong_checksum_stops_but_is_kept(raw_dir, monkeypatch):
    _write_all(raw_dir)
    _, sha_var, filename = fetch.FSIS_FILES["directory"]
    monkeypatch.setenv(sha_var, "0" * 64)
    with pytest.raises(SystemExit, match="does not match"):
        fetch.fetch_fsis()
    assert (raw_dir / filename).exists()


def test_missing_file_without_url_stops(raw_dir):
    with pytest.raises(SystemExit, match="is not set"):
        fetch.fetch_fsis()


def test_fresh_download_with_wrong_checksum_is_deleted(raw_dir, monkeypatch):
    class Resp:
        content = b"unexpected version\n"

        def raise_for_status(self):
            pass

    monkeypatch.setattr(fetch.requests, "get", lambda *a, **k: Resp())
    url_var, sha_var, filename = fetch.FSIS_FILES["directory"]
    monkeypatch.setenv(url_var, "https://example.invalid/directory.csv")
    monkeypatch.setenv(sha_var, "0" * 64)
    with pytest.raises(SystemExit, match="does not match"):
        fetch.fetch_fsis()
    assert not (raw_dir / filename).exists()
