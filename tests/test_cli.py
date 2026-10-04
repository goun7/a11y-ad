"""CLI tests: exit codes, JSON payload, directory scanning."""

import json
from pathlib import Path

import pytest

from a11y_ad.cli import main

FIXTURES = Path(__file__).parent / "fixtures"


def test_clean_file_exits_zero(capsys):
    assert main([str(FIXTURES / "good.html")]) == 0
    out = capsys.readouterr().out
    assert "0 without accessible name" in out


def test_dirty_file_exits_one(capsys):
    assert main([str(FIXTURES / "bad.html")]) == 1
    out = capsys.readouterr().out
    assert "MISSING" in out


def test_directory_scan_and_json(capsys):
    rc = main([str(FIXTURES), "--json"])
    payload = json.loads(capsys.readouterr().out)
    names = {Path(p["target"]).name for p in payload}
    assert names == {"good.html", "bad.html"}
    bad = next(p for p in payload if p["target"].endswith("bad.html"))
    assert bad["ok"] is False and bad["total"] == 3 and len(bad["missing"]) == 2
    good = next(p for p in payload if p["target"].endswith("good.html"))
    assert good["ok"] is True
    assert rc == 1  # one of the files is dirty


def test_missing_file_is_error(capsys):
    assert main(["/nonexistent/x.html"]) == 1
    assert "error" in capsys.readouterr().err


@pytest.mark.parametrize("fixture", ["good.html", "bad.html"])
def test_fixture_files_exist(fixture):
    assert (FIXTURES / fixture).is_file()
