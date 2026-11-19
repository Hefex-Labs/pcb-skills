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
SCHEMATIC = PRACTICE.with_suffix(".kicad_sch")
J2_PIN = "92f96235-9f05-475f-a68b-dd23a12a8a50"


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

    def test_variant_properties_leave_mpn_assessment_unresolved(self):
        for base_properties in ("", '(property "MPN" "A") (property "Manufacturer_Part_Number" "B")'):
            source = '(kicad_pcb (variants (variant (name "Lite"))) ' \
                     '(footprint "R" (property "Reference" "R1") ' + base_properties + \
                     '(variant (name "Lite") (property "MPN" "VARIANT-PART"))))'
            result = self.inspect(source, variant="Lite")
            self.assertEqual([f["kind"] for f in result["findings"]], ["variant_properties_need_review"])
            self.assertEqual(result["footprints"][0]["mpn_assessment"], "unassessed_variant_properties")

    def test_invalid_variant_dnp_refuses_an_assembly_inference(self):
        source = '(kicad_pcb (variants (variant (name "Lite"))) ' \
                 '(footprint "R" (property "Reference" "R1") (variant (name "Lite") (dnp maybe))))'
        with self.assertRaisesRegex(ValueError, "Invalid DNP override"):
            self.inspect(source, variant="Lite")

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
    def setUp(self):
        self.cli = os.environ.get("KICAD_CLI") or shutil.which("kicad-cli")
        if not self.cli:
            if os.environ.get("PCB_PREFLIGHT_REQUIRE_NATIVE") == "1":
                self.fail("Native checks required but kicad-cli is unavailable")
            self.skipTest("kicad-cli unavailable")
        report_root = os.environ.get("PCB_PREFLIGHT_REPORT_DIR")
        if report_root:
            report_root = Path(report_root).resolve()
            report_root.mkdir(parents=True, exist_ok=True)
            self.directory = Path(tempfile.mkdtemp(prefix=self._testMethodName + "-", dir=report_root))
        else:
            temporary = tempfile.TemporaryDirectory()
            self.addCleanup(temporary.cleanup)
            self.directory = Path(temporary.name)
        self.env = {**os.environ, "KICAD_CONFIG_HOME": str(self.directory / "config")}
        self.originals = {path: path.read_bytes() for path in (PRACTICE, SCHEMATIC)}
        self.addCleanup(self.check_originals)

    def check_originals(self):
        for path, original in self.originals.items():
            self.assertEqual(path.read_bytes(), original, str(path))

    def run_check(self, group: list[str], source: Path, name: str, *options: str) -> dict:
        report = self.directory / f"{name}.json"
        before = source.read_bytes()
        command = [self.cli, *group, "--format", "json", "--severity-all",
                   "--exit-code-violations", "--output", str(report), *options, str(source)]
        result = subprocess.run(command, cwd=source.parent, env=self.env,
                                capture_output=True, text=True, timeout=90)
        metadata = {"command": command, "exit_code": result.returncode,
                    "input_sha256": hashlib.sha256(before).hexdigest(),
                    "input_unchanged": source.read_bytes() == before}
        (self.directory / f"{name}-command.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
        (self.directory / f"{name}-stdout.txt").write_text(result.stdout, encoding="utf-8")
        (self.directory / f"{name}-stderr.txt").write_text(result.stderr, encoding="utf-8")
        self.assertEqual(source.read_bytes(), before)
        self.assertIn(result.returncode, (0, 5), result.stdout + result.stderr)
        self.assertTrue(report.is_file(), "No native report. See command stdout/stderr.")
        return json.loads(report.read_text(encoding="utf-8"))

    def test_removed_trace_is_reported_without_changing_the_source(self):
        original = PRACTICE.read_bytes()
        source = original.decode("utf-8")
        segment_start = source.index("  (segment ")
        # This fixture's single segment is its final object. Removing it
        # leaves two same-net pads with no copper connection.
        disconnected = source[:segment_start] + ")\n"
        for name, text, expected_open in (("connected", source, False), ("disconnected", disconnected, True)):
            with self.subTest(name=name):
                board = self.directory / f"{name}.kicad_pcb"
                board.write_text(text, encoding="utf-8")
                data = self.run_check(["pcb", "drc"], board, name)
                self.assertEqual(bool(data["unconnected_items"]), expected_open)

    def test_removed_schematic_wire_has_an_erc_pin_anchor(self):
        source = SCHEMATIC.read_text(encoding="utf-8")
        wire_start = source.index("  (wire ")
        wire_end = source.index("  (label ", wire_start)
        disconnected = source[:wire_start] + source[wire_end:]
        for name, text, expected_open in (("connected", source, False), ("disconnected", disconnected, True)):
            with self.subTest(name=name):
                case = self.directory / name
                case.mkdir()
                schematic = case / "practice.kicad_sch"
                schematic.write_text(text, encoding="utf-8")
                data = self.run_check(["sch", "erc"], schematic, name)
                violations = [v for sheet in data["sheets"] for v in sheet["violations"]
                              if v["type"] == "pin_not_connected"]
                self.assertEqual(bool(violations), expected_open)
                if expected_open:
                    anchors = [item["uuid"] for v in violations for item in v["items"]]
                    self.assertIn(J2_PIN, anchors)

    def test_schematic_parity_reports_an_injected_wrong_net(self):
        help_result = subprocess.run([self.cli, "pcb", "drc", "--help"],
                                     capture_output=True, text=True, timeout=15)
        self.assertEqual(help_result.returncode, 0, help_result.stderr)
        if "--schematic-parity" not in help_result.stdout:
            if os.environ.get("PCB_PREFLIGHT_REQUIRE_NATIVE") == "1":
                self.fail("Schematic parity required but unsupported by this KiCad CLI")
            self.skipTest("Installed KiCad CLI does not expose --schematic-parity")
        source = PRACTICE.read_text(encoding="utf-8")
        for name, board_text, expected_conflict in (
            ("matching", source, False),
            ("wrong_net", source.replace('"/LINK"', '"WRONG_LINK"'), True),
        ):
            with self.subTest(name=name):
                case = self.directory / name
                case.mkdir()
                board = case / "practice.kicad_pcb"
                board.write_text(board_text, encoding="utf-8")
                schematic = case / "practice.kicad_sch"
                schematic.write_bytes(SCHEMATIC.read_bytes())
                data = self.run_check(["pcb", "drc"], board, name, "--schematic-parity")
                self.assertEqual(schematic.read_bytes(), SCHEMATIC.read_bytes())
                parity = data["schematic_parity"]
                if not expected_conflict:
                    self.assertEqual(parity, [], parity)
                else:
                    conflicts = [v for v in parity if v["type"] == "net_conflict"]
                    self.assertTrue(conflicts, parity)
                    anchors = [item["uuid"] for v in conflicts for item in v["items"]]
                    self.assertIn("449fa4de-c3ac-4ba0-a22d-8b1ebfc2789a", anchors)


if __name__ == "__main__":
    unittest.main()
