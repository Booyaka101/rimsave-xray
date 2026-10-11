"""defName -> mod attribution."""

from __future__ import annotations

from pathlib import Path

from rimsavexray.discover import Game
from rimsavexray.mods import attribute, scan_installed_mods
from rimsavexray.scan import ModEntry, stream_scan

from builders import build_save, map_block, pawn_block, thing_block, write_mod


def make_game(tmp_path: Path) -> Game:
    root = tmp_path / "RimWorld"
    root.mkdir()
    return Game(root=root, version="1.6.4850")


def save_with_defs(tmp_path: Path, mods, def_names: list[str]):
    """A real scan of a synthetic save whose meta lists exactly these mods."""
    from builders import MOD_NAMES
    mod_ids = "".join(f"<li>{m}</li>" for m in mods)
    steam_ids = "".join("<li>0</li>" for _ in mods)
    names = "".join(f"<li>{MOD_NAMES.get(m, m)}</li>" for m in mods)
    meta = (f"<meta><modIds>{mod_ids}</modIds>"
            f"<modSteamIds>{steam_ids}</modSteamIds><modNames>{names}</modNames></meta>")
    things = "".join(thing_block(name, ident=i) for i, name in enumerate(def_names))
    xml = build_save(meta=meta, maps_xml=map_block(0, things))
    path = tmp_path / "s.rws"
    path.write_text(xml, encoding="utf-8")
    return stream_scan(path)


def test_mod_folder_attribution(tmp_path):
    game = make_game(tmp_path)
    write_mod(game.data_dir / "Core", "ludeon.rimworld", "Core", ["Wall", "Human"])
    write_mod(game.mods_dir / "TestMod", "test.mod.one", "Test Mod", ["GlowStone"])
    write_mod(game.mods_dir / "OtherMod", "other.mod", "Other", ["Unused"])

    result = save_with_defs(tmp_path, ["ludeon.rimworld", "test.mod.one"],
                            ["Wall", "GlowStone", "Mystery"])
    attribution = attribute(result, game)

    by_label = {m.label: m for m in attribution.mods}
    assert by_label["Vanilla (Core)"].bytes == result.def_bytes["Wall"]
    assert by_label["Test Mod"].bytes == result.def_bytes["GlowStone"]
    assert by_label["Vanilla (Core)"].thing_count == 1
    assert attribution.unattributed_bytes == result.def_bytes["Mystery"]
    assert attribution.unattributed_defs == 1


def test_missing_mod_marked_unattributed(tmp_path):
    game = make_game(tmp_path)
    write_mod(game.data_dir / "Core", "ludeon.rimworld", "Core", ["Wall"])
    result = save_with_defs(tmp_path, ["ludeon.rimworld", "gone.mod"],
                            ["Wall", "GlowStone"])
    attribution = attribute(result, game)
    missing = [m for m in attribution.mods if m.package_id == "gone.mod"][0]
    assert missing.installed is False
    assert "mod folder not found" in missing.label
    assert missing.bytes == 0
    assert attribution.unattributed_bytes == result.def_bytes["GlowStone"]


def test_last_writer_in_load_order_wins(tmp_path):
    game = make_game(tmp_path)
    write_mod(game.mods_dir / "A", "mod.a", "A", ["Contested"])
    write_mod(game.mods_dir / "B", "mod.b", "B", ["Contested"])
    # B loads after A in the save's list, so B owns the def
    result = save_with_defs(tmp_path, ["mod.a", "mod.b"], ["Contested"])
    attribution = attribute(result, game)
    by_id = {m.package_id: m for m in attribution.mods}
    assert by_id["mod.b"].bytes == result.def_bytes["Contested"]
    assert by_id["mod.a"].bytes == 0


def test_corpse_defs_follow_their_thing_def(tmp_path):
    """Corpse_Human is a runtime-generated def; its bytes belong to Human's owner."""
    game = make_game(tmp_path)
    write_mod(game.data_dir / "Core", "ludeon.rimworld", "Core", ["Human"])
    result = save_with_defs(tmp_path, ["ludeon.rimworld"], ["Corpse_Human"])
    attribution = attribute(result, game)
    assert attribution.by_def["Corpse_Human"].package_id == "ludeon.rimworld"


def test_vanilla_grouping(tmp_path):
    game = make_game(tmp_path)
    write_mod(game.data_dir / "Core", "ludeon.rimworld", "Core", ["Wall"])
    write_mod(game.data_dir / "Royalty", "ludeon.rimworld.royalty", "Royalty", ["Throne"])
    result = save_with_defs(tmp_path, ["ludeon.rimworld", "ludeon.rimworld.royalty"],
                            ["Wall", "Throne"])
    attribution = attribute(result, game)
    labels = [m.label for m in attribution.mods]
    assert "Vanilla (Core)" in labels and "Vanilla (Royalty)" in labels


def test_attribution_without_game(tmp_path):
    result = save_with_defs(tmp_path, ["ludeon.rimworld"], ["Wall"])
    attribution = attribute(result, None)
    assert attribution.unattributed_bytes == result.def_bytes["Wall"]
    assert all(not m.installed for m in attribution.mods)


def test_world_pawn_defs_attributed(tmp_path):
    game = make_game(tmp_path)
    write_mod(game.data_dir / "Core", "ludeon.rimworld", "Core", ["Human"])
    pawns = pawn_block("Human", 1, "Faction_0") + pawn_block("Human", 2, "Faction_0")
    xml = build_save(meta="<meta><modIds><li>ludeon.rimworld</li></modIds></meta>",
                     world_pawns_alive=pawns)
    path = tmp_path / "s.rws"
    path.write_text(xml, encoding="utf-8")
    result = stream_scan(path)
    attribution = attribute(result, game)
    assert attribution.by_def["Human"].package_id == "ludeon.rimworld"
    assert attribution.by_def["Human"].bytes == result.def_bytes["Human"]


def test_patches_define_defs(tmp_path):
    """A PatchOperationAdd whose <value> holds a <defName> defines that def;
    an xpath selector quoting defName="X" does not."""
    game = make_game(tmp_path)
    mod = game.mods_dir / "Patcher"
    write_mod(mod, "patcher.mod", "Patcher", [])
    patches = mod / "Patches"
    patches.mkdir(parents=True, exist_ok=True)
    (patches / "P.xml").write_text(
        '<?xml version="1.0" encoding="utf-8"?>\n<PatchOperations>'
        '<li Class="PatchOperationAdd"><xpath>/Defs</xpath>'
        "<value><DesignationCategoryDef><defName>GR_SomeTab</defName></DesignationCategoryDef></value>"
        "</li>"
        '<li Class="PatchOperationReplace">'
        "<xpath>/Defs/ThingDef[defName=\"Wall\"]/label</xpath>"
        "<value><label>changed</label></value>"
        "</li>"
        "</PatchOperations>", encoding="utf-8")
    # only GR_SomeTab is a def the mod defines; "Wall" is a selector reference
    write_mod(game.data_dir / "Core", "ludeon.rimworld", "Core", ["Wall"])
    result = save_with_defs(tmp_path, ["ludeon.rimworld", "patcher.mod"],
                            ["GR_SomeTab", "Wall"])
    attribution = attribute(result, game)
    by_id = {m.package_id: m for m in attribution.mods}
    assert by_id["patcher.mod"].bytes == result.def_bytes["GR_SomeTab"]
    assert attribution.by_def["Wall"].package_id == "ludeon.rimworld"


def test_about_xml_case_insensitive_tags(tmp_path):
    """About.xml with different tag case still yields the packageId."""
    game = Game(root=tmp_path, version="1.6")
    write_mod(game.mods_dir / "Weird", "Odd.Case", "Odd", [])
    index = scan_installed_mods(game)
    assert "odd.case" in index
