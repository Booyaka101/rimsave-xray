"""The CLI end to end: --json schema, error messages, the worked example's budget."""

from __future__ import annotations

import gzip
import json
import time
from pathlib import Path

import pytest

from rimsavexray.cli import main
from rimsavexray import __version__

from builders import build_save, map_block, thing_block
from conftest import FIXTURES


def test_json_schema_and_numbers(demosave1, tmp_path, capsys):
    report = tmp_path / "report.html"
    code = main([str(demosave1), "--json", "--out", str(report)])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["rimsavexray"] == __version__
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


def test_missing_file_is_a_message_not_a_traceback(tmp_path, capsys):
    code = main([str(tmp_path / "definitely" / "missing.rws")])
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
    from rimsavexray import __version__
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    assert f"rimsavexray {__version__}" in capsys.readouterr().out


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
    monkeypatch.setattr("rimsavexray.cli._pause_if_double_clicked", lambda raw: None)
    monkeypatch.chdir(tmp_path)
    code = main([])
    out = capsys.readouterr().out
    assert code == 0
    assert "Colony.rws" in out
    assert "read-only" in out
    assert (tmp_path / "rimsavexray-report.html").is_file()


def test_double_click_pauses_before_closing(monkeypatch, tmp_path, capsys):
    """A zero-argv launch with a tty holds the window open; with argv it exits."""
    save = tmp_path / "Colony.rws"
    save.write_text(build_save(), encoding="utf-8")
    monkeypatch.setattr("rimsavexray.cli.saves_dir", lambda: tmp_path)
    monkeypatch.setattr("rimsavexray.discover.saves_dir", lambda: tmp_path)
    monkeypatch.setattr("sys.stdin", type("FakeStdin", (), {"isatty": lambda self: True})())
    prompts = []
    monkeypatch.setattr("builtins.input", lambda prompt="": prompts.append(prompt) or "1")
    monkeypatch.chdir(tmp_path)
    assert main([]) == 0
    assert any("Press Enter to close" in p for p in prompts)


def test_no_pause_with_arguments(monkeypatch, tmp_path, capsys):
    save = tmp_path / "Colony.rws"
    save.write_text(build_save(), encoding="utf-8")
    monkeypatch.setattr("rimsavexray.cli.saves_dir", lambda: tmp_path)
    monkeypatch.setattr("sys.stdin", type("FakeStdin", (), {"isatty": lambda self: True})())
    calls = []
    monkeypatch.setattr("builtins.input", lambda prompt="": calls.append(prompt) or "1")
    code = main([str(save), "--out", "none"])
    assert code == 0
    assert calls == []  # argv present: no prompt, no pause


def test_interactive_prompt_rejects_then_accepts(monkeypatch, tmp_path, capsys):
    save = tmp_path / "Colony.rws"
    save.write_text(build_save(), encoding="utf-8")
    monkeypatch.setattr("rimsavexray.cli.saves_dir", lambda: tmp_path)
    monkeypatch.setattr("sys.stdin", type("FakeStdin", (), {"isatty": lambda self: True})())
    answers = iter(["not a save", "1"])
    monkeypatch.setattr("builtins.input", lambda _prompt: next(answers))
    monkeypatch.setattr("rimsavexray.cli._pause_if_double_clicked", lambda raw: None)
    monkeypatch.chdir(tmp_path)
    code = main([])
    out = capsys.readouterr().out
    assert code == 0
    assert "Try again." in out


def test_list_flag(monkeypatch, tmp_path, capsys):
    alpha = tmp_path / "Alpha.rws"
    alpha.write_text(build_save(), encoding="utf-8")
    beta = tmp_path / "Beta.rws.gz"
    beta.write_bytes(gzip.compress(build_save().encode()))
    monkeypatch.setattr("rimsavexray.cli.list_saves", lambda folder=None: [alpha, beta])
    code = main(["--list"])
    out = capsys.readouterr().out
    assert code == 0
    assert "Alpha.rws" in out and "Beta.rws.gz" in out


def test_summary_prints_top_mods(demosave1, tmp_path, capsys):
    """End-to-end plumbing only; the mods-bytes line itself is unit-tested
    against constructed attribution so it does not depend on a local
    RimWorld install."""
    code = main([str(demosave1), "--out", str(tmp_path / "r.html")])
    assert code == 0
    assert (tmp_path / "r.html").is_file()


def test_summary_names_top_mods_from_attribution():
    from rimsavexray.mods import Attribution, ModAttribution
    from rimsavexray.report import summary_lines
    from rimsavexray.scan import MapInfo, ScanResult

    result = ScanResult(path=Path("x.rws"), file_size=100, xml_bytes=100, compressed=False,
                        sha256_before="a", sha256_after="a", sections={"maps": 100},
                        maps=[MapInfo(0, 0, 100, things=1)])
    attribution = Attribution(mods=[
        ModAttribution("ludeon.rimworld", "Core", "0", True, bytes=90),
        ModAttribution("brrainz.harmony", "Harmony", "0", True, bytes=7),
    ])
    text = "\n".join(summary_lines(result, attribution, []))
    assert "mods by bytes Vanilla (Core) 90 B (90.0%), Harmony 7 B (7.0%)" in text
    assert "unattributed" not in text  # nothing unattributed: no noise line


def test_summary_names_unattributed_when_present():
    from rimsavexray.mods import Attribution, ModAttribution
    from rimsavexray.report import summary_lines
    from rimsavexray.scan import MapInfo, ScanResult

    result = ScanResult(path=Path("x.rws"), file_size=100, xml_bytes=100, compressed=False,
                        sha256_before="a", sha256_after="a", sections={"maps": 100},
                        maps=[MapInfo(0, 0, 100, things=1)])
    attribution = Attribution(mods=[ModAttribution("a.b", "A", "0", True, bytes=90)])
    attribution.unattributed_bytes = 10
    attribution.unattributed_defs = 3
    text = "\n".join(summary_lines(result, attribution, []))
    assert "unattributed 3 defs (10 B) no installed mod defines" in text


def test_fixture_present():
    assert (FIXTURES / "demosave 1.rws.gz").stat().st_size == 2908452
