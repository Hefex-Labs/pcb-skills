---
name: pcb-preflight
description: Review a saved KiCad schematic and PCB before fabrication. Run ERC, DRC and supported schematic parity checks, inspect populated part numbers and assembly variants, and report findings with component, net and source evidence. Works locally without a manufacturer account.
---

# PCB preflight

Review the board the user intends to build. Return a short list of concrete
findings, the checks that produced them, and the checks that remain unresolved.
Use this for a review of existing design files, including “check this board
before fab” and “what is missing before I send this for assembly?”

## Establish the source

Locate the saved `.kicad_pcb`, root `.kicad_sch` and matching `.kicad_pro`, plus
local libraries and `.kicad_dru` when present. If multiple boards or schematic
roots are plausible, establish which one the user means. Record their paths,
revision or file hashes, KiCad version, assembly variant and any stated voltage,
current, mechanical or fabrication requirements.

Check for an active editor or lock file. The CLI reads saved files. If unsaved
work matters, have the user save it before reviewing. Keep source files intact
and place reports in a fresh temporary directory outside the project. Review
requests authorize analysis, not edits to the design or an upload.

## Run the available native checks

Find `kicad-cli` on PATH or in the user's existing KiCad installation. Check
`version` and the relevant `--help` before choosing options. Use the installed
tool's behavior and the matching [KiCad CLI documentation](https://docs.kicad.org/)
when versions differ. An unavailable command is an unperformed check.

For a CLI with JSON reports, run the applicable commands with explicit temporary
output paths and absolute input paths.

```sh
kicad-cli sch erc --format json --severity-all --exit-code-violations --output "<temp>/erc.json" "<root>.kicad_sch"
kicad-cli pcb drc --format json --severity-all --exit-code-violations --output "<temp>/drc.json" "<board>.kicad_pcb"
```

When `pcb drc --help` exposes `--schematic-parity` and the board has the matching
schematic in its project, add it to the DRC run. Establish that the schematic was
loaded from the command output and report. A standalone board or unsupported
CLI leaves parity unassessed. For deliberately different schematic and PCB file
names, establish the intended project association before claiming parity.

Use `--refill-zones` when supported to check fresh copper fills in memory.
Do not use `--save-board`, which saves the checked board. State whether the check
used saved zone fills or fresh fills. Preserve project exclusions in the report
and distinguish excluded findings from active errors and warnings.

Read the report even when the command returns a nonzero code. KiCad can return
5 for reported violations. Missing output, an unreadable source, a failed
library load or an unsupported option needs its own explanation. Zero errors
does not establish circuit correctness or manufacturing approval.

## Inspect the assembly intent

The bundled helper uses Python 3.10 or later with the standard library. It
inventories native board properties without changing the file and locates missing
part numbers and DNP flags.

```sh
python "<skill>/scripts/inspect_board.py" "<board>.kicad_pcb"
python "<skill>/scripts/inspect_board.py" "<board>.kicad_pcb" --variant "Lite"
```

If variants are present, the helper requires an exact `--variant` or explicit
`--base`. Establish the user's intended variant before reviewing assembly.
`--mpn-field "<property>"` adds a project-specific manufacturer part number field.
First verify that it contains manufacturer identifiers, rather than internal
article numbers. The helper reports base board properties and recognized DNP
overrides. Other variant attributes require inspection in KiCad or the source.

Cross-check the populated references against the root schematic's BOM and
properties when available. KiCad's native BOM export can provide this evidence
when the installed version supports it. Keep the exact variant, DNP, excluded
part and field choices visible. A board-only inventory cannot establish
schematic agreement or the electrical suitability of a part.

Check these points when the input supports them.

- Identify populated references lacking an exact manufacturer part number,
  conflicting part number fields, and differences between schematic and PCB
  part or footprint assignments. Cite the reference and property.
- List DNP parts and footprints excluded from the BOM. “Exclude from BOM” and
  “do not populate” have different meanings. Establish physical assembly intent
  instead of silently treating one flag as the other.
- Inspect footprint/package, pin 1, polarity, connector orientation and assembly
  side where a datasheet or source drawing provides evidence. A matching pin
  count alone is insufficient. State when manufacturer evidence is absent.
- Read board dimensions, outline/cutouts, layers, stackup and explicit design
  rules. Compare them with supplied requirements or manufacturer limits.
  When limits are absent, report the observed values and what remains to check.

## Examine the findings

Follow a failed check to its component, pad, net, coordinate or source property.
For a circuit question, use the schematic and the relevant manufacturer
datasheet. Label a visual concern or an assumption as such. Avoid inventing a
violation from a generic preference, or calling a library/CLI setup failure a
board defect. Scale a deeper review to the user's request and circuit risks.

Prioritize things that block the intended build, followed by warnings and
unresolved questions. Each finding should say what was observed, where, why it
matters for this board, and what needs review or correction. Recheck the source
hashes at the end so a file changed during the run cannot pass as reviewed.

## Report and handoff

Name the reviewed source and assembly variant, summarize ERC/DRC/parity and
assembly evidence, and give paths to the raw reports. State material gaps beside
the conclusion, such as missing schematic, unavailable CLI, unreviewed excluded
violations or absent manufacturer constraints. A review with unperformed checks
must not be presented as clean.

Examples of focused requests include “Review the saved board and schematic for
an assembly of five Lite variants” and “Run the electrical and layout checks and
show the components I need to fix.”

When the user also requests manufacturing files, hand the identified revision
and variant to `odbpp-export` if available, or the requested EDA export workflow.
An export or quote is a separate action requested by the user. This skill works
offline and does not need a supplier connection or Hefex account.
