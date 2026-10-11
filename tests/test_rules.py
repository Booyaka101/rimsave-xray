"""The six seed rules, each firing with its counted numbers."""

from __future__ import annotations

from pathlib import Path

from rimsavexray.mods import Attribution, ModAttribution
from rimsavexray.rules import (apparel_on_corpses_rule, autosave_size_rule,
                               component_share_rule, evaluate,
                               filth_rule, floor_items_rule, mod_bytes_rule,
                               world_pawns_rule)
from rimsavexray.scan import MapInfo, ScanResult

from collections import Counter


def make_result(**kwargs) -> ScanResult:
    defaults = dict(path=Path("x.rws"), file_size=1000, xml_bytes=1000, compressed=False,
                    sha256_before="a", sha256_after="a")
    defaults.update(kwargs)
    return ScanResult(**defaults)


def make_attribution(mods: list[tuple[str, str, int]] | None = None,
                     unattributed: int = 0) -> Attribution:
    attribution = Attribution()
    for package_id, name, byte_count in mods or []:
        attribution.mods.append(ModAttribution(package_id=package_id, name=name,
                                               steam_id="0", installed=True, bytes=byte_count))
    attribution.unattributed_bytes = unattributed
    return attribution


def test_world_pawns_over_limit():
    r = make_result(world_pawns_alive=900, world_pawns_dead=100,
                    world_pawns_by_faction=Counter({"Faction_1": 900, "Faction_0": 100}),
                    dead_pawns_by_faction=Counter({"Faction_1": 100}),
                    world_pawn_apparel=1500, world_pawn_apparel_by_faction=Counter({"Faction_1": 1500}),
                    player_faction_id="Faction_0")
    finding = world_pawns_rule(r)
    assert finding.severity == "high"
    assert "900 world pawns still tracked (100 dead, 1500 apparel items" in finding.message
    assert "Clean up world pawns" in finding.message


def test_world_pawns_under_limit_is_info():
    r = make_result(world_pawns_alive=3, world_pawns_dead=0,
                    world_pawns_by_faction=Counter({"Faction_0": 3}),
                    player_faction_id="Faction_0")
    finding = world_pawns_rule(r)
    assert finding is None or (finding.severity == "info" and "within" in finding.message)


def test_floor_items_over_limit():
    r = make_result(maps=[MapInfo(0, 0, 10, items=20001)])
    finding = floor_items_rule(r)
    assert "20001 items lie on your maps" in finding.message


def test_filth_over_limit():
    r = make_result(maps=[MapInfo(0, 0, 10, filth=5001)])
    assert "5001 filth things" in filth_rule(r).message


def test_apparel_on_dead_pawns_over_limit():
    r = make_result(dead_pawn_apparel=2001)
    assert "2001 apparel items on dead pawns" in apparel_on_corpses_rule(r).message


def test_mod_share_over_15_percent():
    r = make_result(xml_bytes=1000)
    attribution = make_attribution([("big.mod", "Big Mod", 200)])
    findings = mod_bytes_rule(r, attribution)
    assert len(findings) == 1
    assert "Mod Big Mod owns" in findings[0].message
    assert "20.0% of the save" in findings[0].message


def test_mod_share_under_threshold_silent():
    r = make_result(xml_bytes=1000)
    attribution = make_attribution([("small.mod", "Small", 149)])
    assert mod_bytes_rule(r, attribution) == []


def test_component_share_rule():
    r = make_result(xml_bytes=1000, component_bytes={"VTE.TradingManager": 40},
                    components_by_class=Counter({"VTE.TradingManager": 1}))
    finding = component_share_rule(r)
    assert finding.severity == "medium"
    assert "Component VTE.TradingManager holds" in finding.message
    assert "4.0% of the save" in finding.message


def test_component_share_rule_quiet_under_threshold():
    r = make_result(xml_bytes=1000, component_bytes={"Small.Comp": 29},
                    components_by_class=Counter({"Small.Comp": 3}))
    assert component_share_rule(r) is None


def test_component_share_rule_empty_save():
    assert component_share_rule(make_result()) is None


def test_autosave_size_over_150mb():
    r = make_result(file_size=151 * 1024 * 1024)
    finding = autosave_size_rule(r)
    assert "151.0 MB save file" in finding.message
    assert "autosave" in finding.message


def test_evaluate_ranks_high_first():
    r = make_result(file_size=200 * 1024 * 1024, maps=[MapInfo(0, 0, 10, items=30000)],
                    world_pawns_alive=1000, world_pawns_dead=50,
                    world_pawns_by_faction=Counter({"Faction_1": 1000}),
                    dead_pawns_by_faction=Counter({"Faction_1": 50}),
                    world_pawn_apparel=10, dead_pawn_apparel=10)
    findings = evaluate(r, make_attribution())
    severities = [f.severity for f in findings]
    assert severities == sorted(severities, key={"high": 0, "medium": 1, "info": 2}.get)
    assert {f.rule for f in findings} >= {"autosave-size", "floor-items", "world-pawns"}


def test_messages_print_counted_numbers_only():
    """No rule message ships with a placeholder count."""
    r = make_result(world_pawns_alive=801, world_pawns_dead=1,
                    world_pawns_by_faction=Counter({"Faction_9": 801}),
                    dead_pawns_by_faction=Counter({"Faction_9": 1}),
                    world_pawn_apparel=2, world_pawn_apparel_by_faction=Counter({"Faction_9": 2}))
    message = world_pawns_rule(r).message
    for number in ("801", "1", "2"):
        assert number in message
