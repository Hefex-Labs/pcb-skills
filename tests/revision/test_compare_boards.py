"""Change-location checks on an authored, synthetic two-layer board snapshot."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("compare_boards", ROOT / "pcb-revision-review/scripts/compare_boards.py")
assert SPEC and SPEC.loader
helper = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(helper)
BOARD = Path(__file__).parent / "fixtures/two_layer.kicad_pcb"


def changed(tmp_path: Path, old: str, new: str) -> Path:
    target = tmp_path / "after.kicad_pcb"
    text = BOARD.read_text(encoding="utf-8")
    assert old in text
    target.write_text(text.replace(old, new, 1), encoding="utf-8")
    return target


def test_localizes_placement_and_copper_changes_without_modifying_inputs(tmp_path: Path) -> None:
    target = changed(tmp_path, "(at 110 90)", "(at 112 90)")
    target.write_text(target.read_text().replace("(width 0.4)", "(width 0.5)", 1))
    before_bytes, after_bytes = BOARD.read_bytes(), target.read_bytes()
    result = helper.compare(BOARD, target, 5)
    assert {entry["kind"] for entry in result["record_changes"]} == {"footprint", "segment"}
    assert all(entry["added_records"] == entry["removed_records"] == 1 for entry in result["record_changes"])
    assert len(result["diff_preview"]) == 5 and result["diff_truncated"]
    assert BOARD.read_bytes() == before_bytes and target.read_bytes() == after_bytes


def test_spacing_inside_a_property_is_a_real_token_change(tmp_path: Path) -> None:
    target = changed(tmp_path, '(property "Value" "10k"', '(property "Value" "10 k"')
    assert [entry["kind"] for entry in helper.compare(BOARD, target)["record_changes"]] == ["footprint"]


def test_ignores_external_whitespace_and_top_level_record_order(tmp_path: Path) -> None:
    target = tmp_path / "formatted.kicad_pcb"
    text = BOARD.read_text()
    text = text.replace('(paper "A4")\n', '').replace('(general (thickness 1.6))', '(general   (thickness 1.6))\n  (paper "A4")')
    target.write_text(text.replace('\n  (segment', '\n\n    (segment'))
    result = helper.compare(BOARD, target)
    assert result["normalized_record_content_equal"]
    assert not result["raw_bytes_equal"]


@pytest.mark.parametrize("text", ['(kicad_pcb (version 20240108)', '(kicad_pcb (property "broken))'])
def test_refuses_unbalanced_or_unterminated_content(tmp_path: Path, text: str) -> None:
    target = tmp_path / "invalid.kicad_pcb"
    target.write_text(text)
    with pytest.raises(ValueError):
        helper.compare(BOARD, target)
