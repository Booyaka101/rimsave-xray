"""Finding the install and the save file."""

from __future__ import annotations

from pathlib import Path

import pytest

from rimsavexray.discover import Game, _parse_vdf, list_saves, resolve_save, saves_dir
from rimsavexray.errors import UserError
from rimsavexray.scan import sha256_of, stream_scan

from builders import build_save, map_block, thing_block


def test_parse_vdf():
    vdf = ('"libraryfolders"\n{\n'
           '"0"\n{\n"path"\t\t"C:\\\\Program Files (x86)\\\\Steam"\n'
           '"apps"\n{\n"294100"\t\t"123"\n}\n}\n'
           '"1"\n{\n"path"\t\t"D:\\\\SteamLibrary"\n}\n}\n')
    parsed = _parse_vdf(vdf)
    folders = parsed["libraryfolders"]
    assert folders["0"]["path"] == "C:\\Program Files (x86)\\Steam"
    assert "294100" in folders["0"]["apps"]
    assert folders["1"]["path"] == "D:\\SteamLibrary"


def test_list_saves_newest_first(tmp_path):
    older = tmp_path / "Older.rws"
    newer = tmp_path / "Newer.rws"
    for p, tick in ((older, 1), (newer, 2)):
        p.write_text(build_save(), encoding="utf-8")
        stamp = 1700000000 + tick * 1000
        import os
        os.utime(p, (stamp, stamp))
    (tmp_path / "notes.txt").write_text("ignore me")
    saves = list_saves(tmp_path)
    assert [p.name for p in saves] == ["Newer.rws", "Older.rws"]


def test_resolve_save_by_path_and_cwd(monkeypatch, tmp_path):
    save = tmp_path / "Kolonie.rws"
    save.write_text(build_save(maps_xml=map_block(0, thing_block("Wall"))), encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    assert resolve_save("Kolonie.rws") == save
    assert resolve_save("Kolonie") == save          # bare name in cwd


def test_resolve_save_by_saves_dir_name(monkeypatch, tmp_path):
    save = tmp_path / "Tribe.rws"
    save.write_text(build_save(), encoding="utf-8")
    monkeypatch.setattr("rimsavexray.discover.saves_dir", lambda: tmp_path)
    assert resolve_save("Tribe") == save
    assert resolve_save(None) == save               # newest


def test_resolve_save_missing_lists_alternatives(monkeypatch, tmp_path):
    save = tmp_path / "Tribe.rws"
    save.write_text(build_save(), encoding="utf-8")
    monkeypatch.setattr("rimsavexray.discover.saves_dir", lambda: tmp_path)
    monkeypatch.chdir(Path(".").resolve())
    with pytest.raises(UserError, match="Tribe"):
        resolve_save("Nope")


def test_resolve_save_empty_saves_dir(monkeypatch, tmp_path):
    monkeypatch.setattr("rimsavexray.discover.saves_dir", lambda: tmp_path)
    with pytest.raises(UserError, match="no saves"):
        resolve_save(None)


def test_game_paths(tmp_path):
    root = tmp_path / "RimWorld"
    (root / "Data").mkdir(parents=True)
    game = Game(root=root, version="1.6.4850")
    assert game.mods_dir == root / "Mods"
    assert game.data_dir == root / "Data"
    assert game.workshop_dir is None  # not inside a steam library


def test_game_workshop_dir_inside_library(tmp_path):
    root = tmp_path / "steamapps" / "common" / "RimWorld"
    root.mkdir(parents=True)
    game = Game(root=root, version="1.6")
    assert game.workshop_dir == tmp_path / "steamapps" / "workshop" / "content" / "294100"


def test_scan_of_resolved_save_is_read_only(tmp_path):
    save = tmp_path / "Tribe.rws"
    save.write_text(build_save(maps_xml=map_block(0, thing_block("Wall"))), encoding="utf-8")
    before = sha256_of(save)
    result = stream_scan(resolve_save("Tribe") if saves_dir() == tmp_path else save)
    assert sha256_of(save) == before == result.sha256_before
