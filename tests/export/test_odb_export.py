"""Export a synthetic saved board with native KiCad; inspect the actual ODB++ ZIP."""
from __future__ import annotations

import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest
from zipfile import ZipFile, is_zipfile


ROOT = Path(__file__).resolve().parents[2]
PRACTICE = ROOT / "tests/preflight/fixtures/practice.kicad_pcb"
CLI = os.environ.get("KICAD_CLI") or shutil.which("kicad-cli")


@unittest.skipUnless(CLI, "kicad-cli unavailable")
class NativeOdbExportTests(unittest.TestCase):
    def run_cli(self, temporary: Path, *arguments: str) -> subprocess.CompletedProcess:
        result = subprocess.run(
            [CLI, *arguments], cwd=temporary,
            env={**os.environ, "KICAD_CONFIG_HOME": str(temporary / "config")},
            capture_output=True, text=True, timeout=90,
        )
        self.assertEqual(result.returncode, 0, f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}")
        return result

    def export(self, temporary: Path, source: bytes, *options: str, report_name: str = "base") -> Path:
        board = temporary / "board.kicad_pcb"
        board.write_bytes(source)
        archive = temporary / "board-odb.zip"
        self.assertFalse(archive.exists())
        # Use the guide's exact command and defaults, including ZIP and mm.
        result = self.run_cli(temporary, "pcb", "export", "odb", *options, "-o", archive.name, board.name)
        print(f"ODB++ export ({report_name}) stderr:\n{result.stderr}")
        if report_dir := os.environ.get("PCB_EXPORT_REPORT_DIR"):
            reports = Path(report_dir)
            reports.mkdir(parents=True, exist_ok=True)
            version = self.run_cli(temporary, "version").stdout.strip()
            stem = f"kicad-{re.sub(r'[^A-Za-z0-9._-]', '_', version)}-{report_name}"
            (reports / f"{stem}.stdout.txt").write_text(result.stdout, encoding="utf-8")
            (reports / f"{stem}.stderr.txt").write_text(result.stderr, encoding="utf-8")
            shutil.copyfile(archive, reports / f"{stem}.zip")
        self.assertEqual(board.read_bytes(), source, "Export rewrote the saved board")
        self.assertTrue(is_zipfile(archive), "The default export is not a ZIP archive")
        return archive

    def read_member(self, archive: ZipFile, suffix: str) -> str:
        names = [name for name in archive.namelist() if name == suffix or name.endswith("/" + suffix)]
        self.assertEqual(len(names), 1, f"Expected one archive member ending in {suffix!r}")
        return archive.read(names[0]).decode("utf-8")

    def components(self, text: str) -> dict[str, tuple[list[str], str]]:
        records = {}
        for line in text.splitlines():
            if line.startswith("CMP "):
                placement, _, attributes = line.partition(";")
                fields = placement.split()
                self.assertGreaterEqual(len(fields), 8)
                self.assertNotIn(fields[6], records, "Duplicate component reference")
                records[fields[6]] = (fields, attributes)
        self.assertEqual(set(records), {"J1", "J2"})
        return records

    def dnp_references(self, text: str) -> set[str]:
        names = re.findall(r"^@(\d+)\s+\.no_pop\s*$", text, re.MULTILINE)
        self.assertLessEqual(len(names), 1)
        if not names:
            return set()
        attribute = names[0]
        return {
            reference for reference, (_, attributes) in self.components(text).items()
            if any(value.strip() in (attribute, attribute + "=1") for value in attributes.split(","))
        }

    def test_default_export_contains_real_placements_copper_and_outline(self):
        original = PRACTICE.read_bytes()
        with tempfile.TemporaryDirectory() as directory:
            temporary = Path(directory)
            board = temporary / "board.kicad_pcb"
            board.write_bytes(original)
            self.run_cli(temporary, "pcb", "drc", "--severity-error", "--exit-code-violations",
                         "-o", "drc.rpt", str(board))
            self.assertTrue((temporary / "drc.rpt").is_file())
            self.assertEqual(board.read_bytes(), original, "DRC rewrote the saved board")
            with ZipFile(self.export(temporary, original)) as archive:
                self.assertIsNone(archive.testzip(), "An archive member failed its CRC check")
                matrix = self.read_member(archive, "matrix/matrix")
                self.assertRegex(matrix, r"(?s)STEP\s*\{[^}]*\bNAME=PCB\b")
                layers = {}
                for block in re.findall(r"LAYER\s*\{([^}]*)\}", matrix):
                    fields = {key: value.strip() for key, value in re.findall(r"^\s*([A-Z_]+)=(.*)$", block, re.MULTILINE)}
                    layers[fields["NAME"].lower()] = fields["TYPE"]
                self.assertEqual(layers["f.cu"], "SIGNAL")
                self.assertEqual(layers["b.cu"], "SIGNAL")
                self.assertEqual(layers["f.mask"], "SOLDER_MASK")
                self.assertEqual(layers["comp_+_top"], "COMPONENT")
                self.assertIn("UNITS=MM", self.read_member(archive, "misc/info"))

                text = self.read_member(archive, "steps/pcb/layers/comp_+_top/components")
                self.assertIn("UNITS=MM", text)
                placements = self.components(text)
                for reference, x in (("J1", 10.0), ("J2", 20.0)):
                    fields, _ = placements[reference]
                    self.assertEqual((float(fields[2]), float(fields[3])), (x, -10.0))
                    self.assertEqual((float(fields[4]), fields[5]), (0.0, "N"))
                self.assertEqual(text.count("PRP MPN 'SYNTHETIC-TEST-PAD'"), 2)
                self.assertEqual(len(re.findall(r"^TOP ", text, re.MULTILINE)), 2)

                copper = self.read_member(archive, "steps/pcb/layers/f.cu/features")
                self.assertIn("UNITS=MM", copper)
                tracks = [line.split(";", 1)[0].split() for line in copper.splitlines() if line.startswith("L ")]
                self.assertEqual(len(tracks), 1)
                track = tracks[0]
                self.assertEqual({float(track[1]), float(track[3])}, {10.0, 20.0})
                self.assertEqual((float(track[2]), float(track[4])), (-10.0, -10.0))
                symbols = dict(re.findall(r"^\$(\d+)\s+(\S+)", copper, re.MULTILINE))
                self.assertRegex(symbols[track[5]], r"^r[0-9.]+$")
                self.assertAlmostEqual(float(symbols[track[5]][1:]), 300.0)
                self.assertEqual(len(re.findall(r"^P ", copper, re.MULTILINE)), 2)
                profile = self.read_member(archive, "steps/pcb/profile")
                self.assertGreaterEqual(len(re.findall(r"^O[BS] ", profile, re.MULTILINE)), 4)
            self.assertEqual(PRACTICE.read_bytes(), original)

    def test_dnp_keeps_the_component_and_marks_only_its_placement(self):
        original = PRACTICE.read_bytes()
        self.assertEqual(original.count(b"(attr smd)"), 2)
        dnp = original.replace(b"(attr smd)", b"(attr smd dnp)", 1)
        with tempfile.TemporaryDirectory() as directory:
            with ZipFile(self.export(Path(directory), dnp, report_name="dnp")) as archive:
                self.assertIsNone(archive.testzip())
                text = self.read_member(archive, "steps/pcb/layers/comp_+_top/components")
                self.components(text)
                self.assertEqual(self.dnp_references(text), {"J1"}, "The DNP flag must apply only to J1")
            self.assertEqual(PRACTICE.read_bytes(), original)

    def test_named_variant_changes_only_the_requested_population_state(self):
        original = PRACTICE.read_bytes()
        with tempfile.TemporaryDirectory() as directory:
            temporary = Path(directory)
            help_text = self.run_cli(temporary, "pcb", "export", "odb", "--help").stdout
            if "--variant" not in help_text:
                self.skipTest("This KiCad CLI does not advertise ODB++ --variant")
            # These are KiCad 10's saved-board variant records. The fixture's
            # base state stays populated, while the named variant marks J1 DNP.
            source = original.replace(b'(paper "A4")', b'(paper "A4")\n  (variants (variant (name "Lite")))', 1)
            source = source.replace(b"(attr smd)", b'(attr smd)\n    (variant (name "Lite") (dnp yes))', 1)
            for name, options, expected in (("base", (), set()), ("lite", ("--variant", "Lite"), {"J1"})):
                with self.subTest(export=name):
                    output = temporary / name
                    output.mkdir()
                    with ZipFile(self.export(output, source, *options, report_name=f"variant-{name}")) as archive:
                        self.assertIsNone(archive.testzip())
                        text = self.read_member(archive, "steps/pcb/layers/comp_+_top/components")
                        self.components(text)
                        self.assertEqual(self.dnp_references(text), expected)
            self.assertEqual(PRACTICE.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
