"""Shared fixtures: the three real demosaves plus synthetic save builders."""

from __future__ import annotations

import gzip
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent
FIXTURES = ROOT / "fixtures"
SRC = ROOT.parent / "src"
sys.path.insert(0, str(SRC))

from rimsavexray.scan import stream_scan  # noqa: E402


def fixture_path(name: str) -> Path:
    path = FIXTURES / name
    if not path.is_file():
        pytest.skip(f"fixture {name} not present")
    return path


@pytest.fixture(scope="session")
def demosave1() -> Path:
    return fixture_path("demosave 1.rws.gz")


@pytest.fixture(scope="session")
def waylith_new() -> Path:
    """A brand-new colony created and saved in RimWorld 1.7 (Waylith, unstable
    build 1.7.4976) on this project's own machine, vanilla loadout."""
    return fixture_path("waylith new colony.rws.gz")


@pytest.fixture(scope="session")
def waylith_new_scan(waylith_new):
    return stream_scan(waylith_new)


@pytest.fixture(scope="session")
def waylith_migrated() -> Path:
    """The owner's real 1.6.4850 save (Autosave-1, 8 mods) loaded in 1.7 and
    re-saved there: the migration path players actually hit. The tick count
    and mod list carried over from the 1.6 original."""
    return fixture_path("waylith migrated save.rws.gz")


@pytest.fixture(scope="session")
def waylith_migrated_scan(waylith_migrated):
    return stream_scan(waylith_migrated)


@pytest.fixture(scope="session")
def demosave1_scan(demosave1):
    return stream_scan(demosave1)


def gunzip_to(source: Path, target: Path) -> Path:
    with gzip.open(source, "rb") as src, target.open("wb") as dst:
        shutil.copyfileobj(src, dst)
    return target
