---
name: odbpp-export
description: Export a KiCad PCB as an ODB++ archive for a Hefex Labs PCBA quote or order. Use when the user wants to quote, order or upload a KiCad board to Hefex, or asks for an ODB++ export.
---

# ODB++ export from KiCad

Hefex reads one ODB++ archive per board: outline, layers, placements and BOM all come
from it. No separate Gerber, pick-and-place or BOM files are needed.

## 1. Find `kicad-cli`

Try `kicad-cli version` first. If it is not on the PATH, look here:

| OS | Path |
|---|---|
| Windows | `C:\Program Files\KiCad\<version>\bin\kicad-cli.exe` (take the highest version) |
| macOS | `/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli` |
| Linux | `kicad-cli` from the KiCad package |

If `kicad-cli pcb export odb --help` fails, the KiCad version has no ODB++ export. Tell the
user to update KiCad or to export ODB++ from the PCB editor (File → Fabrication Outputs).

## 2. Pick the board

- Use the `.kicad_pcb` in the project the user is working on. If there are several, ask.
- If the project uses assembly variants, ask which one to export.

## 3. Check before export

Run the design rules check and report errors to the user before going on:

```bash
kicad-cli pcb drc --severity-error --exit-code-violations -o drc.rpt board.kicad_pcb
```

A non-zero exit code means violations. Show them and ask whether to continue.

Parts are priced by manufacturer part number. Footprints without an `MPN` field
(also accepted: `Manufacturer_Part_Number`, `MFR_PN`, `Part_Number` and similar) cannot be
priced automatically. Mention any that are missing; the user can fix them in KiCad or
pick parts later in the Hefex portal or through the Hefex MCP tools.

## 4. Export

```bash
kicad-cli pcb export odb -o board-odb.zip board.kicad_pcb
```

Add `--variant <name>` for an assembly variant. Defaults (ZIP, millimetres) are what
Hefex expects. Write the archive next to the project or into a temporary folder, not
into the user's version-controlled sources unless they ask.

## 5. Hand over to Hefex

- With the Hefex MCP server connected: create a project and upload the archive with the
  upload command the server returns, then wait for the parse status.
- Without it: tell the user where the archive is and that they can upload it at
  https://prototyping.hefex-labs.com.
