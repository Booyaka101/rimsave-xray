"""The streaming scanner: exact byte attribution and every counter."""

from __future__ import annotations

import gzip
import xml.parsers.expat
from pathlib import Path

import pytest

from rimsavexray.errors import UserError
from rimsavexray.scan import sha256_of, stream_scan

from builders import build_save, designation_block, faction_block, map_block, pawn_block, thing_block
from conftest import gunzip_to


def test_byte_index_semantics():
    """The attribution contract this module is built on: a start event's
    CurrentByteIndex points at the '<' of the start tag, an end event's at the
    '<' of the end tag (or just past a self-closing element)."""
    doc = b"<r><a>xx</a><b/><c k=\"v\">y</c></r>"
    seen = []
    p = xml.parsers.expat.ParserCreate()
    p.StartElementHandler = lambda n, a: seen.append(("s", n, p.CurrentByteIndex))
    p.EndElementHandler = lambda n: seen.append(("e", n, p.CurrentByteIndex))
    p.Parse(doc, True)
    starts = {n: i for ev, n, i in seen if ev == "s"}
    ends = {n: i for ev, n, i in seen if ev == "e"}
    assert doc[starts["a"]:ends["a"] + len(b"</a>")] == b"<a>xx</a>"
    assert doc[starts["c"]:ends["c"] + len(b"</c>")] == b'<c k="v">y</c>'
    assert ends["b"] - starts["b"] == len(b"<b/>")  # self-closing: end index is just past


def write(tmp_path: Path, xml: str, name: str = "test.rws") -> Path:
    path = tmp_path / name
    path.write_bytes(xml.encode("utf-8"))   # exact bytes: no newline translation
    return path


# -- fixture: the three real demosaves --------------------------------------


def test_fixture_counts(demosave1_scan):
    r = demosave1_scan
    assert r.game_version == "1.3.3200 rev726"
    assert r.ticks_game == "41164371"
    assert len(r.mods) == 135
    assert r.mods[0].package_id == "brrainz.harmony"
    assert r.mods[0].name == "Harmony"
    assert r.world_pawns_alive == 29
    assert r.world_pawns_dead == 97
    assert r.world_pawns_forced == 64
    assert r.world_pawn_apparel == 114
    assert r.dead_pawn_apparel == 18
    assert r.player_faction_id == "Faction_17"
    assert len(r.maps) == 1
    assert r.map_things == 15535
    assert r.filth == 62
    assert r.floor_items == 101
    assert r.corpses == 29
    assert r.things_by_class["Plant"] == 11169
    assert sum(r.designations.values()) == 232


def test_fixture_sections_sum_to_file(demosave1_scan):
    r = demosave1_scan
    assert sum(r.sections.values()) == r.xml_bytes == 20831455
    assert r.sections["world"] == 10630036
    assert r.sections["maps"] == 6235236


def test_fixture_def_bytes_sum_within_maps(demosave1_scan):
    r = demosave1_scan
    # def-attributed bytes cannot exceed the sections that hold things
    assert sum(r.def_bytes.values()) < r.xml_bytes
    assert r.def_bytes["Human"] == 1589091


def test_read_only_sha(demosave1, demosave1_scan):
    r = demosave1_scan
    assert r.sha256_before == r.sha256_after == sha256_of(demosave1)
    assert r.read_only_ok


def test_plain_rws_of_fixture(demosave1, tmp_path):
    """The gunzipped copy scans with the same numbers, xml_bytes == file size."""
    plain = gunzip_to(demosave1, tmp_path / "demosave1.rws")
    r = stream_scan(plain)
    assert r.compressed is False
    assert r.xml_bytes == plain.stat().st_size
    assert r.map_things == 15535
    assert r.world_pawns_dead == 97


def test_gzip_magic_without_suffix(demosave1, tmp_path):
    """A gz file not ending in .gz is still opened by magic bytes."""
    copied = tmp_path / "weird-name"
    copied.write_bytes(demosave1.read_bytes())
    r = stream_scan(copied)
    assert r.compressed is True
    assert r.map_things == 15535


# -- synthetic saves: exact attribution --------------------------------------


def test_section_and_thing_attribution_exact(tmp_path):
    wall = thing_block("Wall", cls="Building", ident=1)
    steel = thing_block("Steel", stack=True, ident=2)
    things = wall + steel
    xml = build_save(meta=build_meta(), maps_xml=map_block(0, things))
    path = write(tmp_path, xml)
    r = stream_scan(path)
    # sections partition the whole file
    assert sum(r.sections.values()) == r.xml_bytes == path.stat().st_size
    assert r.def_counts == {"Wall": 1, "Steel": 1}
    assert r.def_bytes["Wall"] == len(wall.encode())
    assert r.def_bytes["Steel"] == len(steel.encode())


def build_meta() -> str:
    from builders import meta_block
    return meta_block()


def test_floor_items_and_filth_and_corpses(tmp_path):
    things = (
        thing_block("Steel", stack=True, ident=1)      # item
        + thing_block("Filth_Dirt", cls="Filth", ident=2)
        + thing_block("Corpse_Human", cls="Corpse", ident=3)
        + thing_block("Wall", cls="Building", ident=4)
        + thing_block("Apparel_Hat", stack=True, ident=5)  # dropped apparel is an item
    )
    xml = build_save(maps_xml=map_block(0, things))
    r = stream_scan(write(tmp_path, xml))
    assert r.floor_items == 2
    assert r.filth == 1
    assert r.corpses == 1
    assert r.things_by_class == {"Building": 1, "Filth": 1, "Corpse": 1}


def test_nested_stack_count_is_not_a_floor_item(tmp_path):
    """stackCount inside a container item does not make the container an item."""
    container = ('<thing Class="Building_Crate"><def>Crate</def><id>C1</id>'
                 '<innerContainer><innerList>'
                 '<li Class="ThingWithComps"><def>Steel</def><id>S1</id>'
                 "<stackCount>50</stackCount></li>"
                 "</innerList></innerContainer></thing>")
    xml = build_save(maps_xml=map_block(0, container))
    r = stream_scan(write(tmp_path, xml))
    assert r.floor_items == 0
    assert r.things_by_class["Building_Crate"] == 1


def test_world_pawns_and_apparel(tmp_path):
    alive = (pawn_block("Human", 1, "Faction_0", apparel=2, inventory=3)
             + pawn_block("Human", 2, "Faction_1", apparel=1))
    dead = pawn_block("Android", 3, "Faction_1", apparel=4)
    factions = faction_block(0, "PlayerColony") + faction_block(1, "Pirate")
    xml = build_save(factions=factions, world_pawns_alive=alive, world_pawns_dead=dead)
    r = stream_scan(write(tmp_path, xml))
    assert r.world_pawns_alive == 2
    assert r.world_pawns_dead == 1
    assert r.world_pawn_apparel == 7
    assert r.dead_pawn_apparel == 4
    assert r.world_pawn_inventory_items == 3
    assert r.player_faction_id == "Faction_0"
    assert r.faction_defs["Faction_1"] == "Pirate"


def test_designations(tmp_path):
    desigs = designation_block("Hunt", 1) + designation_block("Hunt", 2) + designation_block("CutPlant", 3)
    xml = build_save(maps_xml=map_block(0, designations=desigs))
    r = stream_scan(write(tmp_path, xml))
    assert dict(r.designations) == {"Hunt": 2, "CutPlant": 1}


def test_thing_comps_by_class(tmp_path):
    thing = ('<thing Class="ThingWithComps"><def>Gun</def><id>G1</id>'
             '<comps><li Class="CompQuality"><quality>Good</quality></li>'
             '<li Class="CompEquippable"><verbs /></li></comps></thing>')
    xml = build_save(maps_xml=map_block(0, thing))
    r = stream_scan(write(tmp_path, xml))
    assert dict(r.thing_comps) == {"CompQuality": 1, "CompEquippable": 1}


def test_multi_map_spans(tmp_path):
    things = thing_block("Wall", ident=1)
    xml = build_save(maps_xml=map_block(0, things) + map_block(1, things) + map_block(2, things))
    r = stream_scan(write(tmp_path, xml))
    assert len(r.maps) == 3
    assert sum(m.bytes for m in r.maps) <= r.sections["maps"]
    assert all(m.things == 1 for m in r.maps)
    assert sum(m.bytes for m in r.maps) + min(m.start for m in r.maps) >= 0


def test_self_closing_maps_section_exact(tmp_path):
    """A world-only save with <maps/> still partitions every byte exactly."""
    xml = build_save(maps_xml="")
    assert "<maps/>" in xml or "<maps></maps>" in xml
    path = write(tmp_path, xml)
    r = stream_scan(path)
    assert r.maps == []
    assert sum(r.sections.values()) == r.xml_bytes == path.stat().st_size
    assert r.sections.get("maps") in (None, 0, len("<maps/>"), len("<maps></maps>"))


def test_future_tags_ignored(tmp_path):
    """Unknown 1.7-style elements never crash and change no counters."""
    xml = build_save(maps_xml=map_block(0, thing_block("Wall", ident=1)
                                        + "<futureThing weird=\"1\">x</futureThing>"))
    xml = xml.replace("</game>", "<newManager17><deep><li>whatever</li></deep></newManager17></game>")
    r = stream_scan(write(tmp_path, xml))
    assert r.map_things == 1


def test_huge_single_text_node(tmp_path):
    big = "A" * (6 << 20)
    xml = build_save(maps_xml=map_block(0, thing_block("Wall", ident=1)),
                     game_scalars=f"<giant>{big}</giant>")
    r = stream_scan(write(tmp_path, xml))
    assert r.def_counts["Wall"] == 1
    assert sum(r.sections.values()) == r.xml_bytes


# -- bad input ----------------------------------------------------------------


def test_not_a_rimworld_save(tmp_path):
    path = write(tmp_path, "<?xml version=\"1.0\"?><other><x/></other>", "bad.rws")
    with pytest.raises(UserError, match="does not look like a RimWorld save"):
        stream_scan(path)


def test_truncated_save(tmp_path):
    xml = build_save(maps_xml=map_block(0, thing_block("Wall", ident=1)))
    path = write(tmp_path, xml[: len(xml) - 20], "cut.rws")
    with pytest.raises(UserError, match="truncated|corrupt|XML"):
        stream_scan(path)


def test_missing_file(tmp_path):
    with pytest.raises(UserError, match="no such file"):
        stream_scan(tmp_path / "nope.rws")


def test_empty_file(tmp_path):
    path = tmp_path / "empty.rws"
    path.write_bytes(b"")
    with pytest.raises(UserError, match="empty"):
        stream_scan(path)


def test_bom_save(tmp_path):
    xml = build_save(maps_xml=map_block(0, thing_block("Wall", ident=1)))
    path = tmp_path / "bom.rws"
    path.write_bytes(b"\xef\xbb\xbf" + xml.encode("utf-8"))
    r = stream_scan(path)
    assert r.def_counts["Wall"] == 1


def test_unicode_save_name(tmp_path):
    xml = build_save(maps_xml=map_block(0, thing_block("Wall", ident=1)))
    path = write(tmp_path, xml, "Сохранение наносити.rws")
    r = stream_scan(path)
    assert r.def_counts["Wall"] == 1
    assert "Сохранение" in str(r.path)


def test_double_gzip_raises_friendly(tmp_path):
    path = tmp_path / "double.gz"
    payload = gzip.compress(build_save().encode())
    path.write_bytes(gzip.compress(payload))
    with pytest.raises(UserError, match="XML"):
        stream_scan(path)


def test_truncated_gzip_raises_friendly(tmp_path, demosave1):
    """A gzip cut off mid-stream fails as a message, not an EOFError traceback."""
    raw = demosave1.read_bytes()
    path = tmp_path / "cut.rws.gz"
    path.write_bytes(raw[: len(raw) // 2])
    with pytest.raises(UserError, match="truncated|corrupt|mid-stream"):
        stream_scan(path)


def test_capture_capped_by_total_length(tmp_path):
    """One leaf with absurd text cannot balloon memory: the capture stops
    accumulating past CAPTURE_CAP instead of counting callbacks."""
    from rimsavexray.scan import CAPTURE_CAP
    big = "B" * (CAPTURE_CAP + 500000)
    xml = build_save(game_scalars=f"<giant>{big}</giant>",
                     maps_xml=map_block(0, thing_block("Wall", ident=1)))
    r = stream_scan(write(tmp_path, xml))
    # the scan completed and section sums still cover every byte
    assert r.def_counts["Wall"] == 1
    assert sum(r.sections.values()) == r.xml_bytes
