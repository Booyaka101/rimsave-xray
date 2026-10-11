"""Command line entry point.

Run with a save path or an in-game save name; with no argument it lists the
saves in the game's Saves folder and asks which one to scan (this is what the
double-clicked exe does).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import webbrowser
from pathlib import Path

from . import __version__, mods as mods_mod, report as report_mod, rules as rules_mod
from .discover import find_game, list_saves, resolve_save, saves_dir
from .errors import UserError
from .scan import stream_scan

DEFAULT_REPORT = "rimsavexray-report.html"


def _utf8_stdout() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):
            pass


def _prompt_save() -> Path:
    folder = saves_dir()
    saves = list_saves(folder)
    if not saves:
        raise UserError(f"no saves found in {folder}. Save the game once, "
                        "or drop a .rws file next to this program and drag it in.")
    print(f"Saves in {folder}:")
    for i, p in enumerate(saves, 1):
        size = p.stat().st_size / (1 << 20)
        when = time.strftime("%Y-%m-%d %H:%M", time.localtime(p.stat().st_mtime))
        print(f"  {i:2d}. {p.name}  ({size:.1f} MB, {when})")
    try:
        while True:
            answer = input(f"Scan which save? [1-{len(saves)}, Enter = 1, or a file path] ").strip().strip('"')
            if not answer:
                return saves[0]
            if answer.isdigit() and 1 <= int(answer) <= len(saves):
                return saves[int(answer) - 1]
            candidate = Path(answer).expanduser()
            if candidate.is_file():
                return candidate.resolve()
            try:
                return resolve_save(answer)
            except UserError:
                print(f"  {answer}: not a number from the list, nor an existing .rws file. Try again.")
    except EOFError:
        raise UserError("no save chosen; nothing was scanned.") from None


def _writable_report_path(path: str) -> Path:
    out = Path(path).expanduser()
    if out.is_absolute():
        return out
    # relative: next to the program when double-clicked (cwd), else temp if read-only
    target = (Path.cwd() / out).resolve()
    try:
        with target.open("a"):
            pass
        return target
    except OSError:
        fallback = Path(os.environ.get("TEMP", str(Path.home()))) / out
        print(f"{target} is not writable; writing the report to {fallback} instead.")
        return fallback


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="rimsavexray",
        description="See inside your RimWorld save: a read-only report of every byte and "
                    "every lag-driving count, per section and per mod, with a ranked fix list.")
    parser.add_argument("save", nargs="?", default=None,
                        help="a .rws / .rws.gz file path, a folder of saves, or an in-game "
                             "save name; with no argument the newest save is used "
                             "(or you are asked, in the double-clicked exe)")
    parser.add_argument("--game", metavar="PATH", default=None,
                        help="the RimWorld install folder, if Steam cannot be found")
    parser.add_argument("--json", action="store_true",
                        help="print the full result as JSON instead of the text summary")
    parser.add_argument("--out", metavar="FILE", default=DEFAULT_REPORT,
                        help=f"where to write the HTML report (default: {DEFAULT_REPORT} "
                             "in the current folder; use 'none' to skip it)")
    parser.add_argument("--list", action="store_true", help="list the saves in the Saves folder and exit")
    parser.add_argument("--open", action="store_true",
                        help="open the HTML report in your browser when done")
    parser.add_argument("--version", action="version", version=f"rimsavexray {__version__}")
    return parser


def run(args: argparse.Namespace) -> int:
    interactive = args.save is None and sys.stdin is not None and sys.stdin.isatty()
    if args.list:
        for p in list_saves():
            print(f"{p.name}  ({p.stat().st_size / (1 << 20):.1f} MB)")
        return 0
    save_path = _prompt_save() if interactive else resolve_save(args.save)

    game = None
    attribution_warnings: list[str] = []
    try:
        game = find_game(Path(args.game) if args.game else None)
    except UserError as exc:
        attribution_warnings.append(
            f"mods could not be attributed by owner: {exc} Counts and bytes are still exact.")

    result = stream_scan(save_path)
    attribution = mods_mod.attribute(result, game)
    attribution.warnings = attribution_warnings + attribution.warnings
    findings = rules_mod.evaluate(result, attribution)

    report_path = None
    if args.out.lower() != "none":
        report_path = _writable_report_path(args.out)
        report_path.write_text(
            report_mod.build_html(result, attribution, findings), encoding="utf-8")

    if args.json:
        payload = {
            "rimsavexray": __version__,
            "scan": result.to_dict(),
            "attribution": {
                "mods": [{"packageId": m.package_id, "name": m.name, "steamId": m.steam_id,
                          "installed": m.installed,
                          "label": m.label, "defs": m.def_count,
                          "thingsInSave": m.thing_count, "bytes": m.bytes}
                         for m in attribution.mods],
                "unattributedBytes": attribution.unattributed_bytes,
                "unattributedDefs": attribution.unattributed_defs,
                "warnings": attribution.warnings,
            },
            "findings": [{"rule": f.rule, "severity": f.severity,
                          "message": f.message, "detail": f.detail} for f in findings],
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    for line in report_mod.summary_lines(result, attribution, findings, report_path):
        print(line)
    for warning in attribution.warnings:
        print(f"note: {warning}", file=sys.stderr)

    if args.open and report_path is not None:
        webbrowser.open(report_path.as_uri())
    return 0


def main(argv: list[str] | None = None) -> int:
    _utf8_stdout()
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return run(args)
    except UserError as exc:
        print(f"rimsavexray: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("rimsavexray: stopped.", file=sys.stderr)
        return 130
    except OSError as exc:
        print(f"rimsavexray: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
