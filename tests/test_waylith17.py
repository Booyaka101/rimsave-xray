"""RimWorld 1.7 (Waylith) save support, driven by the two real fixtures made
on this project's own machine from the unstable-branch install (build
1.7.4976 rev1043):

- waylith new colony: a fresh colony generated and saved in 1.7
- waylith migrated save: the owner's real 1.6.4850 save loaded into 1.7 and
  re-saved there (with two of its mods failing on 1.7, as players hit)

The structural finding these fixtures prove: 1.7 writes the same XML shape
as 1.6 (same root, same meta fields, the same 35 game sections, byte-level
conventions included). The scanner accepts them with no unmapped blocks.
"""

from __future__ import annotations

import json
from pathlib import Path

from rimsavexray.scan import sha256_of

from conftest import gunzip_to


def test_new_colony_scan(waylith_new_scan):
    r = waylith_new_scan
    assert r.game_version == "1.7.4976 rev1043"
    assert [m.package_id for m in r.mods] == [
        "ludeon.rimworld", "ludeon.rimworld.royalty", "ludeon.rimworld.ideology",
        "ludeon.rimworld.biotech", "ludeon.rimworld.anomaly", "ludeon.rimworld.odyssey",
        "xray.fixtures"]
    assert len(r.maps) == 1
    assert r.map_things == 41267
    assert r.world_pawns_total == 19
    # a real generated colony, not an empty shell
    assert r.map_things > 40000 and sum(r.def_counts.values()) > 40000


def test_new_colony_sections_partition_exactly(waylith_new_scan):
    r = waylith_new_scan
    assert sum(r.sections.values()) == r.xml_bytes == 19599794
    assert set(r.sections) == {"(xml header)", "meta", "game", "world", "maps",
                               "(after sections)"}


def test_migrated_save_scan(waylith_migrated_scan):
    r = waylith_migrated_scan
    assert r.game_version == "1.7.4976 rev1043"
    # the 1.6 original's game clock carried through the migration
    assert r.ticks_game == "660013"
    # the 1.6 loadout carried through, including the two mods that fail on 1.7
    assert [m.package_id for m in r.mods][:2] == ["brrainz.harmony", "ludeon.rimworld"]
    assert "booyaka101.convergence" in [m.package_id for m in r.mods]
    assert len(r.mods) == 9
    assert len(r.maps) == 1 and r.map_things == 21328
    assert sum(r.sections.values()) == r.xml_bytes == 11440957


def test_waylith_saves_have_no_unmapped_blocks(waylith_new_scan, waylith_migrated_scan):
    """The documented structural record: 1.7 added no save-format blocks the
    scanner's 1.3-1.6 vocabulary does not contain."""
    assert waylith_new_scan.unmapped_blocks == {}
    assert waylith_migrated_scan.unmapped_blocks == {}


def test_waylith_reads_are_read_only(waylith_new, waylith_migrated):
    for fixture in (waylith_new, waylith_migrated):
        before = sha256_of(fixture)
        from rimsavexray.scan import stream_scan
        result = stream_scan(fixture)
        assert sha256_of(fixture) == before == result.sha256_before == result.sha256_after
        assert result.read_only_ok


def test_waylith_plain_rws_equivalent(waylith_new, waylith_new_scan, tmp_path):
    plain = gunzip_to(waylith_new, tmp_path / "waylith new.rws")
    from rimsavexray.scan import stream_scan
    r = stream_scan(plain)
    assert r.compressed is False
    assert r.map_things == waylith_new_scan.map_things
    assert r.sections == waylith_new_scan.sections


def test_cli_full_run_on_waylith_new(waylith_new, tmp_path, capsys):
    from rimsavexray.cli import main
    report = tmp_path / "r.html"
    code = main([str(waylith_new), "--out", str(report)])
    out = capsys.readouterr().out
    assert code == 0
    assert "gameVersion 1.7.4976 rev1043" in out
    assert "unknown version" not in out.lower()
    assert "7 in the save's load order" in out
    assert "read-only" in out
    assert report.stat().st_size > 5000
    assert "not yet mapped" not in out          # nothing unmapped in these saves


def test_cli_json_on_waylith_migrated(waylith_migrated, tmp_path, capsys):
    from rimsavexray.cli import main
    code = main([str(waylith_migrated), "--json", "--out", str(tmp_path / "r.html")])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    scan = payload["scan"]
    assert scan["gameVersion"] == "1.7.4976 rev1043"
    assert scan["ticksGame"] == "660013"
    assert scan["unmappedBlocks"] == {}
    assert len(scan["mods"]) == 9
    assert scan["readOnlyOk"] is True


def test_html_report_on_waylith(waylith_new_scan, tmp_path):
    from rimsavexray.mods import attribute
    from rimsavexray.report import build_html
    from rimsavexray.rules import evaluate
    attribution = attribute(waylith_new_scan, None)
    html = build_html(waylith_new_scan, attribution, evaluate(waylith_new_scan, attribution))
    assert "Top 25 defs by bytes" in html
    assert "1.7.4976" in html
    assert "not yet mapped" not in html


def test_waylith_scans_are_deterministic(waylith_new, waylith_migrated):
    from rimsavexray.scan import stream_scan
    for fixture in (waylith_new, waylith_migrated):
        first = stream_scan(fixture).to_dict()
        second = stream_scan(fixture).to_dict()
        first["parseSeconds"] = second["parseSeconds"] = 0
        assert first == second
