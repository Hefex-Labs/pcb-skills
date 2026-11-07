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
| Altium | Ask the user to start Altium and wait until its main window is up. `run.ps1` refuses to start without it: started by a script, Altium once came up without any window and accepted no script. | The script runs in the open instance. Only one script can run at a time; a modal dialog blocks it. The export uses the **saved** files: unsaved edits are not in it (see A4). |

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
- Start every script through `run.ps1` from the kit (A4), from PowerShell. Do not call
  `X2.EXE` from Git Bash or cmd: they mangle the quotes of the `RunScript` argument, and
  Altium then starts a second instance that only reports "another instance is running,
  but it is busy".
- One run at a time: `run.ps1` refuses to start while a dialog is open or several
  Altium processes run, sends `X2.EXE -REditScript:Stop` (clears a script paused after
  an error, harmless otherwise), starts exactly one run and waits for its status file.
  Never start a second run while the first may still be working, and never retry blindly.
- Dialogs belong to the user. Report their title and text and ask the user to close them;
  do not click them away, least of all ones with a real choice (project location,
  version control). Never take screenshots of the whole screen; it shows whatever else
  the user has open.
- Never copy an Altium project folder in the file system to get a test copy: a project
  linked to a server then asks "Location of project files has changed". Use
  Project » Make a Copy in Altium, or work on the project itself with the user's consent.
- If Altium cannot be closed or says another script is executing, a script is paused in
  the debugger: send `X2.EXE -REditScript:Stop` (or the user chooses Run > Stop,
  Ctrl+F3, in the script editor).
- Altium's command-line switches are not officially documented; this flow is tested on
  Altium Designer 26 Standard. If anything behaves differently, stop and tell the user
  instead of experimenting in their running instance.

Writing your own DelphiScript for Altium (only when the kit does not cover a step):
- `Try/Except` catches runtime errors only. An unknown identifier, or a file that cannot
  be opened (I/O error 32: still held by an earlier, stopped run), shows a modal error
  dialog and pauses the script. Check every `DM_*` name before the first run: the
  interfaces are listed in `<Altium>\System\Altium.SDK.Interfaces.dll` as
  `I<Interface>SDK<Method>DispId` (for example `IProjectSDKDMAddProjectVariantDispId`;
  `DM_SupportsVariants` exists only on `IOutputer`, not on `IProject`).
- After an error Altium keeps the script open in its editor and runs that copy, not the
  changed file on disk. Give a corrected script a new file name (and its own `.PrjScr`).
- Open and close the status file for every line, as the kit does; a file kept open by a
  stopped script stays locked until Altium restarts.
- `TIniFile.ReadString` cuts values after 2047 characters; read long OutJob lines as text.

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

### 2a. Do not populate (DNP) and variants

KiCad writes "Do not populate" into the ODB++ archive as the attribute `.no_pop` on
the component (`CMP` line in `steps/pcb/layers/comp_+_top/components` and `comp_+_bot`).
The part stays in the archive; only the flag marks it.

- Variants (KiCad 10 and later) are listed in the board file:
  `(variants (variant (name "Lite")) ...)` near the top of the `.kicad_pcb`. A footprint
  overrides its DNP state per variant with `(variant (name "Lite") (dnp yes))`.
- No variants: export as it is; footprints with the DNP attribute are flagged.
- One or more variants: tell the user which ones exist and ask which to export, or
  whether to export without one (base state). Never guess.
- Pass the name exactly as written in the board file. **`kicad-cli` does not reject an
  unknown variant name**: it silently exports the base state. Compare the name with the
  list first.
- "Exclude from bill of materials" is not in the ODB++ archive at all. If the user
  relies on it to leave parts off, tell them to set "Do not populate" instead.
- If the user wants to change DNP or variants, offer two ways and let them choose:
  explain the steps in KiCad (footprint or symbol properties → "Do not populate"; the
  per-variant state where the user's KiCad version manages variants), or change it by
  script (the KiCad Python module `pcbnew`: `FOOTPRINT.SetDNP`, `BOARD.AddVariant`,
  `FOOTPRINT.AddVariant(name).SetDNP(True)`, then `BOARD.Save`). By script only on their explicit request,
  with KiCad closed, and on a copy first, since it rewrites their board.

Hefex reads `.no_pop` (since 2026-11-06): such parts are neither bought nor placed.
Check it in the quote (section 5).

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

Add `--variant <name>` for the variant the user chose (2a). Defaults (ZIP, millimetres)
are what Hefex expects. Write the archive next to the project or into a temporary
folder, not into the user's version-controlled sources unless they ask.

Afterwards list the components with `.no_pop` (the attribute's index is in the `@`
lines at the top of each `components` file) and show them to the user: these are the
parts that will not be placed.

## A. Altium Designer

Altium has no command line like `kicad-cli`. The export runs as a script inside the
**open** Altium instance, using an output job (OutJob) of the project.

### A1. Preconditions

- Windows, Altium Designer running with no modal dialog open. `X2.EXE` is in
  `C:\Program Files\Altium\<version>\` (take the highest version, or the path of the
  running `X2.exe` process).
- The project file `<Board>.PrjPcb` of the board the user means. If several, ask.

### A2. Install the Hefex kit once

Create `C:\Users\Public\Documents\Hefex\altium\` and put these four files there,
exactly as given: `HefexOdbExport.pas`, `HefexScripts.PrjScr`, `Hefex.OutJob`, `run.ps1`.
They ship with this skill in `altium/`; the Hefex MCP tool `hefex_get_export_guide`
returns them too, in `files`. Replace older copies: a `Hefex.OutJob` without the
`Configuration1_Item1` line exports no copper layers.

### A3. Variants (Not Fitted parts)

Altium keeps "Not Fitted" parts in assembly variants (Project » Variants). Without a
variant, the archive contains every part as fitted. So check first, with
`Action=ListVariants` in `export.ini` (run it as in A4):

```ini
[Export]
Project=C:\full\path\Board.PrjPcb
Action=ListVariants
```

The status file then lists `variants: <n>` and one line per variant,
`variant: <name> | not_fitted: R5,C1 | alternate: <designators>`. Nothing is exported.

- No variants: export without one. If the user mentions parts that should not be
  placed, tell them these need a variant in Altium (see the two ways below).
- One or more variants: show them with their Not Fitted parts and ask which to export,
  or whether to export without one. Never pick one yourself.
- To create or change a variant, offer two ways and let the user choose:
  1. Explain it: Project » Variants → Add Variant, name it, set the parts to Not Fitted
     in its column, OK, save the project. The kit sets the variant for the export.
  2. Do it by script, only on the user's explicit request: `IProject.DM_AddProjectVariant`,
     `IProjectVariant.DM_SetDescription(<name>)`, `DM_AddComponentVariation` with
     `DM_SetPhysicalDesignator`, `DM_SetUniqueId` (the component's `DM_UniqueId`, for
     example `\THOOSRMX`) and `DM_SetVariationKind(eVariation_NotFitted)`, then save the
     project document with `DoFileSave`. The variant's name is its `DM_Description`;
     `DM_Name` only returns `Variant`.

How Altium writes a variant into ODB++ (tested on Altium Designer 26): it does **not**
set `.no_pop`. Every part stays in the archive, and the attribute `.comp_variant_list`
names the variants a part is fitted in, for example `[No_Variations]:HefexTest` for a
fitted part and `[No_Variations]` for a part that is Not Fitted in `HefexTest`. The
values are text strings (`&` lines at the top of the `components` file);
`misc/attrlist` lists all variants in `.variant_list`. A part is Not Fitted in a
variant when that variant is missing from its list. This needs
`IncludeVariantsData=True` in the ODB++ settings, which `Hefex.OutJob` sets.

The archive always carries **all** variants, and it does not record which one is meant:
there is no `.current_variant`, and in the test the components were identical with and
without the variant set in the output job. So the chosen variant must reach Hefex
separately: tell the user, and leave its Not Fitted parts off the quote (section 5).

### A4. Decide the output job and run it exactly once

Write `C:\Users\Public\Documents\Hefex\altium\export.ini`:

```ini
[Export]
Project=C:\full\path\Board.PrjPcb
Action=Export
Variant=
AddOutJob=1
AllowUnsaved=0
```

- `Variant=` the chosen variant's name exactly as listed, empty for none. An unknown
  name stops with `error: variant_not_found <name>` and the list of variants.
- Output job: without a variant, an output job of the project with an enabled ODB++
  output is used as it is (`outjob: existing`; its own variant setting is logged as
  `outjob_variant:`). With a variant, the customer's job is used only if its ODB++
  output already exports that variant. Otherwise the script uses `Hefex.OutJob`
  (`outjob: hefex`) and sets the variant and the ODB++ settings in it before each run;
  it never changes the customer's own output jobs.
- `Hefex.OutJob` is added to the project only with `AddOutJob=1`. Ask the user before
  allowing it ("This adds one output job file to your Altium project and saves the
  project; the board is not changed."). `AddOutJob=0` when the user declined; the
  script then stops with `error: no_odb_outjob` (or `no_odb_outjob_for_variant`).
- Saved state: the export always uses the saved files; unsaved edits are simply not in
  it (tested: a moved but unsaved part kept its saved position). The script's check for
  unsaved documents (`unsaved: <path>`, `error: unsaved_documents`, bypassed by
  `AllowUnsaved=1`) does not see edits in the PCB editor: Altium reports such a PCB as
  not modified. So whenever the user may have been editing, ask whether everything is
  saved before the export, and say that unsaved changes would be missing.

Run it with the kit's runner, from PowerShell, and wait for it to return:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File C:\Users\Public\Documents\Hefex\altium\run.ps1 `
  -ScriptProject C:\Users\Public\Documents\Hefex\altium\HefexScripts.PrjScr `
  -Proc "HefexOdbExport.pas>ExportOdb" `
  -StatusFile C:\Users\Public\Documents\Hefex\altium\export_status.txt
```

It prints the status file. Exit codes: `0` done, `1` the script logged `error:`, `2` a
dialog is open in Altium (title and text are printed: ask the user to close it), `3`
timeout (ask the user to look at Altium), `4` several Altium processes run (ask the user
to close the extra ones), `5` the status file is locked (Altium must be restarted),
`6` Altium is not running or has no main window yet (ask the user to start it).
After `2`, `3` or `5` ask the user before the next attempt; never loop.

### A5. Find the archive and check it

Altium writes `Project Outputs for <project>\<output name>\` in the project folder (the
`output_folder` line names it). Take the newest `*.zip` there, for example
`ODB\PCB1.zip`; Altium also writes a `.tgz` and the unpacked folder. Before uploading,
check and tell the user about:

- copper: `steps/pcb/layers/` must contain `top_layer` and `bottom_layer` (and the inner
  layers of a multilayer board). Without them the output job has no ODB++ settings:
  re-install `Hefex.OutJob` (A2);
- the variant: when one was exported, list the parts that are Not Fitted in it (A3) and
  have the user confirm them;
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
6. Parts that are not populated:
   - KiCad (`.no_pop`): Hefex leaves them off by itself. Check that none of them is in
     the quote; if one is, set it as below.
   - Altium Not Fitted in the exported variant: Hefex does not read variants yet, so
     these parts are in the quote. With the user's consent, set each of them to `dnp`
     with `hefex_set_part_override` (MPN as described for that tool).
   Then quote again until `search_pending` is 0.
7. Point the user to the project's `portal_url` for what only the portal does: confirming
   the PCB and the parts, requesting and accepting the offer.

Without the MCP server: tell the user where the archive is and that they can upload it at
https://prototyping.hefex-labs.com.
