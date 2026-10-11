"""The HTML report and the terminal summary."""

from __future__ import annotations

import html
from pathlib import Path

from . import __version__
from .mods import VANILLA_LABEL, Attribution
from .rules import Finding
from .scan import ScanResult

TOP_DEFS = 25
MAX_BAR = 100.0


def _mb(n: float) -> str:
    return f"{n / (1 << 20):.1f} MB"


def _size(n: float) -> str:
    if n >= 1 << 20:
        return f"{n / (1 << 20):.1f} MB"
    if n >= 1 << 10:
        return f"{n / (1 << 10):.1f} KB"
    return f"{n} B"


def _pct(n: float, total: float) -> str:
    return f"{(n / total * 100):.1f}%" if total else "0%"


def _mod_label(attribution: Attribution, def_name: str) -> str:
    mod = attribution.by_def.get(def_name)
    if mod is None:
        return "unattributed (def not in any installed mod)"
    if mod.package_id in ("ludeon.rimworld", "ludeon.rimworld.royalty", "ludeon.rimworld.ideology",
                          "ludeon.rimworld.biotech", "ludeon.rimworld.anomaly",
                          "ludeon.rimworld.odyssey"):
        return VANILLA_LABEL
    return mod.name or mod.package_id


def top_section(result: ScanResult) -> tuple[str, int]:
    ranked = sorted(result.sections.items(), key=lambda kv: -kv[1])
    return ranked[0] if ranked else ("(none)", 0)


def top_mod(attribution: Attribution) -> tuple[str, int]:
    ranked = sorted(attribution.mods, key=lambda m: -m.bytes)
    if ranked and ranked[0].bytes > 0:
        return ranked[0].label, ranked[0].bytes
    return ("(none attributed)", 0)


def summary_lines(result: ScanResult, attribution: Attribution, findings: list[Finding],
                  report_path: Path | None = None) -> list[str]:
    section_name, section_bytes = top_section(result)
    mod_name, mod_bytes = top_mod(attribution)
    lines = [
        f"save        {result.path}",
        f"file size   {_mb(result.file_size)}"
        + (f" (gzip; {_mb(result.xml_bytes)} of XML inside)" if result.compressed else ""),
        f"gameVersion {result.game_version or '(not found)'}   ticks {result.ticks_game or '?'}",
        f"mods        {len(result.mods)} in the save's load order",
        f"sections    {section_name} is the biggest at {_mb(section_bytes)} "
        f"({_pct(section_bytes, result.xml_bytes)} of the save)",
        f"top mod     {mod_name} - {_mb(mod_bytes)} ({_pct(mod_bytes, result.xml_bytes)})",
        f"world pawns {result.world_pawns_total} tracked "
        f"({result.world_pawns_alive} alive, {result.world_pawns_dead} dead)",
        f"map things  {result.map_things} on {len(result.maps)} map(s): "
        f"{result.floor_items} floor items, {result.filth} filth, {result.corpses} corpses",
    ]
    ranked = [m for m in sorted(attribution.mods, key=lambda m: -m.bytes) if m.bytes > 0]
    if len(ranked) > 1:
        lines.append("mods by bytes " + ", ".join(
            f"{m.label} {_size(m.bytes)} ({_pct(m.bytes, result.xml_bytes)})"
            for m in ranked[:3]))
    if attribution.unattributed_defs:
        lines.append(f"unattributed {attribution.unattributed_defs} defs "
                     f"({_size(attribution.unattributed_bytes)}) no installed mod defines")
    if findings:
        lines.append("")
        lines.append("fix list:")
        for finding in findings:
            mark = "!" if finding.severity == "high" else ("-" if finding.severity == "medium" else " ")
            lines.append(f" [{mark}] {finding.message}")
    lines.append("")
    lines.append(f"read-only   SHA-256 before {result.sha256_before}")
    lines.append(f"            SHA-256 after  {result.sha256_after}"
                 + ("" if result.read_only_ok else "  CHANGED - the save was modified!"))
    if report_path is not None:
        lines.append(f"report      {report_path}")
    return lines


_STYLE = """
:root { color-scheme: dark; }
* { box-sizing: border-box; }
body { font: 14px/1.45 "Segoe UI", system-ui, sans-serif; margin: 0;
       background: #14161a; color: #d7dce3; padding: 24px; }
h1 { font-size: 20px; margin: 0 0 4px; }
h2 { font-size: 15px; margin: 28px 0 8px; color: #9fb4d8;
     border-bottom: 1px solid #2a2f37; padding-bottom: 4px; }
.sub { color: #7d8694; margin: 0 0 16px; }
.grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
        gap: 10px; margin: 14px 0; }
.card { background: #1c2027; border: 1px solid #2a2f37; border-radius: 8px; padding: 10px 12px; }
.card .k { color: #7d8694; font-size: 12px; }
.card .v { font-size: 17px; font-weight: 600; margin-top: 2px; }
.bar { background: #2a2f37; border-radius: 4px; height: 12px; overflow: hidden; }
.bar > i { display: block; height: 100%; background: #4d82c4; }
.bar.warn > i { background: #c46a4d; }
table { border-collapse: collapse; width: 100%; font-size: 13px; }
th, td { text-align: left; padding: 5px 8px; border-bottom: 1px solid #23272f; }
th { color: #9fb4d8; font-weight: 600; white-space: nowrap; }
td.n, th.n { text-align: right; white-space: nowrap; }
tr:hover td { background: #1c2027; }
.muted { color: #7d8694; }
.mono { font-family: Consolas, monospace; font-size: 12px; }
.sha { word-break: break-all; }
.ok { color: #7dba6a; }
.rule { background: #1c2027; border: 1px solid #2a2f37; border-left: 4px solid #4d82c4;
        border-radius: 6px; padding: 8px 12px; margin: 8px 0; }
.rule.high { border-left-color: #c4574d; }
.rule.medium { border-left-color: #c49a4d; }
.rule.info { border-left-color: #4d82c4; }
.rule .sev { font-size: 11px; text-transform: uppercase; letter-spacing: 0.6px; }
.rule.high .sev { color: #e07b6d; }
.rule.medium .sev { color: #d8b46a; }
.rule.info .sev { color: #7fa8dd; }
footer { margin-top: 30px; color: #59626e; font-size: 12px; }
"""


def _bar(value: int, total: int, warn: bool = False) -> str:
    width = min(MAX_BAR, (value / total * 100) if total else 0)
    return (f'<div class="bar{" warn" if warn else ""}">'
            f'<i style="width:{width:.1f}%"></i></div>')


def _section_rows(result: ScanResult) -> str:
    total = result.xml_bytes
    rows = []
    for name, byte_count in sorted(result.sections.items(), key=lambda kv: -kv[1]):
        rows.append(
            f"<tr><td>{html.escape(name)}</td>"
            f'<td class="n">{byte_count:,}</td>'
            f'<td class="n">{_mb(byte_count)}</td>'
            f'<td class="n">{_pct(byte_count, total)}</td>'
            f"<td>{_bar(byte_count, total, warn=name == 'maps' and byte_count > total * 0.6)}</td></tr>")
    return "".join(rows)


def _maps_rows(result: ScanResult) -> str:
    rows = []
    for m in result.maps:
        rows.append(
            f"<tr><td>map #{m.index + 1}</td>"
            f'<td class="n">{_mb(m.bytes)}</td>'
            f'<td class="n">{m.things:,}</td>'
            f'<td class="n">{m.pawns:,}</td>'
            f'<td class="n">{m.items:,}</td>'
            f'<td class="n">{m.filth:,}</td>'
            f'<td class="n">{m.corpses:,}</td></tr>')
    return "".join(rows)


def _defs_rows(result: ScanResult, attribution: Attribution) -> str:
    total = result.xml_bytes
    rows = []
    ranked = sorted(result.def_bytes.items(), key=lambda kv: -kv[1])[:TOP_DEFS]
    for def_name, byte_count in ranked:
        rows.append(
            f"<tr><td class='mono'>{html.escape(def_name)}</td>"
            f"<td>{html.escape(_mod_label(attribution, def_name))}</td>"
            f'<td class="n">{result.def_counts.get(def_name, 0):,}</td>'
            f'<td class="n">{byte_count:,}</td>'
            f'<td class="n">{_mb(byte_count)}</td>'
            f'<td class="n">{_pct(byte_count, total)}</td>'
            f"<td>{_bar(byte_count, total)}</td></tr>")
    return "".join(rows)


def _mods_rows(result: ScanResult, attribution: Attribution) -> str:
    total = result.xml_bytes
    rows = []
    for mod in sorted(attribution.mods, key=lambda m: (-m.bytes, m.label)):
        if mod.bytes == 0 and not mod.installed:
            continue
        rows.append(
            f"<tr><td>{html.escape(mod.label)}</td>"
            f'<td class="n">{mod.def_count:,}</td>'
            f'<td class="n">{mod.thing_count:,}</td>'
            f'<td class="n">{_mb(mod.bytes)}</td>'
            f'<td class="n">{_pct(mod.bytes, total)}</td>'
            f"<td>{_bar(mod.bytes, total)}</td></tr>")
    if attribution.unattributed_bytes:
        rows.append(
            f"<tr><td class='muted'>defs no installed mod defines "
            f"({attribution.unattributed_defs} defs)</td>"
            f"<td class='n muted'>-</td><td class='n muted'>-</td>"
            f'<td class="n">{_mb(attribution.unattributed_bytes)}</td>'
            f'<td class="n">{_pct(attribution.unattributed_bytes, total)}</td>'
            f"<td>{_bar(attribution.unattributed_bytes, total)}</td></tr>")
    return "".join(rows)


def _counter_rows(counter: dict, limit: int = 15) -> str:
    rows = []
    for name, count in list(counter.items())[:limit]:
        rows.append(f"<tr><td class='mono'>{html.escape(str(name))}</td>"
                    f'<td class="n">{count:,}</td></tr>')
    total = sum(counter.values())
    if len(counter) > limit:
        rows.append(f"<tr><td class='muted'>... {len(counter) - limit} more</td>"
                    f'<td class="n muted">{total:,} total</td></tr>')
    return "".join(rows)


def build_html(result: ScanResult, attribution: Attribution, findings: list[Finding]) -> str:
    mods_installed = sum(1 for m in attribution.mods if m.installed)
    section_name, section_bytes = top_section(result)
    mod_name, mod_bytes = top_mod(attribution)
    sha_note = ("unchanged - the save was only read" if result.read_only_ok
                else "CHANGED - the save was modified during the scan!")
    sha_class = "ok" if result.read_only_ok else ""
    rules_html = "".join(
        f'<div class="rule {f.severity}"><span class="sev">{f.severity}</span> '
        f"- {html.escape(f.message)}"
        + (f'<div class="muted">{html.escape(f.detail)}</div>' if f.detail else "")
        + "</div>"
        for f in findings) or '<div class="rule info"><span class="sev">clear</span> - no rule fired; nothing above a threshold.</div>'
    ticks = f"{int(result.ticks_game):,}" if result.ticks_game.isdigit() else (result.ticks_game or "?")
    year = f" (~year {5500 + int(result.ticks_game) // 3600000})" if result.ticks_game.isdigit() else ""

    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>rimsave-xray &middot; {html.escape(result.path.name)}</title>
<style>{_STYLE}</style></head><body>
<h1>rimsave-xray - {html.escape(result.path.name)}</h1>
<p class="sub">every byte and every lag-driving count in this save, by section and by mod.
Scan took {result.parse_seconds:.1f} s; attribution of mods took {attribution.scan_seconds:.1f} s.</p>

<div class="grid">
<div class="card"><div class="k">file size</div><div class="v">{_mb(result.file_size)}</div></div>
<div class="card"><div class="k">XML inside</div><div class="v">{_mb(result.xml_bytes)}</div></div>
<div class="card"><div class="k">gameVersion</div><div class="v">{html.escape(result.game_version or "?")}</div></div>
<div class="card"><div class="k">mods in save</div><div class="v">{len(result.mods)}
 <span class="muted" style="font-size:12px">({mods_installed} found installed)</span></div></div>
<div class="card"><div class="k">ticks played</div><div class="v">{ticks}</div>
 <div class="k">{year.strip(" ()")}</div></div>
<div class="card"><div class="k">biggest section</div><div class="v">{html.escape(section_name)}</div>
 <div class="k">{_mb(section_bytes)} &middot; {_pct(section_bytes, result.xml_bytes)}</div></div>
<div class="card"><div class="k">top byte-owning mod</div><div class="v">{html.escape(mod_name)}</div>
 <div class="k">{_mb(mod_bytes)} &middot; {_pct(mod_bytes, result.xml_bytes)}</div></div>
</div>

<h2>Read-only proof</h2>
<p class="mono sha">SHA-256 before scan: {result.sha256_before}<br>
SHA-256 after scan:&nbsp; {result.sha256_after}
<span class="{sha_class}">- {sha_note}</span></p>

<h2>Where the bytes are, by section</h2>
<table><tr><th>section</th><th class="n">bytes</th><th class="n"></th><th class="n">share</th><th style="width:34%"></th></tr>
{_section_rows(result)}</table>
<p class="muted">"game" is the part before &lt;world&gt;; the world and every map are counted separately.</p>

<h2>Maps</h2>
<table><tr><th>map</th><th class="n">bytes</th><th class="n">things</th><th class="n">pawns</th>
<th class="n">floor items</th><th class="n">filth</th><th class="n">corpses</th></tr>
{_maps_rows(result)}</table>

<h2>Top {TOP_DEFS} defs by bytes</h2>
<table><tr><th>def</th><th>mod</th><th class="n">count</th><th class="n">bytes</th>
<th class="n"></th><th class="n">share</th><th style="width:22%"></th></tr>
{_defs_rows(result, attribution)}</table>
<p class="muted">Bytes of a thing include everything nested inside it; world pawns are counted
under their own def (e.g. Human). {attribution.unattributed_defs} defs
({_mb(attribution.unattributed_bytes)}) could not be attributed.</p>

<h2>Mods by bytes owned</h2>
<table><tr><th>mod (load order as saved)</th><th class="n">defs</th><th class="n">things in save</th>
<th class="n">bytes</th><th class="n">share</th><th style="width:22%"></th></tr>
{_mods_rows(result, attribution)}</table>

<h2>Fix list (ranked)</h2>
{rules_html}

<h2>World pawns</h2>
<table><tr><th>faction</th><th class="n">alive</th><th class="n">dead</th><th class="n">apparel worn</th></tr>
{''.join(f"<tr><td class='mono'>{html.escape(f or '(none)')}"
         + (" <span class='muted'>(you)</span>" if f == result.player_faction_id else "")
         + f"</td><td class='n'>{result.world_pawns_by_faction.get(f, 0):,}</td>"
         f"<td class='n'>{result.dead_pawns_by_faction.get(f, 0):,}</td>"
         f"<td class='n'>{result.world_pawn_apparel_by_faction.get(f, 0):,}</td></tr>"
         for f in sorted(set(result.world_pawns_by_faction) | set(result.dead_pawns_by_faction)))}
</table>
<p class="muted">Player faction: <span class="mono">{html.escape(result.player_faction_id or "not identified")}</span>
(def {html.escape(result.player_faction_def or "?")}); {result.world_pawns_forced} pawn references are
forcefully kept as world pawns; dead world pawns wear {result.dead_pawn_apparel} apparel items;
their inventories hold {result.world_pawn_inventory_items} items.</p>

<h2>Things by Class</h2>
<table><tr><th>Class</th><th class="n">count</th></tr>{_counter_rows(dict(result.things_by_class.most_common()))}</table>

<h2>Thing comps by Class</h2>
<table><tr><th>comp Class</th><th class="n">count</th></tr>{_counter_rows(dict(result.thing_comps.most_common()))}</table>

<h2>Designations</h2>
<table><tr><th>designation</th><th class="n">count</th></tr>{_counter_rows(dict(result.designations.most_common()))}</table>

<footer>rimsave-xray {__version__} &middot; read-only &middot; {html.escape(str(result.path))} &middot;
scanned {result.parse_seconds:.1f} s</footer>
</body></html>"""
