"""Compare two saves of the same colony: what grew, what shrank.

Built for mod development loops: play a few in-game days (or re-test your
mod), then check whether your build made the save heavier.

    py examples/save-drift-check.py Saves/Autosave-5.rws Saves/Autosave-4.rws
    py examples/save-drift-check.py old.rws new.rws --max-growth-pct 2

Exit codes: 0 within budget, 2 over budget or unreadable.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rimsavexray.errors import UserError
from rimsavexray.mods import attribute
from rimsavexray.scan import stream_scan


def _mb(n: float) -> str:
    return f"{n / (1 << 20):.1f} MB"


def _signed(n: int) -> str:
    return f"+{n:,}" if n >= 0 else f"{n:,}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("old", help="the older save (.rws or .rws.gz)")
    parser.add_argument("new", help="the newer save")
    parser.add_argument("--game", metavar="PATH", default=None,
                        help="RimWorld install folder, for mod attribution")
    parser.add_argument("--max-growth-pct", type=float, default=5.0,
                        help="fail when the newer save's XML grew more than this (default 5)")
    args = parser.parse_args(argv)

    game = None
    try:
        from rimsavexray.discover import find_game
        game = find_game(Path(args.game) if args.game else None)
    except UserError as exc:
        if args.game:
            print(f"drift-check: {exc}")
            return 2
        print(f"note: mods not attributed ({exc})")

    try:
        old = stream_scan(Path(args.old))
        new = stream_scan(Path(args.new))
    except UserError as exc:
        print(f"drift-check: {exc}")
        return 2

    if old.game_version != new.game_version:
        print(f"note: gameVersion changed: {old.game_version} -> {new.game_version}")
    ticks_old = int(old.ticks_game) if old.ticks_game.isdigit() else 0
    ticks_new = int(new.ticks_game) if new.ticks_game.isdigit() else 0
    if ticks_old and ticks_new and ticks_new < ticks_old:
        print("warning: the 'new' save is older in game time than the 'old' one; "
              "check the argument order.")
    if old.ticks_game and new.ticks_game and old.ticks_game != new.ticks_game:
        print(f"colony time: {ticks_old:,} -> {ticks_new:,} ticks "
              f"({_signed(ticks_new - ticks_old)})")

    growth_pct = ((new.xml_bytes - old.xml_bytes) / old.xml_bytes * 100) if old.xml_bytes else 0.0
    print(f"\ntotal XML   {_mb(old.xml_bytes)} -> {_mb(new.xml_bytes)}  "
          f"({_signed(new.xml_bytes - old.xml_bytes)} bytes, {growth_pct:+.2f}%)")

    print("\nsections (bytes)")
    for name in sorted(set(old.sections) | set(new.sections)):
        a, b = old.sections.get(name, 0), new.sections.get(name, 0)
        if a or b:
            print(f"  {name:20s} {a:>12,} -> {b:>12,}  {_signed(b - a)}")

    print("\ncounters")
    rows = [
        ("world pawns alive", old.world_pawns_alive, new.world_pawns_alive),
        ("world pawns dead", old.world_pawns_dead, new.world_pawns_dead),
        ("map things", old.map_things, new.map_things),
        ("floor items", old.floor_items, new.floor_items),
        ("filth", old.filth, new.filth),
        ("corpses", old.corpses, new.corpses),
        ("designations", sum(old.designations.values()), sum(new.designations.values())),
    ]
    for label, a, b in rows:
        print(f"  {label:20s} {a:>12,} -> {b:>12,}  {_signed(b - a)}")

    movers = {}
    for def_name in set(old.def_bytes) | set(new.def_bytes):
        movers[def_name] = new.def_bytes.get(def_name, 0) - old.def_bytes.get(def_name, 0)
    grown = sorted((d for d in movers.items() if d[1] > 0), key=lambda kv: -kv[1])[:5]
    shrunk = sorted((d for d in movers.items() if d[1] < 0), key=lambda kv: kv[1])[:5]
    if grown:
        print("\nbiggest growers")
        for def_name, delta in grown:
            print(f"  {def_name:28s} {_signed(delta):>12}")
    if shrunk:
        print("biggest shrinkers")
        for def_name, delta in shrunk:
            print(f"  {def_name:28s} {_signed(delta):>12}")

    comp_movers = sorted(
        ((cls, new.component_bytes.get(cls, 0) - old.component_bytes.get(cls, 0))
         for cls in set(old.component_bytes) | set(new.component_bytes)),
        key=lambda kv: -abs(kv[1]))[:5]
    if any(delta for _cls, delta in comp_movers):
        print("\ncomponents (biggest movers)")
        for cls, delta in comp_movers:
            print(f"  {cls:36s} {_signed(delta):>12}")

    if game is not None:
        old_att, new_att = attribute(old, game), attribute(new, game)
        by_pid_old = {m.package_id: m for m in old_att.mods}
        by_pid_new = {m.package_id: m for m in new_att.mods}

        def _mod_delta(pid: str) -> int:
            new_bytes = by_pid_new[pid].bytes if pid in by_pid_new else 0
            old_bytes = by_pid_old[pid].bytes if pid in by_pid_old else 0
            return new_bytes - old_bytes

        print("\nmods by bytes (only movers)")
        for pid in sorted(set(by_pid_old) | set(by_pid_new), key=_mod_delta, reverse=True):
            a = by_pid_old[pid].bytes if pid in by_pid_old else 0
            b = by_pid_new[pid].bytes if pid in by_pid_new else 0
            if b - a:
                label = (by_pid_new.get(pid) or by_pid_old[pid]).label
                print(f"  {label:44s} {a:>12,} -> {b:>12,}  {_signed(b - a)}")

    if growth_pct > args.max_growth_pct:
        print(f"\nOVER BUDGET: XML grew {growth_pct:.2f}% between these saves "
              f"(budget {args.max_growth_pct}%).")
        return 2
    print(f"\nwithin budget (XML {growth_pct:+.2f}% vs a {args.max_growth_pct}% growth budget).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
