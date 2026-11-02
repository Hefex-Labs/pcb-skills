---
name: odbpp-export
description: Export a KiCad or Altium Designer PCB as an ODB++ archive for a Hefex Labs PCBA quote or order. Use when the user wants to quote, order or upload a KiCad or Altium board to Hefex, or asks for an ODB++ export.
---

# ODB++ export for Hefex (KiCad, Altium Designer)

Hefex reads one ODB++ archive per board: outline, layers, placements and BOM all come
from it. No separate Gerber, pick-and-place or BOM files are needed.

Which tool: a `.kicad_pcb` or `.kicad_pro` means KiCad (sections 1 to 4), a `.PrjPcb` means
Altium Designer (section A). Section 0 (state of the tool) and section 5 (hand-over to
Hefex) apply to both.

## 0. Before the export: state of the EDA tool

Check this first, tell the user what you found, and never act around the user's
running session. Exporting the wrong state or fighting a busy tool is the main
source of friction.

| | Tool closed | Tool open |
|---|---|---|
| KiCad | `kicad-cli` reads the saved `.kicad_pcb`; nothing else is needed. | Still works on the **saved** file only: unsaved edits in the editor are not exported. A lock file `~<board>.kicad_pcb.lck` next to the board means it is open. |
| Altium | The export command starts Altium itself, opens the project and exports (about 40 s, more on a first start with sign-in or licence dialogs). | The script runs in the open instance. Only one script can run at a time; a modal dialog blocks it. Unsaved documents are refused unless allowed (see A3). |

KiCad, always:
- If a lock file exists, ask the user to save the board (and to refill zones with `B`
  if copper pours changed) before exporting.
- Never write into the project folder except the export archive the user agreed to;
  put DRC reports in a temporary folder. Do not use `--save-board`: it rewrites the
  user's board.
- `kicad-cli pcb drc --refill-zones` checks with fresh zones but does not change the
  file or the export; mention stale zones if DRC reports them.

Altium, always:
- Ask whether the user is working in Altium right now. Do not start the export while
  they are in the middle of a session or while a dialog is open; ask them to close it.
- One run at a time: send `X2.EXE -REditScript:Stop` before each run (it clears a script
  paused after an error, and is harmless otherwise), start exactly one run and wait for
  its status file. Never start a second run while the first may still be working, and
  never retry blindly.
- If Altium cannot be closed or says another script is executing, a script is paused in
  the debugger: send `X2.EXE -REditScript:Stop` (or the user chooses Run > Stop,
  Ctrl+F3, in the script editor).
- Altium's command-line switches are not officially documented; this flow is tested on
  Altium Designer 26 Standard. If anything behaves differently, stop and tell the user
  instead of experimenting in their running instance.

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

## A. Altium Designer

Altium has no command line like `kicad-cli`. The export runs as a script inside the
**open** Altium instance, using an output job (OutJob) of the project.

### A1. Preconditions

- Windows, Altium Designer running with no modal dialog open. `X2.EXE` is in
  `C:\Program Files\Altium\<version>\` (take the highest version, or the path of the
  running `X2.exe` process).
- The project file `<Board>.PrjPcb` of the board the user means. If several, ask.

### A2. Install the Hefex kit once

Create `C:\Users\Public\Documents\Hefex\altium\` and put these three files there,
exactly as given: `HefexOdbExport.pas`, `HefexScripts.PrjScr`, `Hefex.OutJob`. They ship
with this skill in `altium/`; the Hefex MCP tool `hefex_get_export_guide` returns them
too, in `files`.

### A3. Decide the output job

The script first looks for an output job in the project with an enabled ODB++ output
and uses it. Only if there is none does it add `Hefex.OutJob` to the project and save
the project, and only when allowed. Ask the user before allowing it ("This adds one
output job file to your Altium project and saves the project; the board is not
changed."). Then write `C:\Users\Public\Documents\Hefex\altium\export.ini`:

```ini
[Export]
Project=C:\full\path\Board.PrjPcb
AddOutJob=1
AllowUnsaved=0
```

`AddOutJob=0` when the user declined; the script then stops with `error: no_odb_outjob`.
With unsaved documents the script lists them (`unsaved: <path>`) and stops with
`error: unsaved_documents`: ask the user to save, or set `AllowUnsaved=1` only if they
explicitly want the unsaved state exported.

### A4. Run it exactly once

Altium runs one script at a time. A script that hit an error stays paused in the
debugger; every later script is then refused ("another script is executing") and Altium
cannot be closed. So always in this order, and never start a second run while one may
still be working:

1. Clear a paused script: `X2.EXE -REditScript:Stop`, wait 3 seconds.
2. Delete an old `export_status.txt`, then start the export once:
   `X2.EXE -RScriptingSystem:RunScript(ProjectName="C:\Users\Public\Documents\Hefex\altium\HefexScripts.PrjScr"|ProcName="HefexOdbExport.pas>ExportOdb")`
3. Poll `export_status.txt` every few seconds, up to 3 minutes, until it contains `done`
   or a line starting with `error:`. Start nothing else meanwhile.
4. If nothing happens or Altium shows a dialog, ask the user to look at Altium and close
   the dialog; then send step 1 again before any new attempt.

### A5. Find the archive and check it

Altium writes `Project Outputs for <project>\<output name>\` in the project folder (the
`output_folder` line names it). Take the newest `*.zip` there, for example
`ODB\PCB1.zip`; Altium also writes a `.tgz` and the unpacked folder. Before uploading,
tell the user about:

- reference designators that are not annotated (containing `?`, for example `J?`):
  annotate in Altium first;
- components whose part number parameter is missing or holds a value such as `100nF`:
  they are priced by value and footprint at best, or not at all.

Both can be read from `steps/pcb/layers/comp_+_top/components` (and `comp_+_bot`) in
the archive: `CMP` lines carry the reference designator, `PRP` lines the part number
properties.

## 5. Hand over to Hefex

With the Hefex MCP server connected (tools named `hefex_*`):

1. `hefex_create_project` with the board's name (for example the `.kicad_pcb` file name
   without extension). Skip this if the user names an existing Hefex project; find it with
   `hefex_list_projects`.
2. `hefex_get_upload_command` with the project id and the archive's file name (for Altium
   the zip, for example `PCB1.zip`).
3. Run the returned command (`command_windows` on Windows, else `command_posix`) in the
   folder that holds the archive. The link works once and expires after 15 minutes; on
   any failure ask for a new command instead of retrying the old one.
4. Poll `hefex_get_parse_status` every few seconds until `status` is `done` or `failed`.
   On `failed`, show `error_message` and stop.
5. Ask the user for the quantity (boards to fabricate; assembled boards default to all of
   them), then `hefex_get_quote` with `price_if_missing=true` and `hefex_check_parts`.
   Report the total, and every part that is not in stock with the suggested alternatives.
6. Point the user to the project's `portal_url` for what only the portal does: confirming
   the PCB and the parts, requesting and accepting the offer.

Without the MCP server: tell the user where the archive is and that they can upload it at
https://prototyping.hefex-labs.com.
