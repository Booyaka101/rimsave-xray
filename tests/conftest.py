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
def demosave1_scan(demosave1):
    return stream_scan(demosave1)


def gunzip_to(source: Path, target: Path) -> Path:
    with gzip.open(source, "rb") as src, target.open("wb") as dst:
        shutil.copyfileobj(src, dst)
    return target
