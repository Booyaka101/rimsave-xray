"""Map defNames to the mod that owns them.

The save's own mod list (meta/modIds) is the load order. For every mod there,
the installed folder is found the way the game finds mods (official data under
Data/, local and Workshop mods under Mods/, Workshop folders by Steam id), its
Defs/**/*.xml files are read for <defName> elements, and the LAST mod in load
order to define a defName owns it, which is how the game resolves redefined
defs.
"""

from __future__ import annotations

import os
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

from .discover import VANILLA_PACKAGE_IDS, Game
from .scan import ModEntry, ScanResult

VANILLA_LABEL = "Vanilla"
UNATTRIBUTED = "(unattributed)"

_ABOUT_BOMS = (b"\xef\xbb\xbf", b"\xff\xfe", b"\xfe\xff", b"\xff\xfe\x00\x00", b"\x00\x00\xfe\xff")


@dataclass
class ModAttribution:
    package_id: str
    name: str
    steam_id: str
    installed: bool
    folder: Path | None = None
    def_count: int = 0
    bytes: int = 0
    thing_count: int = 0

    @property
    def label(self) -> str:
        if not self.installed:
            return f"{self.name or self.package_id} (unattributed: mod folder not found)"
        if self.package_id in VANILLA_PACKAGE_IDS:
            return f"Vanilla ({VANILLA_PACKAGE_IDS[self.package_id]})"
        return self.name or self.package_id


def _read_about(folder: Path) -> tuple[str, str]:
    """(packageId, name) from About/About.xml, read the way the game reads it:
    any encoding with a BOM, tags matched case-insensitively, text joined."""
    path = folder / "About" / "About.xml"
    try:
        raw = path.read_bytes()
    except OSError:
        return "", folder.name
    if raw[:4] in _ABOUT_BOMS[3:] or raw[:2] in _ABOUT_BOMS[1:3] or raw[:3] == _ABOUT_BOMS[0]:
        for bom, codec in ((_ABOUT_BOMS[3], "utf-32"), (_ABOUT_BOMS[4], "utf-32"),
                           (_ABOUT_BOMS[1], "utf-16"), (_ABOUT_BOMS[2], "utf-16"),
                           (_ABOUT_BOMS[0], "utf-8-sig")):
            if raw.startswith(bom):
                try:
                    raw = raw.decode(codec).encode("utf-8")
                except UnicodeError:
                    pass
                break
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        return "", folder.name
    package_id = ""
    name = ""
    for el in root.iter():
        tag = el.tag.lower() if isinstance(el.tag, str) else ""
        if tag == "packageid" and not package_id:
            package_id = "".join(el.itertext()).strip().lower()
        elif tag == "name" and not name:
            name = "".join(el.itertext()).strip()
    return package_id, name


def _subfolders(path: Path | None) -> list[Path]:
    if path is None or not path.is_dir():
        return []
    return [p for p in path.iterdir() if p.is_dir()]


def scan_installed_mods(game: Game) -> dict[str, Path]:
    """packageId (lowercase) -> mod folder, across Data/, Mods/ and the Workshop dir."""
    index: dict[str, Path] = {}
    for folder in _subfolders(game.data_dir):           # official expansions
        package_id, _name = _read_about(folder)
        if package_id:
            index.setdefault(package_id, folder)
    for folder in _subfolders(game.mods_dir):           # local and Steam-downloaded mods
        package_id, _name = _read_about(folder)
        if package_id:
            index.setdefault(package_id, folder)
    workshop = game.workshop_dir
    for folder in _subfolders(workshop):                # classic Workshop layout, if present
        package_id, _name = _read_about(folder)
        if package_id and package_id not in index:
            index[package_id] = folder
    return index


def _iter_def_files(folder: Path):
    """Every xml a mod can define or rewrite defs in: Defs/ and Patches/.

    Patches count because a PatchOperationAdd/Replace whose <value> holds a
    <defName> defines that def as surely as a Defs file does (xpath selectors
    quote defNames as defName="X", never as <defName> elements, so the
    element scan does not pick up mere references).
    """
    for sub in ("Defs", "Patches"):
        base = folder / sub
        if not base.is_dir():
            continue
        for current, _dirs, files in os.walk(base):
            for fname in files:
                if fname.lower().endswith(".xml"):
                    yield Path(current, fname)


_DEF_NAME = re.compile(rb"<defName>([^<]+)</defName>")


def _def_names_in_file(path: Path) -> list[str]:
    """All defNames in one defs file, found textually.

    RimWorld defs files are machine-written with one <defName> leaf per def
    and no namespaces or CDATA, so a byte scan reads them exactly and an order
    of magnitude faster than building a tree per file.
    """
    try:
        raw = path.read_bytes()
    except OSError:
        return []
    names = [m.group(1).decode("utf-8", "replace").strip()
             for m in _DEF_NAME.finditer(raw)]
    return [n for n in names if n]


def _scan_defs_parallel(folder: Path) -> list[tuple[str, list[str]]]:
    """(file, defNames) for every defs file, read on a small thread pool.

    Defs folders are hundreds of small files; on a cold disk the reads, not
    the regex, dominate, and they overlap cleanly.
    """
    from concurrent.futures import ThreadPoolExecutor

    files = list(_iter_def_files(folder))
    if len(files) < 8:
        return [(str(f), _def_names_in_file(f)) for f in files]
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(_def_names_in_file, files))
    return list(zip((str(f) for f in files), results))


def _folder_by_steam_id(game: Game | None, steam_id: str) -> Path | None:
    """A mod folder named for its Workshop id: the layout Steam downloads
    into the game's Mods folder. The fallback for saves whose modId no longer
    matches the About.xml packageId (renamed or forked mods)."""
    if game is None or not steam_id or steam_id == "0":
        return None
    for base in (game.mods_dir, game.workshop_dir):
        if base is None:
            continue
        folder = base / steam_id
        if (folder / "About").is_dir() or (folder / "Defs").is_dir():
            return folder
    return None


class DefOwnerIndex:
    """defName -> owning mod package id, last writer in load order wins."""

    def __init__(self) -> None:
        self.owner: dict[str, str] = {}
        self.def_count: dict[str, int] = {}
        self.warnings: list[str] = []

    def add_mod(self, package_id: str, folder: Path) -> int:
        found = 0
        for _file, names in _scan_defs_parallel(folder):
            for def_name in names:
                self.owner[def_name] = package_id
                found += 1
        self.def_count[package_id] = self.def_count.get(package_id, 0) + found
        return found

    def owner_of(self, def_name: str) -> str | None:
        if def_name in self.owner:
            return self.owner[def_name]
        if def_name.startswith("Corpse_"):
            return self.owner.get(def_name[len("Corpse_"):])
        return None


@dataclass
class Attribution:
    mods: list[ModAttribution] = field(default_factory=list)
    by_def: dict[str, ModAttribution] = field(default_factory=dict)
    unattributed_bytes: int = 0
    unattributed_defs: int = 0
    scan_seconds: float = 0.0
    warnings: list[str] = field(default_factory=list)


def attribute(result: ScanResult, game: Game | None) -> Attribution:
    """Attribute every def the scan measured to the mod that defines it."""
    import time

    started = time.perf_counter()
    attribution = Attribution()
    installed = scan_installed_mods(game) if game is not None else {}

    # The save's mod list is the load order; walk it in order so redefined
    # defs end up with the last writer.
    entries: list[ModEntry] = list(result.mods)
    package_ids = [m.package_id.lower() for m in entries]
    load_order = list(dict.fromkeys(package_ids))
    by_package: dict[str, ModAttribution] = {}
    for entry in entries:
        pid = entry.package_id.lower()
        if pid in by_package:
            continue
        folder = installed.get(pid) or _folder_by_steam_id(game, entry.steam_id)
        mod = ModAttribution(package_id=pid, name=entry.name, steam_id=entry.steam_id,
                             installed=folder is not None, folder=folder)
        by_package[pid] = mod
        attribution.mods.append(mod)

    owner_index = DefOwnerIndex()
    # The save's own mod list is the load order; walking it in that order
    # leaves redefined defs with their last writer, the way the game loads them.
    for pid in load_order:
        if by_package[pid].folder is not None:
            owner_index.add_mod(pid, by_package[pid].folder)

    # def -> mod byte sums
    for def_name, byte_count in result.def_bytes.items():
        pid = owner_index.owner_of(def_name)
        if pid is None or pid not in by_package:
            attribution.unattributed_bytes += byte_count
            attribution.unattributed_defs += 1
            continue
        mod = by_package[pid]
        mod.bytes += byte_count
        mod.thing_count += result.def_counts.get(def_name, 0)
        attribution.by_def[def_name] = mod

    attribution.scan_seconds = time.perf_counter() - started
    attribution.warnings = list(owner_index.warnings)
    return attribution
