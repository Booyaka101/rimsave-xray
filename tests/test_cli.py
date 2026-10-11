"""The CLI end to end: --json schema, error messages, the worked example's budget."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from rimsavexray.cli import main

from builders import build_save, map_block, thing_block
from conftest import FIXTURES


def test_json_schema_and_numbers(demosave1, tmp_path, capsys):
    report = tmp_path / "report.html"
    code = main([str(demosave1), "--json", "--out", str(report)])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["rimsavexray"] == "1.0.0"
    scan = payload["scan"]
    assert scan["gameVersion"] == "1.3.3200 rev726"
    assert scan["ticksGame"] == "41164371"   # tickManager's own, not per-pawn copies
    assert len(scan["mods"]) == 135
    assert scan["sections"]["world"] == 10630036
    assert scan["worldPawns"]["alive"] == 29
    assert scan["worldPawns"]["dead"] == 97
    assert scan["defBytes"]["Human"] == 1589091
    assert scan["readOnlyOk"] is True
    assert scan["sha256Before"] == scan["sha256After"]

    # the same numbers the HTML shows
    html = report.read_text(encoding="utf-8")
    assert "1,589,091" in html          # Human bytes, thousands-separated
    assert "world" in html
    assert payload["findings"], "the fixture fires at least one rule"


def test_json_and_html_agree_on_the_big_numbers(demosave1, tmp_path, capsys):
    report = tmp_path / "r.html"
    main([str(demosave1), "--json", "--out", str(report)])
    payload = json.loads(capsys.readouterr().out)
    html = report.read_text(encoding="utf-8")
    for number in (payload["scan"]["sections"]["world"],
                   payload["scan"]["sections"]["maps"]):
        assert f"{number:,}" in html


def test_worked_example_under_5s(demosave1, tmp_path):
    """The brief's worked example: a full run on demosave 1 finishes under 5 s."""
    started = time.perf_counter()
    code = main([str(demosave1), "--out", str(tmp_path / "report.html")])
    elapsed = time.perf_counter() - started
    assert code == 0
    assert elapsed < 5.0, f"took {elapsed:.2f}s"
    assert (tmp_path / "report.html").stat().st_size > 5000


def test_summary_output(demosave1, tmp_path, capsys):
    code = main([str(demosave1), "--out", str(tmp_path / "report.html")])
    out = capsys.readouterr().out
    assert code == 0
    assert "file size" in out and "gameVersion" in out
    assert "world pawns 126 tracked" in out
    assert "read-only" in out


def test_missing_file_is_a_message_not_a_traceback(capsys):
    code = main([r"Z:\nowhere\nope.rws"])
    err = capsys.readouterr().err
    assert code == 2
    assert "rimsavexray:" in err
    assert "no such file" in err
    assert "Traceback" not in err


def test_unknown_save_name_lists_alternatives(capsys, monkeypatch, tmp_path):
    (tmp_path / "Real.rws").write_text("<savegame/>", encoding="utf-8")
    monkeypatch.setattr("rimsavexray.discover.saves_dir", lambda: tmp_path)
    monkeypatch.chdir(tmp_path)
    code = main(["Dream"])
    err = capsys.readouterr().err
    assert code == 2
    assert "no save named 'Dream'" in err
    assert "Real" in err


def test_out_none_skips_report(demosave1, tmp_path, capsys, monkeypatch):
    monkeypatch.chdir(tmp_path)
    code = main([str(demosave1), "--out", "none"])
    out = capsys.readouterr().out
    assert code == 0
    assert "report" not in out
    assert not list(tmp_path.glob("*.html"))


def test_version_flag(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    assert "rimsavexray 1.0.0" in capsys.readouterr().out


def test_default_report_written_to_cwd(demosave1, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    code = main([str(demosave1)])
    assert code == 0
    assert (tmp_path / "rimsavexray-report.html").is_file()


def test_interactive_prompt_lists_saves_and_scans(monkeypatch, tmp_path, capsys):
    """The double-clicked exe path: no argument, a tty, and a typed number."""
    save = tmp_path / "Colony.rws"
    save.write_text(build_save(maps_xml=map_block(0, thing_block("Wall"))), encoding="utf-8")
    monkeypatch.setattr("rimsavexray.discover.saves_dir", lambda: tmp_path)
    monkeypatch.setattr("rimsavexray.cli.saves_dir", lambda: tmp_path)
    monkeypatch.setattr("sys.stdin", type("FakeStdin", (), {"isatty": lambda self: True})())
    answers = iter(["1"])
    monkeypatch.setattr("builtins.input", lambda _prompt: next(answers))
    monkeypatch.chdir(tmp_path)
    code = main([])
    out = capsys.readouterr().out
    assert code == 0
    assert "Colony.rws" in out
    assert "read-only" in out
    assert (tmp_path / "rimsavexray-report.html").is_file()


def test_interactive_prompt_rejects_then_accepts(monkeypatch, tmp_path, capsys):
    save = tmp_path / "Colony.rws"
    save.write_text(build_save(), encoding="utf-8")
    monkeypatch.setattr("rimsavexray.cli.saves_dir", lambda: tmp_path)
    monkeypatch.setattr("sys.stdin", type("FakeStdin", (), {"isatty": lambda self: True})())
    answers = iter(["not a save", "1"])
    monkeypatch.setattr("builtins.input", lambda _prompt: next(answers))
    monkeypatch.chdir(tmp_path)
    code = main([])
    out = capsys.readouterr().out
    assert code == 0
    assert "Try again." in out


def test_fixture_present():
    assert (FIXTURES / "demosave 1.rws.gz").stat().st_size == 2908452
