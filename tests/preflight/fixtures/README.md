# Preflight practice circuit

These fixtures were authored for the tests in this repository. They use KiCad 8
file formats and contain two single-pad connectors, J1 and J2, joined by the net
`/LINK`, KiCad's qualified name for the schematic's local `LINK` label.
The part number `SYNTHETIC-TEST-PAD` is test data.

The native tests exercise three independent checks.

- Removing the board's only trace must produce an unconnected-items DRC finding.
- Removing the schematic wire must produce a `pin_not_connected` ERC finding
  with an item anchor for J2's pin.
- Changing the PCB net name while retaining the schematic must produce a
  `net_conflict` schematic-parity finding with an affected pad anchor.

The baseline asserts absence of these defects. Other native warnings, such as
the custom symbol or footprint not being installed in a library, remain in the
raw reports and do not establish that this synthetic board is ready to build.
The tests do not modify the fixtures. Every injected defect lives in a temporary
copy.

Run `python -m unittest discover -s tests/preflight -v` from the repository root.
Set `KICAD_CLI` if the executable is outside PATH. A missing CLI skips the native
tests. Set `PCB_PREFLIGHT_REQUIRE_NATIVE=1` to make missing native tooling fail a
CI run. `PCB_PREFLIGHT_REPORT_DIR` retains commands, exit codes, stdout/stderr,
input hashes and raw JSON reports in that directory for inspection.

Report keys and defect types follow the KiCad 9 implementation.
[ERC report](https://github.com/KiCad/kicad-source-mirror/blob/9.0/eeschema/erc/erc_report.cpp),
[ERC item types](https://github.com/KiCad/kicad-source-mirror/blob/9.0/eeschema/erc/erc_item.cpp),
[DRC report](https://github.com/KiCad/kicad-source-mirror/blob/9.0/pcbnew/drc/drc_report.cpp),
[parity checks](https://github.com/KiCad/kicad-source-mirror/blob/9.0/pcbnew/drc/drc_test_provider_schematic_parity.cpp)
