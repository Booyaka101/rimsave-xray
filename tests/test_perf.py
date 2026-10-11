"""The scale gate: a synthetic ~400 MB save parses in under 60 s under 500 MB RSS."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from rimsavexray.scan import stream_scan

from builders import build_save, map_block, thing_block

TARGET_BYTES = 400 * 1024 * 1024
TIME_BUDGET = 60.0
RSS_BUDGET = 500 * 1024 * 1024

pytestmark = pytest.mark.slow


def _peak_rss() -> int:
    if sys.platform == "win32":
        import ctypes

        class PMC(ctypes.Structure):
            _fields_ = [("cb", ctypes.c_uint32), ("PageFaultCount", ctypes.c_uint32),
                        ("PeakWorkingSetSize", ctypes.c_size_t),
                        ("WorkingSetSize", ctypes.c_size_t),
                        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                        ("PagefileUsage", ctypes.c_size_t),
                        ("PeakPagefileUsage", ctypes.c_size_t)]

        pmc = PMC()
        pmc.cb = ctypes.sizeof(PMC)
        ctypes.windll.psapi.GetProcessMemoryInfo(
            ctypes.windll.kernel32.GetCurrentProcess(), ctypes.byref(pmc), pmc.cb)
        return int(pmc.PeakWorkingSetSize)
    import resource
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024


@pytest.fixture(scope="module")
def big_save(tmp_path_factory) -> tuple[Path, int, int]:
    """A save built from duplicated map blocks until it passes 400 MB."""
    path = tmp_path_factory.mktemp("big") / "big.rws"
    thing_names = ["Wall", "Plant_Grass", "Steel", "Filth_Dirt"]
    batch = 500
    template = "".join(
        thing_block(thing_names[i % len(thing_names)], cls=None,
                    stack=(thing_names[i % len(thing_names)] == "Steel"), ident=i)
        for i in range(batch))
    header = build_save().split("<maps>")[0] + "<maps>"
    footer = "</maps></game></savegame>"
    things_per_map = batch
    with path.open("w", encoding="utf-8", newline="") as handle:
        handle.write(header)
        written = len(header.encode("utf-8"))
        maps = 0
        while written < TARGET_BYTES:
            block = map_block(maps, template)
            handle.write(block)
            written += len(block.encode("utf-8"))
            maps += 1
        handle.write(footer)
    return path, things_per_map * maps, len(thing_names)


def test_400mb_under_60s_under_500mb(big_save):
    path, expected_things, _distinct = big_save
    assert path.stat().st_size >= TARGET_BYTES

    import time
    started = time.perf_counter()
    result = stream_scan(path)
    elapsed = time.perf_counter() - started

    assert elapsed < TIME_BUDGET, f"parse took {elapsed:.1f}s"
    peak = _peak_rss()
    assert peak < RSS_BUDGET, f"peak RSS {peak / (1 << 20):.0f} MB"
    assert result.map_things == expected_things
    assert sum(result.sections.values()) == result.xml_bytes == path.stat().st_size
    assert result.read_only_ok
