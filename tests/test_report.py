"""The HTML report and the terminal summary."""

from __future__ import annotations

import re
from pathlib import Path

from rimsavexray.mods import attribute
from rimsavexray.report import build_html, summary_lines
from rimsavexray.rules import evaluate


def full_run(demosave1_scan):
    attribution = attribute(demosave1_scan, None)
    findings = evaluate(demosave1_scan, attribution)
    return attribution, findings


def test_html_contains_required_sections(demosave1_scan):
    attribution, findings = full_run(demosave1_scan)
    html = build_html(demosave1_scan, attribution, findings)
    for required in (
        "Top 25 defs by bytes",
            "Where the bytes are, by section",
            "Fix list (ranked)",
            "Read-only proof",
            "SHA-256 before scan:",
            "SHA-256 after scan:",
            "Mods by bytes owned",
            "World pawns",
            "Things by Class",
            "Components by Class",
            "Designations"):
        assert required in html, required


def test_html_has_mod_column_and_real_numbers(demosave1_scan):
    attribution, findings = full_run(demosave1_scan)
    html = build_html(demosave1_scan, attribution, findings)
    assert "<th>mod</th>" in html
    # real numbers from the scan appear in the table
    assert ">Human<" in html
    assert "1,589,091" in html          # Human's measured bytes
    assert "unattributed" in html       # fixture mods are not installed here


def test_html_missing_mods_row(demosave1_scan):
    """Mods in the save that are not installed appear as the brief's
    '(unattributed: mod folder not found)' row, collapsed to one line."""
    attribution, findings = full_run(demosave1_scan)
    html = build_html(demosave1_scan, attribution, findings)
    assert "mods in the save are not installed" in html
    assert "(unattributed: mod folder not found)" in html


def test_html_components_table(tmp_path):
    from builders import build_save, map_block, thing_block
    from rimsavexray.scan import stream_scan

    comp = ('<components><li Class="Convergence.GameComponent_Sync">'
            '<state>abc</state></li></components>')
    xml = build_save(game_scalars=comp, maps_xml=map_block(0, thing_block("Wall")))
    path = tmp_path / "c.rws"
    path.write_bytes(xml.encode())
    result = stream_scan(path)
    attribution, findings = full_run(result)
    html = build_html(result, attribution, findings)
    assert "Convergence.GameComponent_Sync" in html
    assert result.component_bytes["Convergence.GameComponent_Sync"] == len(
        b'<li Class="Convergence.GameComponent_Sync"><state>abc</state></li>')


def test_html_is_self_contained(demosave1_scan):
    attribution, findings = full_run(demosave1_scan)
    html = build_html(demosave1_scan, attribution, findings)
    assert "<script" not in html
    assert "http://" not in html and "https://" not in html
    assert html.startswith("<!DOCTYPE html>")
    assert html.count("<style>") == 1


def test_html_escaping_of_save_names(tmp_path):
    from rimsavexray.scan import MapInfo, ScanResult
    result = ScanResult(path=tmp_path / "<script>&.rws", file_size=1, xml_bytes=1,
                        compressed=False, sha256_before="a", sha256_after="a",
                        sections={"meta": 1})
    html = build_html(result, attribution_empty(), [])
    assert "<script>&.rws" not in html
    assert "&lt;script&gt;&amp;.rws" in html


def attribution_empty():
    from rimsavexray.mods import Attribution
    return Attribution()


def test_summary_lines_print_the_brief_numbers(demosave1_scan):
    attribution, findings = full_run(demosave1_scan)
    lines = summary_lines(demosave1_scan, attribution, findings, Path("report.html"))
    text = "\n".join(lines)
    assert "gameVersion 1.3.3200 rev726" in text
    assert "135 in the save" in text
    assert "world is the biggest" in text
    assert "126 tracked (29 alive, 97 dead)" in text
    assert "15535 on 1 map(s)" in text
    assert "SHA-256 before" in text and "SHA-256 after" in text
    assert "report.html" in text


def test_sha_line_reports_unchanged(demosave1_scan):
    attribution, findings = full_run(demosave1_scan)
    text = "\n".join(summary_lines(demosave1_scan, attribution, findings))
    assert "CHANGED" not in text
    assert demosave1_scan.sha256_before == demosave1_scan.sha256_after


def test_rules_panel_holds_counts(demosave1_scan):
    attribution, findings = full_run(demosave1_scan)
    html = build_html(demosave1_scan, attribution, findings)
    for finding in findings:
        first_number = re.search(r"\d[\d,]*", finding.message).group(0)
        assert first_number in html
