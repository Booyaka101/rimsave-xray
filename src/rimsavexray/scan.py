"""The streaming scan: one pass over the save, every byte attributed.

xml.parsers.expat is used directly instead of ElementTree.iterparse for one
reason: expat's CurrentByteIndex gives the exact byte offset of every element,
which is what per-section and per-def byte attribution needs. It is the same
stdlib parser ElementTree builds on, walked with a pair of handlers; no tree is
ever built, so memory stays flat no matter how large the save is.

Measured index semantics (tests/test_scan.py calibrates them against a file
with known offsets): a start event's index points at the '<' of the start tag;
an end event's index points at the '<' of the end tag, or just past the
element when it is self-closing.
"""

from __future__ import annotations

import gzip
import hashlib
import re
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from xml.parsers import expat

from .errors import UserError

CHUNK = 1 << 20          # bytes fed to expat per Parse() call
WINDOW = 8 << 20         # tail of the stream kept addressable for tag peeks
CAPTURE_CAP = 1 << 16    # longest single text value captured (defs are short)
GZIP_MAGIC = b"\x1f\x8b"

# Structural vocabulary as observed in real saves back to 1.3 (children of
# <savegame>, and children of <game>), measured across the three demosave
# fixtures (1.3, 135 mods), three real 1.6 autosaves and a real 1.5 save
# with 815 mods: the union is exactly this set. A block outside it in a
# 1.7+ save is surfaced as new, never silently dropped.
KNOWN_DEPTH2 = frozenset({"meta", "game"})
KNOWN_GAME_CHILDREN = frozenset({
    "analysisManager", "battleLog", "cameraMap", "components", "currentMapIndex",
    "customXenogermDatabase", "customXenotypeDatabase", "dateNotifier",
    "drugPolicyDatabase", "entityCodex", "foodRestrictionDatabase", "gameEnder",
    "hiddenItemsManager", "history", "info", "letterStack", "maps", "outfitDatabase",
    "playLog", "playSettings", "questManager", "readingPolicyDatabase",
    "relationshipRecords", "researchManager", "rules", "scenario", "storyWatcher",
    "storyteller", "studyManager", "taleManager", "tickManager",
    "transportShipManager", "tutor", "uniqueIDsManager", "world",
})


def version_tuple(version: str) -> tuple[int, ...]:
    """'1.7.4976 rev1043' -> (1, 7, 4976); unparseable -> (0,)."""
    match = re.match(r"(\d+)\.(\d+)(?:\.(\d+))?", (version or "").strip())
    if not match:
        return (0,)
    return tuple(int(part) for part in match.groups(default="0"))



@dataclass
class MapInfo:
    index: int
    start: int
    end: int
    things: int = 0
    filth: int = 0
    items: int = 0
    pawns: int = 0
    corpses: int = 0

    @property
    def bytes(self) -> int:
        return max(0, self.end - self.start)


@dataclass
class ModEntry:
    package_id: str
    steam_id: str = ""
    name: str = ""


@dataclass
class ScanResult:
    path: Path
    file_size: int                 # bytes on disk
    xml_bytes: int                 # bytes of XML after gunzip (== file_size for plain .rws)
    compressed: bool
    sha256_before: str
    sha256_after: str
    game_version: str = ""
    ticks_game: str = ""
    mods: list[ModEntry] = field(default_factory=list)
    sections: dict[str, int] = field(default_factory=dict)
    maps: list[MapInfo] = field(default_factory=list)
    def_counts: Counter = field(default_factory=Counter)     # map things + world pawns
    def_bytes: dict[str, int] = field(default_factory=dict)
    things_by_class: Counter = field(default_factory=Counter)
    thing_comps: Counter = field(default_factory=Counter)
    components_by_class: Counter = field(default_factory=Counter)
    component_bytes: dict[str, int] = field(default_factory=dict)
    designations: Counter = field(default_factory=Counter)
    world_pawns_alive: int = 0
    world_pawns_dead: int = 0
    world_pawns_forced: int = 0
    world_pawns_by_faction: Counter = field(default_factory=Counter)
    dead_pawns_by_faction: Counter = field(default_factory=Counter)
    world_pawn_apparel: int = 0
    world_pawn_apparel_by_faction: Counter = field(default_factory=Counter)
    world_pawn_inventory_items: int = 0
    dead_pawn_apparel: int = 0
    player_faction_id: str = ""
    player_faction_def: str = ""
    faction_defs: dict[str, str] = field(default_factory=dict)
    # structural blocks outside the known 1.3-1.6 vocabulary, 1.7+ saves only:
    # name -> [count, total bytes]
    unmapped_blocks: dict[str, list[int]] = field(default_factory=dict)
    parse_seconds: float = 0.0

    @property
    def is_waylith_save(self) -> bool:
        """True for saves written by RimWorld 1.7 (the Waylith engine) or newer."""
        return version_tuple(self.game_version) >= (1, 7, 0)

    @property
    def read_only_ok(self) -> bool:
        return self.sha256_before == self.sha256_after

    @property
    def world_pawns_total(self) -> int:
        return self.world_pawns_alive + self.world_pawns_dead

    @property
    def map_things(self) -> int:
        return sum(m.things for m in self.maps)

    @property
    def filth(self) -> int:
        return sum(m.filth for m in self.maps)

    @property
    def floor_items(self) -> int:
        return sum(m.items for m in self.maps)

    @property
    def corpses(self) -> int:
        return sum(m.corpses for m in self.maps)

    def to_dict(self) -> dict:
        return {
            "path": str(self.path),
            "fileSize": self.file_size,
            "xmlBytes": self.xml_bytes,
            "compressed": self.compressed,
            "sha256Before": self.sha256_before,
            "sha256After": self.sha256_after,
            "readOnlyOk": self.read_only_ok,
            "gameVersion": self.game_version,
            "ticksGame": self.ticks_game,
            "mods": [{"packageId": m.package_id, "steamId": m.steam_id, "name": m.name}
                     for m in self.mods],
            "sections": dict(self.sections),
            "maps": [{"index": m.index, "bytes": m.bytes, "things": m.things,
                      "filth": m.filth, "items": m.items, "pawns": m.pawns,
                      "corpses": m.corpses} for m in self.maps],
            "defCounts": dict(self.def_counts.most_common()),
            "defBytes": dict(sorted(self.def_bytes.items(), key=lambda kv: -kv[1])),
            "thingsByClass": dict(self.things_by_class.most_common()),
            "thingComps": dict(self.thing_comps.most_common()),
            "componentsByClass": dict(self.components_by_class.most_common()),
            "componentBytes": dict(sorted(self.component_bytes.items(), key=lambda kv: -kv[1])),
            "designations": dict(self.designations.most_common()),
            "unmappedBlocks": {name: {"count": entry[0], "bytes": entry[1]}
                               for name, entry in sorted(self.unmapped_blocks.items())},
            "worldPawns": {"alive": self.world_pawns_alive, "dead": self.world_pawns_dead,
                           "forcedKept": self.world_pawns_forced,
                           "byFaction": dict(self.world_pawns_by_faction.most_common()),
                           "deadByFaction": dict(self.dead_pawns_by_faction.most_common()),
                           "apparel": self.world_pawn_apparel,
                           "apparelByFaction": dict(self.world_pawn_apparel_by_faction.most_common()),
                           "inventoryItems": self.world_pawn_inventory_items,
                           "deadPawnApparel": self.dead_pawn_apparel,
                           "playerFactionId": self.player_faction_id,
                           "playerFactionDef": self.player_faction_def},
            "parseSeconds": round(self.parse_seconds, 3),
        }


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(CHUNK), b""):
            digest.update(block)
    return digest.hexdigest()


def _open_stream(path: Path) -> tuple[object, bool]:
    """The save file as a binary stream, gunzipped when it ends in .rws.gz."""
    with path.open("rb") as probe:
        magic = probe.read(2)
    if path.name.endswith(".gz") or magic == GZIP_MAGIC:
        try:
            return gzip.open(path, "rb"), True
        except OSError as exc:
            raise UserError(f"{path}: could not open as gzip: {exc}") from exc
    return path.open("rb"), False


class _NotASave(Exception):
    pass


class _Scanner:
    """SAX walk over the save. Counters key off the element stack; byte spans
    come from expat's CurrentByteIndex at the events of attributed elements."""

    def __init__(self) -> None:
        self.names: list[str] = []            # tag stack, one entry per open element
        self.ctx: list[dict] = []             # attributed elements only
        self.buf = bytearray()                # tail of the fed stream, for peeks
        self.buf_start = 0                    # absolute index of buf[0]
        self.fed = 0
        self.section_start: dict[str, int] = {}
        self.maps_end = 0
        self._maps_paired = True
        self.map_starts: list[int] = []
        self.capture: list | None = None      # [sink, parts, tag]
        self._capture_len = 0
        self._steam_sink = None
        self._name_sink = None
        self.struct_spans: dict[str, list[int]] = {}   # depth2/game-child name -> [count, bytes]
        self._struct_open: dict[int, tuple[str, int, bool]] = {}  # depth -> (name, start, paired)
        self.result: ScanResult | None = None
        self.parser: expat.XMLParserType | None = None

    # -- stream window -----------------------------------------------------

    def _self_closing(self, start_idx: int) -> bool:
        """Does the start tag at start_idx end with '/>' ?

        RimWorld save attributes never contain '>', so the first '>' after the
        tag's '<' closes the start tag.
        """
        off = start_idx - self.buf_start
        if off < 0:
            return False
        chunk = self.buf[off:off + 4096]
        gt = chunk.find(b">")
        return gt > 0 and chunk[gt - 1:gt] == b"/"

    # -- expat handlers ------------------------------------------------------

    def _start(self, name, attrs):
        names = self.names
        names.append(name)
        n = len(names)
        if n == 1:
            if name != "savegame":
                raise _NotASave()
            return
        parent = names[n - 2]
        ctx = self.ctx
        top = ctx[-1] if ctx else None
        kind = top["kind"] if top else ""

        # structural spans: children of <savegame> and of <game> only, so a
        # block the report vocabulary has never seen can still be measured
        if n == 2 or (n == 3 and parent == "game"):
            start = self.parser.CurrentByteIndex
            self._struct_open[n] = (name, start, not self._self_closing(start))

        # section boundaries: a contiguous partition of the whole file
        if n == 2 and name in ("meta", "game"):
            self.section_start[name] = self.parser.CurrentByteIndex
        elif n == 3 and parent == "game" and name in ("world", "maps"):
            self.section_start[name] = self.parser.CurrentByteIndex
            if name == "maps":
                # the end-event formula differs for <maps/> vs <maps>...</maps>
                self._maps_paired = not self._self_closing(self.parser.CurrentByteIndex)

        # meta: game version and the three parallel mod lists
        if name == "gameVersion" and parent == "meta":
            self._arm_text(lambda v: setattr(self.result, "game_version", v.strip()))
        elif name == "li" and parent in ("modIds", "modSteamIds", "modNames"):
            if parent == "modIds":
                self._arm_text(self._mod_id)
            else:
                # modSteamIds and modNames are parallel to modIds: item i belongs
                # to mod i, not to whichever mod was appended last
                if parent == "modSteamIds":
                    if self._steam_sink is None:
                        self._steam_sink = self._parallel_list_sink("steam_id")
                    self._arm_text(self._steam_sink)
                else:
                    if self._name_sink is None:
                        self._name_sink = self._parallel_list_sink("name")
                    self._arm_text(self._name_sink)
        elif name == "li" and parent == "pawnsForcefullyKeptAsWorldPawns":
            self.result.world_pawns_forced += 1
        elif name == "ticksGame" and parent == "tickManager":
            # only the game's own tick count, not per-colonist colonistEvents copies
            self._arm_text(lambda v: setattr(self.result, "ticks_game", v.strip()))
        elif name == "factionDef" and parent == "playerFaction":
            # the scenario names the player faction's def (PlayerColony, or a mod's variant)
            self._arm_text(lambda v: setattr(self.result, "player_faction_def", v.strip()))
        elif name == "li" and parent == "maps":
            start = self.parser.CurrentByteIndex
            self.map_starts.append(start)
            info = MapInfo(index=len(self.result.maps), start=start, end=0)
            ctx.append({"tag": name, "kind": "map", "start": start, "paired": True,
                        "depth": len(names), "info": info})
            self.result.maps.append(info)
        elif name == "thing" and parent == "things" and kind == "map":
            self._open_thing(name, attrs, nested=False)
        elif name == "thing" and kind == "thing":
            self._open_thing(name, attrs, nested=True)
        elif kind == "thing":
            if name == "def" and parent == "thing" and not top["nested"] and n == top["depth"] + 1:
                self._arm_text(top["set_def"])
            elif name == "stackCount" and n == top["depth"] + 1:
                top["item"] = True
            elif name == "li" and parent == "comps" and "Class" in attrs:
                self.result.thing_comps[attrs["Class"]] += 1
        elif name == "li" and parent == "allDesignations":
            entry = {"tag": name, "kind": "designation", "start": 0, "paired": True,
                     "depth": len(names), "def": None}
            entry["set_def"] = lambda v, e=entry: e.__setitem__("def", v.strip())
            ctx.append(entry)
        elif name == "li" and "Class" in attrs and parent == "components":
            # game, world and map components: the one place a mod's save
            # footprint lives outside things (things use 'comps', not
            # 'components', so the two never collide)
            start = self.parser.CurrentByteIndex
            ctx.append({"tag": name, "kind": "component", "start": start,
                        "paired": not self._self_closing(start), "depth": len(names),
                        "cls": attrs["Class"]})
        elif kind == "designation":
            if name == "def" and parent == "li" and n == top["depth"] + 1:
                self._arm_text(top["set_def"])
        elif name == "li" and parent in ("pawnsAlive", "pawnsDead"):
            start = self.parser.CurrentByteIndex
            entry = {"tag": name, "kind": "pawn", "start": start,
                     "paired": not self._self_closing(start), "depth": len(names),
                     "def": None, "faction": None,
                     "alive": parent == "pawnsAlive",
                     "apparel": 0, "inv_items": 0, "in_apparel": 0, "in_inventory": 0}
            entry["set_def"] = lambda v, e=entry: e.__setitem__("def", v.strip())
            entry["set_faction"] = lambda v, e=entry: e.__setitem__("faction", v.strip())
            entry["add_apparel"] = lambda _v, e=entry: e.__setitem__("apparel", e["apparel"] + 1)
            entry["add_inv_item"] = lambda _v, e=entry: e.__setitem__("inv_items", e["inv_items"] + 1)
            ctx.append(entry)
        elif kind == "pawn":
            if name == "wornApparel":
                top["in_apparel"] += 1
            elif name == "inventory":
                top["in_inventory"] += 1
            elif name == "def":
                if top["in_apparel"]:
                    self._arm_text(top["add_apparel"])
                elif top["in_inventory"]:
                    self._arm_text(top["add_inv_item"])
                elif parent == "li" and n == top["depth"] + 1:
                    self._arm_text(top["set_def"])
            elif name == "faction" and parent == "li" and n == top["depth"] + 1:
                self._arm_text(top["set_faction"])
            elif name == "li" and parent == "comps" and "Class" in attrs:
                self.result.thing_comps[attrs["Class"]] += 1
        elif name == "li" and parent == "allFactions":
            entry = {"tag": name, "kind": "faction", "start": 0, "paired": True,
                     "depth": len(names), "load_id": None, "fdef": None}
            entry["set_id"] = lambda v, e=entry: e.__setitem__("load_id", v.strip())
            entry["set_fdef"] = lambda v, e=entry: e.__setitem__("fdef", v.strip())
            ctx.append(entry)
        elif kind == "faction":
            if name == "loadID" and parent == "li" and n == top["depth"] + 1:
                self._arm_text(top["set_id"])
            elif name == "def" and parent == "li" and n == top["depth"] + 1:
                self._arm_text(top["set_fdef"])

    def _open_thing(self, name, attrs, nested: bool) -> None:
        start = self.parser.CurrentByteIndex
        entry = {"tag": name, "kind": "thing", "start": start,
                 "paired": not self._self_closing(start), "nested": nested,
                 "depth": len(self.names), "def": None, "class": attrs.get("Class"),
                 "item": False}
        entry["set_def"] = lambda v, e=entry: e.__setitem__("def", v.strip())
        self.ctx.append(entry)

    def _end(self, name):
        depth = len(self.names)
        opened = self._struct_open.pop(depth, None)
        if opened is not None and opened[0] == name:
            end = self.parser.CurrentByteIndex
            if opened[2]:
                end += len(name) + 3
            entry = self.struct_spans.setdefault(name, [0, 0])
            entry[0] += 1
            entry[1] += max(0, end - opened[1])
        if name == "maps" and depth == 3:
            end = self.parser.CurrentByteIndex
            self.maps_end = end + (len(name) + 3 if self._maps_paired else 0)
        ctx = self.ctx
        if ctx and ctx[-1]["tag"] == name and ctx[-1]["depth"] == len(self.names):
            entry = ctx.pop()
            kind = entry["kind"]
            end = self.parser.CurrentByteIndex
            if entry["paired"]:
                end += len(name) + 3
            result = self.result
            if kind == "thing" and not entry["nested"]:
                def_name = entry["def"] or "(no def)"
                result.def_counts[def_name] += 1
                result.def_bytes[def_name] = result.def_bytes.get(def_name, 0) + (end - entry["start"])
                cls = entry["class"]
                if cls:
                    result.things_by_class[cls] += 1
                mp = result.maps[-1]
                mp.things += 1
                if cls == "Filth":
                    mp.filth += 1
                elif cls == "Pawn":
                    mp.pawns += 1
                elif cls == "Corpse":
                    mp.corpses += 1
                if entry["item"]:
                    mp.items += 1
            elif kind == "pawn":
                def_name = entry["def"] or "(no def)"
                result.def_counts[def_name] += 1
                result.def_bytes[def_name] = result.def_bytes.get(def_name, 0) + (end - entry["start"])
                faction = entry["faction"] or "(none)"
                if entry["alive"]:
                    result.world_pawns_alive += 1
                    result.world_pawns_by_faction[faction] += 1
                else:
                    result.world_pawns_dead += 1
                    result.dead_pawns_by_faction[faction] += 1
                    result.dead_pawn_apparel += entry["apparel"]
                result.world_pawn_apparel += entry["apparel"]
                result.world_pawn_apparel_by_faction[faction] += entry["apparel"]
                result.world_pawn_inventory_items += entry["inv_items"]
            elif kind == "designation":
                if entry["def"]:
                    result.designations[entry["def"]] += 1
            elif kind == "component":
                cls = entry["cls"]
                result.components_by_class[cls] += 1
                result.component_bytes[cls] = (result.component_bytes.get(cls, 0)
                                               + (end - entry["start"]))
            elif kind == "faction":
                if entry["load_id"]:
                    faction_ref = f"Faction_{entry['load_id']}"
                    result.faction_defs[faction_ref] = entry["fdef"] or ""
                    if entry["fdef"] and (entry["fdef"] == result.player_faction_def
                                          or entry["fdef"].startswith("Player")):
                        result.player_faction_id = faction_ref
            elif kind == "map":
                entry["info"].end = end
        else:
            top = ctx[-1] if ctx else None
            if top is not None and top["kind"] == "pawn":
                if name == "wornApparel":
                    top["in_apparel"] -= 1
                elif name == "inventory":
                    top["in_inventory"] -= 1
        if self.capture is not None and self.capture[2] == name:
            sink, parts, _tag = self.capture
            sink("".join(parts))
            self.capture = None
            self._capture_len = 0
            self.parser.CharacterDataHandler = None
        self.names.pop()

    def _chars(self, data):
        if self._capture_len + len(data) <= CAPTURE_CAP:
            self.capture[1].append(data)
            self._capture_len += len(data)

    # -- text capture ------------------------------------------------------

    def _arm_text(self, sink):
        self.capture = [sink, [], self.names[-1]]
        self._capture_len = 0
        self.parser.CharacterDataHandler = self._chars

    # -- mod list sinks ------------------------------------------------------

    def _mod_id(self, value):
        self.result.mods.append(ModEntry(package_id=value.strip()))

    def _parallel_list_sink(self, attr: str):
        """A sink for the i-th <li> of modSteamIds / modNames: it updates mod i."""
        state = {"i": 0}

        def sink(value):
            i = state["i"]
            state["i"] += 1
            if i < len(self.result.mods):
                setattr(self.result.mods[i], attr, value.strip())

        return sink


def stream_scan(path: Path) -> ScanResult:
    """Scan one save file. Read-only: the file is opened for reading only."""
    path = Path(path)
    if not path.is_file():
        raise UserError(f"{path}: no such file.")
    sha_before = sha256_of(path)
    file_size = path.stat().st_size
    stream, compressed = _open_stream(path)

    scanner = _Scanner()
    parser = expat.ParserCreate()
    scanner.parser = parser
    parser.StartElementHandler = scanner._start
    parser.EndElementHandler = scanner._end
    result = ScanResult(path=path, file_size=file_size, xml_bytes=0, compressed=compressed,
                        sha256_before=sha_before, sha256_after="")
    scanner.result = result

    started = time.perf_counter()
    try:
        while True:
            try:
                block = stream.read(CHUNK)
            except (OSError, EOFError, gzip.BadGzipFile) as exc:
                # gzip streams raise EOFError mid-read when the file is cut off
                raise UserError(f"{path} ends mid-stream ({exc}); the save is truncated or "
                                "corrupt. RimWorld autosaves rotate, try the previous one."
                                ) from exc
            if not block:
                break
            scanner.fed += len(block)
            scanner.buf += block
            if len(scanner.buf) > 2 * WINDOW:
                drop = len(scanner.buf) - WINDOW
                del scanner.buf[:drop]
                scanner.buf_start += drop
            try:
                parser.Parse(block, False)
            except expat.ExpatError as exc:
                raise UserError(
                    f"{path} is not XML the scanner can read (expat: {exc}). "
                    "If RimWorld can load this save, please open an issue."
                ) from exc
        try:
            parser.Parse(b"", True)
        except expat.ExpatError as exc:
            raise UserError(f"{path} ends mid-element ({exc}); the save is truncated or corrupt. "
                            "RimWorld autosaves rotate, try the previous one.") from exc
    except _NotASave:
        raise UserError(f"{path} does not look like a RimWorld save (no <savegame> root element). "
                        "Pass a .rws or .rws.gz file.") from None
    finally:
        stream.close()

    result.parse_seconds = time.perf_counter() - started
    result.xml_bytes = scanner.fed
    if result.xml_bytes == 0:
        raise UserError(f"{path} is empty.")

    # Sections as a contiguous partition: every byte lands in exactly one.
    # Each section runs from its start marker to the next section's start
    # marker (so trailing whitespace between sections folds in); the last
    # section runs to </maps> when present, and everything after is tail.
    starts = scanner.section_start
    markers = [(name, at) for name, at in
               (("meta", starts.get("meta")), ("game", starts.get("game")),
                ("world", starts.get("world")), ("maps", starts.get("maps")))
               if at is not None]
    display: dict[str, int] = {}
    if markers:
        display["(xml header)"] = markers[0][1]   # declaration and anything before the sections
        for i, (nm, at) in enumerate(markers):
            end = markers[i + 1][1] if i + 1 < len(markers) else (
                scanner.maps_end if scanner.maps_end else result.xml_bytes)
            display[nm] = max(0, end - at)
        last_end = scanner.maps_end if scanner.maps_end else result.xml_bytes
        if last_end < result.xml_bytes:
            display["(after sections)"] = result.xml_bytes - last_end
    else:
        display["(whole file)"] = result.xml_bytes
    result.sections = display

    # 1.7+: structural blocks outside the 1.3-1.6 vocabulary are surfaced,
    # never dropped. Older saves are reported exactly as before.
    if result.is_waylith_save:
        for name, (count, byte_count) in scanner.struct_spans.items():
            known = name in KNOWN_DEPTH2 or name in KNOWN_GAME_CHILDREN
            if not known and byte_count > 0:
                result.unmapped_blocks[name] = [count, byte_count]

    # per-map spans: each map runs from its start to the next map's start
    ends = scanner.map_starts[1:] + [scanner.maps_end or result.xml_bytes]
    for mp, end in zip(result.maps, ends):
        if end > mp.start:
            mp.end = end
    result.sha256_after = sha256_of(path)
    return result
