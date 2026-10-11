"""Builders for synthetic .rws saves and synthetic mod folders.

The synthetic saves use the same shapes as real ones (savegame > meta, game >
world > worldPawns, maps > li > things > thing[@Class] > def), so the scanner
code paths exercised are the production ones.
"""

from __future__ import annotations

from pathlib import Path

MODS = ("ludeon.rimworld", "ludeon.rimworld.royalty", "brrainz.harmony", "test.mod.one")
MOD_NAMES = {"ludeon.rimworld": "Core", "ludeon.rimworld.royalty": "Royalty",
             "brrainz.harmony": "Harmony", "test.mod.one": "Test Mod"}


def meta_block(version: str = "1.6.4850 rev646", mods=MODS) -> str:
    mod_ids = "".join(f"<li>{m}</li>" for m in mods)
    steam_ids = "".join("<li>0</li>" for _ in mods)
    names = "".join(f"<li>{MOD_NAMES.get(m, m)}</li>" for m in mods)
    return (f"<meta><gameVersion>{version}</gameVersion>"
            f"<modIds>{mod_ids}</modIds>"
            f"<modSteamIds>{steam_ids}</modSteamIds>"
            f"<modNames>{names}</modNames></meta>")


def faction_block(load_id: int, fdef: str) -> str:
    return (f"<li><def>{fdef}</def><name>F{load_id}</name>"
            f"<loadID>{load_id}</loadID></li>")


def pawn_block(def_name: str = "Human", pid: int = 1, faction: str = "Faction_1",
               apparel: int = 0, inventory: int = 0) -> str:
    worn = ""
    for i in range(apparel):
        worn += (f"<li><def>Apparel_Shirt{i}</def><id>A{i}</id>"
                 "<health>100</health><stackCount>1</stackCount></li>")
    inv = ""
    for i in range(inventory):
        inv += (f'<li Class="ThingWithComps"><def>MealSimple{i}</def><id>M{i}</id>'
                "<health>1</health><stackCount>3</stackCount></li>")
    return (
        f"<li><def>{def_name}</def><id>{def_name}{pid}</id><faction>{faction}</faction>"
        f"<apparel><wornApparel><InnerList>{worn}</InnerList></wornApparel></apparel>"
        f"<inventory><innerContainer><innerList>{inv}</innerList></innerContainer></inventory>"
        "</li>")


def thing_block(def_name: str, cls: str | None = None, stack: bool = False,
                ident: int = 0) -> str:
    attr = f' Class="{cls}"' if cls else ""
    stack_xml = "<stackCount>5</stackCount>" if stack else ""
    return (f"<thing{attr}><def>{def_name}</def><id>{def_name}{ident}</id>"
            f"<health>100</health>{stack_xml}</thing>")


def map_block(index: int, things: str = "", designations: str = "") -> str:
    return (f"<li><uniqueID>{index}</uniqueID><mapInfo><size>(50, 1, 50)</size></mapInfo>"
            f"<things>{things}</things>"
            f"<designationManager><allDesignations>{designations}</allDesignations>"
            f"</designationManager></li>")


def designation_block(def_name: str, ident: int = 0) -> str:
    return f"<li><def>{def_name}</def><target>Thing_X{ident}</target></li>"


def build_save(meta: str = "", game_scalars: str = "", factions: str = "",
               world_pawns_alive: str = "", world_pawns_dead: str = "",
               maps_xml: str = "") -> str:
    game_head = (
        "<game>"
        "<tickManager><ticksGame>41164371</ticksGame></tickManager>"
        "<scenario><playerFaction><def>PlayerFaction</def>"
        "<factionDef>PlayerColony</factionDef></playerFaction></scenario>"
        f"{game_scalars}"
        "<components />"
    )
    world = (
        "<world><info><name>Test</name></info>"
        f"<factionManager><allFactions>{factions}</allFactions></factionManager>"
        f"<worldPawns><pawnsForcefullyKeptAsWorldPawns />"
        f"<pawnsAlive>{world_pawns_alive}</pawnsAlive>"
        f"<pawnsDead>{world_pawns_dead}</pawnsDead></worldPawns>"
        "<components /></world>"
    )
    return ('<?xml version="1.0" encoding="utf-8"?>\n<savegame>'
            f"{meta}{game_head}{world}<maps>{maps_xml}</maps></game></savegame>")


def write_mod(folder: Path, package_id: str, name: str, def_names: list[str]) -> Path:
    """A synthetic installed mod: About/About.xml plus Defs/ThingDefs.xml."""
    about = folder / "About"
    about.mkdir(parents=True, exist_ok=True)
    (about / "About.xml").write_text(
        '<?xml version="1.0" encoding="utf-8"?>\n'
        f"<ModMetaData><packageId>{package_id}</packageId><name>{name}</name>"
        "<supportedVersions><li>1.6</li></supportedVersions></ModMetaData>",
        encoding="utf-8")
    defs = folder / "Defs" / "ThingDefs"
    defs.mkdir(parents=True, exist_ok=True)
    body = "".join(f"<ThingDef><defName>{d}</defName></ThingDef>" for d in def_names)
    (defs / "ThingDefs.xml").write_text(
        '<?xml version="1.0" encoding="utf-8"?>\n<Defs>'
        f"{body}</Defs>", encoding="utf-8")
    return folder
