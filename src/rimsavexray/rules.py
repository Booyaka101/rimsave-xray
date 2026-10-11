"""The six seed rules. Every message prints the counted numbers it fired on."""

from __future__ import annotations

from dataclasses import dataclass

from .mods import Attribution
from .scan import ScanResult

WORLD_PAWN_LIMIT = 800
FLOOR_ITEM_LIMIT = 20000
FILTH_LIMIT = 5000
DEAD_APPAREL_LIMIT = 2000
MOD_SHARE_LIMIT = 0.15
COMPONENT_SHARE_LIMIT = 0.03
FILE_SIZE_LIMIT = 150 * 1024 * 1024
VANILLA_IDS = ("ludeon.rimworld", "ludeon.rimworld.royalty", "ludeon.rimworld.ideology",
               "ludeon.rimworld.biotech", "ludeon.rimworld.anomaly", "ludeon.rimworld.odyssey")


@dataclass
class Finding:
    rule: str
    severity: str          # "high" | "medium" | "info"
    message: str
    detail: str = ""


def _mb(n: float) -> str:
    return f"{n / (1 << 20):.1f} MB"


def world_pawns_rule(result: ScanResult) -> Finding | None:
    player = result.player_faction_id
    non_player = sum(count for faction, count in result.world_pawns_by_faction.items()
                     if faction != player)
    non_player_dead = sum(count for faction, count in result.dead_pawns_by_faction.items()
                          if faction != player)
    non_player_apparel = (result.world_pawn_apparel
                          - result.world_pawn_apparel_by_faction.get(player, 0))
    player_count = result.world_pawns_by_faction.get(player, 0)
    if non_player > WORLD_PAWN_LIMIT:
        return Finding(
            "world-pawns", "high",
            f"{non_player} world pawns still tracked ({non_player_dead} dead, "
            f"{non_player_apparel} apparel items in their inventories); every one costs ticks. "
            "Fix: dev mode Clean up world pawns, or enable your culling mod's option.",
            detail=(f"{player_count} of the tracked pawns are yours (faction "
                    f"{player or 'not identified'}); dead pawns wear "
                    f"{result.dead_pawn_apparel} apparel items in total."))
    if non_player == 0 and result.world_pawns_total == 0:
        return None
    return Finding(
        "world-pawns", "info",
        f"{non_player} world pawns still tracked ({non_player_dead} dead, "
        f"{non_player_apparel} apparel items in their inventories) - "
        f"within the {WORLD_PAWN_LIMIT} rule threshold.")


def floor_items_rule(result: ScanResult) -> Finding | None:
    items = result.floor_items
    if items <= FLOOR_ITEM_LIMIT:
        return None
    return Finding(
        "floor-items", "high",
        f"{items} items lie on your maps (over {FLOOR_ITEM_LIMIT}); every one is checked by "
        "hauling jobs and save size. Fix: consolidate into stockpiles or sell them.")


def filth_rule(result: ScanResult) -> Finding | None:
    filth = result.filth
    if filth <= FILTH_LIMIT:
        return None
    return Finding(
        "filth", "medium",
        f"{filth} filth things on your maps (over {FILTH_LIMIT}); filth re-checks on weather "
        "and time ticks. Fix: clean it, or use a filth-clearing mod.")


def apparel_on_corpses_rule(result: ScanResult) -> Finding | None:
    apparel = result.dead_pawn_apparel
    if apparel <= DEAD_APPAREL_LIMIT:
        return None
    return Finding(
        "apparel-on-corpses", "medium",
        f"{apparel} apparel items on dead pawns (over {DEAD_APPAREL_LIMIT}); stripping "
        "or destroying corpses frees save bytes and world-pawn tracking. "
        "Fix: dev mode Strip world pawns / Clean up world pawns.")


def mod_bytes_rule(result: ScanResult, attribution: Attribution) -> list[Finding]:
    total = result.xml_bytes
    findings: list[Finding] = []
    if total == 0:
        return findings
    from .discover import VANILLA_PACKAGE_IDS
    for mod in attribution.mods:
        if mod.bytes == 0:
            continue
        share = mod.bytes / total
        if share > MOD_SHARE_LIMIT:
            display = (f"Vanilla ({VANILLA_PACKAGE_IDS[mod.package_id]})"
                       if mod.package_id in VANILLA_IDS else (mod.name or mod.package_id))
            vanilla = " (vanilla content)" if mod.package_id in VANILLA_IDS else ""
            findings.append(Finding(
                "save-bytes-by-mod", "high",
                f"Mod {display} owns {_mb(mod.bytes)} "
                f"({share * 100:.1f}% of the save){vanilla}.",
                detail=f"{mod.thing_count} things of {mod.def_count} defs defined by it."))
    return findings


def component_share_rule(result: ScanResult) -> Finding | None:
    """One component Class holding a large share of the save: the shape a
    mod's quiet data accumulation takes (trading logs, stored menus, per-tick
    histories), which the thing counters never show."""
    total = result.xml_bytes
    if total == 0:
        return None
    cls, byte_count = max(result.component_bytes.items(), key=lambda kv: kv[1],
                          default=("", 0))
    if byte_count / total <= COMPONENT_SHARE_LIMIT:
        return None
    count = result.components_by_class.get(cls, 0)
    return Finding(
        "component-bytes", "medium",
        f"Component {cls} holds {_mb(byte_count)} ({byte_count / total * 100:.1f}% of the "
        f"save), outside every thing counter. Fix: check that mod's settings for logs or "
        "histories it keeps forever.",
        detail=f"one {cls} instance" if count == 1 else f"{count} instances of {cls}.")


def autosave_size_rule(result: ScanResult) -> Finding | None:
    size = result.file_size
    if size <= FILE_SIZE_LIMIT:
        return None
    return Finding(
        "autosave-size", "medium",
        f"{_mb(size)} save file (over 150 MB); loading takes longer and every autosave "
        "hitches the game for the whole write. The counters above show where the bytes are.")


_ORDER = {"high": 0, "medium": 1, "info": 2}


def evaluate(result: ScanResult, attribution: Attribution) -> list[Finding]:
    findings: list[Finding] = []
    for rule in (world_pawns_rule(result), floor_items_rule(result), filth_rule(result),
                 apparel_on_corpses_rule(result), component_share_rule(result),
                 autosave_size_rule(result)):
        if rule is not None:
            findings.append(rule)
    findings.extend(mod_bytes_rule(result, attribution))
    findings.sort(key=lambda f: (_ORDER[f.severity], -len(f.message)))
    return findings
