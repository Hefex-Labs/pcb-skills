"""Board inventory checks and a native KiCad smoke test when its CLI is present."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "pcb-preflight/scripts/inspect_board.py"
SPEC = importlib.util.spec_from_file_location("inspect_board", SCRIPT)
assert SPEC and SPEC.loader
helper = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(helper)
PRACTICE = Path(__file__).parent / "fixtures/practice.kicad_pcb"


class InventoryTests(unittest.TestCase):
    def inspect(self, source: str, **options) -> dict:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "board.kicad_pcb"
            path.write_text(source, encoding="utf-8")
            original = path.read_bytes()
            result = helper.inventory(path, **options)
            self.assertEqual(path.read_bytes(), original)
            self.assertEqual(result["sha256"], hashlib.sha256(original).hexdigest())
            return result

    def test_practice_board(self):
        result = self.inspect(PRACTICE.read_text(encoding="utf-8"))
        self.assertEqual([p["reference"] for p in result["footprints"]], ["J1", "J2"])
        self.assertEqual(result["findings"], [])

    def test_missing_mpn_has_reference_and_uuid(self):
        source = PRACTICE.read_text(encoding="utf-8").replace('"MPN"', '"Internal SKU"', 1)
        result = self.inspect(source)
        self.assertEqual(result["findings"], [{
            "kind": "missing_populated_mpn", "reference": "J1",
            "uuid": "53b319ae-7adb-467f-ad55-0056b7040cf3",
        }])

    def test_placeholder_is_not_an_orderable_mpn(self):
        source = '(kicad_pcb (footprint "R" (property "Reference" "R1") (property "MPN" "TBD")))'
        self.assertEqual(self.inspect(source)["findings"][0]["kind"], "missing_populated_mpn")

    def test_dnp_and_bom_exclusion_are_distinct(self):
        source = '(kicad_pcb (footprint "R" (property "Reference" "R1") (attr dnp)) ' \
                 '(footprint "R" (property "Reference" "R2") (attr exclude_from_bom)))'
        result = self.inspect(source)
        self.assertEqual(result["findings"], [{
            "kind": "excluded_from_bom_needs_assembly_intent", "reference": "R2", "uuid": None,
        }])
        self.assertTrue(result["footprints"][0]["dnp"])

    def test_variant_must_be_exact_and_can_enable_base_dnp_part(self):
        source = '(kicad_pcb (variants (variant (name "Lite"))) ' \
                 '(footprint "R" (property "Reference" "R1") (attr dnp) ' \
                 '(variant (name "Lite") (dnp no))))'
        with self.assertRaisesRegex(ValueError, "Select --variant or --base"):
            self.inspect(source)
        with self.assertRaisesRegex(ValueError, "Unknown variant"):
            self.inspect(source, variant="Typo")
        self.assertEqual(self.inspect(source, base=True)["findings"], [])
        self.assertEqual(self.inspect(source, variant="Lite")["findings"][0]["kind"], "missing_populated_mpn")

    def test_custom_mpn_field_and_conflicting_fields(self):
        source = '(kicad_pcb (footprint "R" (property "Reference" "R1") ' \
                 '(property "Ordering code" "A")))'
        self.assertEqual(self.inspect(source, mpn_fields=("Ordering code",))["findings"], [])
        source = source.replace('(property "Ordering code" "A")',
                                '(property "MPN" "A") (property "Manufacturer_Part_Number" "B")')
        self.assertEqual(self.inspect(source)["findings"][0]["kind"], "conflicting_mpn_fields")

    def test_quoted_text_and_malformed_source(self):
        source = r'(kicad_pcb (footprint "R (0603)" (property "Reference" "R1") (property "MPN" "A\"B")))'
        self.assertEqual(self.inspect(source)["footprints"][0]["mpn_properties"], {"MPN": 'A"B'})
        for invalid in ('(kicad_pcb', '(kicad_pcb "unterminated)', '(kicad_sch)', '(kicad_pcb) extra'):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                self.inspect(invalid)

    def test_command_refuses_an_unknown_variant(self):
        result = subprocess.run([sys.executable, str(SCRIPT), str(PRACTICE), "--variant", "Typo"],
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        self.assertIn("Unknown variant", result.stderr)


class NativeKiCadTests(unittest.TestCase):
    @unittest.skipUnless(os.environ.get("KICAD_CLI") or shutil.which("kicad-cli"), "kicad-cli unavailable")
    def test_removed_trace_is_reported_without_changing_the_source(self):
        cli = os.environ.get("KICAD_CLI") or shutil.which("kicad-cli")
        original = PRACTICE.read_bytes()
        with tempfile.TemporaryDirectory() as directory:
            temporary = Path(directory)
            env = {**os.environ, "KICAD_CONFIG_HOME": str(temporary / "config")}
            source = original.decode("utf-8")
            segment_start = source.index("  (segment ")
            # This fixture's single segment is its final object. Removing it
            # leaves two same-net pads with no copper connection.
            disconnected = source[:segment_start] + ")\n"
            for name, text, expected_open in (("connected", source, False), ("disconnected", disconnected, True)):
                with self.subTest(name=name):
                    board = temporary / f"{name}.kicad_pcb"
                    report = temporary / f"{name}.json"
                    board.write_text(text, encoding="utf-8")
                    before = board.read_bytes()
                    command = [cli, "pcb", "drc", "--format", "json", "--severity-all",
                               "--exit-code-violations", "--output", str(report), str(board)]
                    result = subprocess.run(command, cwd=directory, env=env, capture_output=True, text=True, timeout=90)
                    self.assertIn(result.returncode, (0, 5), result.stdout + result.stderr)
                    data = json.loads(report.read_text(encoding="utf-8"))
                    self.assertEqual(bool(data["unconnected_items"]), expected_open)
                    self.assertEqual(board.read_bytes(), before)
            self.assertEqual(PRACTICE.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
