"""Find the RimWorld install, the player's Saves folder, and the save file itself.

The Steam-library walk mirrors how the game is found in rimbisect (registry key,
then every library in libraryfolders.vdf), reimplemented here on the standard
library only.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from .errors import UserError

APP_ID = "294100"
# 1.6 and older ship RimWorldWin64.exe (Unity); 1.7 on Waylith ships RimWorld.exe.
EXE_NAMES = ("RimWorld.exe", "RimWorldWin64.exe")
SAVES_RELATIVE = Path("AppData", "LocalLow", "Ludeon Studios", "RimWorld by Ludeon Studios", "Saves")
VANILLA_PACKAGE_IDS = {
    "ludeon.rimworld": "Core",
    "ludeon.rimworld.royalty": "Royalty",
    "ludeon.rimworld.ideology": "Ideology",
    "ludeon.rimworld.biotech": "Biotech",
    "ludeon.rimworld.odyssey": "Odyssey",
    "ludeon.rimworld.anomaly": "Anomaly",
}


@dataclass(frozen=True)
class Game:
    root: Path
    version: str

    @property
    def mods_dir(self) -> Path:
        return self.root / "Mods"

    @property
    def data_dir(self) -> Path:
        return self.root / "Data"

    @property
    def workshop_dir(self) -> Path | None:
        """<library>/steamapps/workshop/content/294100, when the game sits in a library."""
        if self.root.parent.name.lower() == "common" and self.root.parent.parent.name.lower() == "steamapps":
            return self.root.parent.parent / "workshop" / "content" / APP_ID
        return None


def _parse_vdf(text: str) -> dict:
    """Valve's KeyValues text format: quoted keys, quoted values or nested { } blocks."""
    import re

    tokens = re.findall(r'"((?:[^"\\]|\\.)*)"|([{}])', text)
    stack: list[dict] = [{}]
    key: str | None = None
    for quoted, brace in tokens:
        if brace == "{":
            child: dict = {}
            stack[-1][key or ""] = child
            stack.append(child)
            key = None
        elif brace == "}":
            if len(stack) > 1:
                stack.pop()
            key = None
        elif key is None:
            key = quoted
        else:
            stack[-1][key] = quoted.replace("\\\\", "\\")
            key = None
    return stack[0]


def steam_root() -> Path | None:
    try:
        import winreg
    except ImportError:
        winreg = None  # not on Windows
    if winreg is not None:
        for hive, sub in ((winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam"),
                          (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam")):
            try:
                with winreg.OpenKey(hive, sub) as handle:
                    for name in ("SteamPath", "InstallPath"):
                        try:
                            value, _ = winreg.QueryValueEx(handle, name)
                        except OSError:
                            continue
                        if value and Path(value).is_dir():
                            return Path(value)
            except OSError:
                continue
    default = Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Steam"
    return default if default.is_dir() else None


def _libraries(vdf_text: str) -> list[Path]:
    folders = _parse_vdf(vdf_text).get("libraryfolders", {})
    having: list[Path] = []
    rest: list[Path] = []
    for entry in folders.values():
        if not isinstance(entry, dict) or "path" not in entry:
            continue
        path = Path(entry["path"])
        (having if APP_ID in entry.get("apps", {}) else rest).append(path)
    return having + rest


def _read_version(root: Path) -> str:
    try:
        return (root / "Version.txt").read_text(encoding="utf-8-sig").strip()
    except OSError:
        return "unknown"


def find_game(explicit: Path | None = None) -> Game:
    """Locate the RimWorld install; --game overrides everything."""
    if explicit is not None:
        root = explicit.expanduser().resolve()
        if not root.is_dir():
            raise UserError(f"--game {root}: no such folder.")
        if not any((root / exe).is_file() for exe in EXE_NAMES) and not (root / "Data").is_dir():
            raise UserError(f"{root} does not look like a RimWorld install "
                            f"(no RimWorld.exe, no Data folder). Pass the RimWorld install folder with --game.")
        return Game(root, _read_version(root))
    steam = steam_root()
    if steam is None:
        raise UserError("could not find Steam. Pass the RimWorld install folder with --game.")
    vdf = steam / "steamapps" / "libraryfolders.vdf"
    try:
        libraries = _libraries(vdf.read_text(encoding="utf-8", errors="replace"))
    except OSError:
        libraries = [steam]
    for library in libraries:
        root = library / "steamapps" / "common" / "RimWorld"
        if any((root / exe).is_file() for exe in EXE_NAMES):
            return Game(root, _read_version(root))
    raise UserError(f"RimWorld (Steam app {APP_ID}) is not in any Steam library listed in {vdf}. "
                    "Pass the install folder with --game.")


def saves_dir() -> Path:
    base = Path(os.environ.get("USERPROFILE", str(Path.home())))
    return base / SAVES_RELATIVE


def list_saves(folder: Path | None = None) -> list[Path]:
    """Every .rws / .rws.gz in the Saves folder, newest first."""
    folder = folder or saves_dir()
    if not folder.is_dir():
        return []
    found = [p for p in folder.iterdir()
             if p.is_file() and (p.name.endswith(".rws") or p.name.endswith(".rws.gz"))]
    return sorted(found, key=lambda p: (p.stat().st_mtime, p.name), reverse=True)


def resolve_save(argument: str | None) -> Path:
    """Turn a CLI argument (file path, folder, or in-game save name) into a save path.

    With no argument the newest save in the Saves folder is used.
    """
    if argument is None:
        folder = saves_dir()
        saves = list_saves(folder)
        if not saves:
            raise UserError(f"no saves found in {folder}. Save the game once, or pass a .rws file path.")
        return saves[0]
    candidate = Path(argument).expanduser()
    if candidate.is_dir():
        saves = list_saves(candidate)
        if not saves:
            raise UserError(f"no saves found in {candidate}.")
        return saves[0]
    if candidate.is_file():
        return candidate.resolve()
    # a bare name: next to the program first (drag a save onto the folder), then
    # in the game's Saves folder
    for base in (Path.cwd(), saves_dir()):
        for suffix in (".rws", ".rws.gz"):
            hit = base / (argument + suffix)
            if hit.is_file():
                return hit
    if Path(argument).suffix and Path(argument).anchor:  # an absolute-looking path that is not there
        raise UserError(f"{candidate}: no such file.")
    folder = saves_dir()
    saves = list_saves(folder)
    if not saves:
        raise UserError(f"no save named {argument!r} and no saves at all in {folder}.")
    near = [p.stem for p in saves]
    raise UserError(f"no save named {argument!r} in {folder} (or the current folder). "
                    "Saves present: " + ", ".join(near[:10]) + ("..." if len(near) > 10 else ""))
