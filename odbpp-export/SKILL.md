---
name: odbpp-export
description: Export and verify a saved KiCad or Altium Designer board as a local ODB++ archive, including assembly variants, do-not-populate parts and an archive path/hash handoff. Use when asked for an ODB++ export or local manufacturing data.
---

# Export a board as ODB++ (KiCad and Altium Designer)

Export one ODB++ archive for the saved board, including its outline, layers,
placements and component properties.

Which tool: a `.kicad_pcb` or `.kicad_pro` means KiCad (sections 1 to 4), a `.PrjPcb` means
Altium Designer (section A). Start with section 0 for either tool and finish with the
local handoff in section 5.

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

## 3. Check before export

Run the design rules check from a temporary folder, substituting the absolute saved
board path below. Report errors before going on:

```bash
kicad-cli pcb drc --severity-error --exit-code-violations -o drc.rpt "<absolute path to board.kicad_pcb>"
```

If the report lists violations, show them and ask whether to continue. If the command
failed to read the board or run the check, report the error before treating the board as checked.

Check the footprints' manufacturer part numbers (`MPN`, `Manufacturer_Part_Number`,
`MFR_PN`, `Part_Number` and similar). Report missing or placeholder values with their
reference designators so these component identities can be resolved before assembly.

## 4. Export

```bash
kicad-cli pcb export odb -o board-odb.zip board.kicad_pcb
```

For a named variant (2a), first check `kicad-cli pcb export odb --help` on the
installed version. If it lists `--variant`, pass the exact selected name. If the
option is absent, stop and explain that this CLI cannot select the requested
variant. A base-board export would contain a different assembly. The defaults are ZIP
and millimetres. Use an agreed output directory outside version
control unless the user asks otherwise.

Use a fresh output path so an earlier build cannot pass for this one. After the
CLI succeeds, open the ZIP read-only, test its CRCs, and locate `matrix/matrix`
and the expected board step under `steps/` inside the archive. Check that its
copper layers match the saved board. A missing step, layer or unreadable member
is an incomplete export. Report the saved board, variant,
archive path and SHA-256 together so the user can identify the exact handoff.

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
They ship with this skill in `altium/`, maintained in
[Hefex-Labs/pcb-skills](https://github.com/Hefex-Labs/pcb-skills/tree/main/odbpp-export/altium).

Replace older copies: a `Hefex.OutJob` without the
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

The tested archive carries **all** variants, and it does not record which one is meant:
there is no `.current_variant`, and in the test the components were identical with and
without the variant set in the output job. Record the chosen variant and its Not Fitted
designators separately in the local handoff (section 5).

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

Altium writes `Project Outputs for <project>\<output name>\` in the project folder.
Before running the export, note existing ZIPs for that project. After it succeeds,
use the `output_folder` from this run to identify the board ZIP it created or
rewrote, for example `ODB\PCB1.zip`. If the output is ambiguous, resolve which
file belongs to the run before handing it over. Altium also writes a `.tgz` and an
unpacked folder. Open the ZIP read-only, test its CRCs, record its SHA-256 with
the board and variant, locate `matrix/matrix` and the expected board step under
`steps/`, and check the following entries.

- copper: `steps/pcb/layers/` must contain `top_layer` and `bottom_layer` (and the inner
  layers of a multilayer board). Without them the output job has no ODB++ settings:
  re-install `Hefex.OutJob` (A2);
- the variant: when one was exported, list the parts that are Not Fitted in it (A3) and
  have the user confirm them;
- reference designators that are not annotated (containing `?`, for example `J?`):
  annotate in Altium first;
- components whose part number parameter is missing or holds a value such as `100nF`:
  report the affected designators so their component identities can be resolved.

Read the designators and part numbers from `steps/pcb/layers/comp_+_top/components`
(and `comp_+_bot`) in the archive. `CMP` lines carry the reference designator, and
`PRP` lines carry the part number properties.

## 5. Local handoff

Report the following together after verification:

- The saved board or project path, its revision if known, and the EDA tool version.
- The exact chosen variant, or the base state when no named variant was selected.
- The archive's absolute path and SHA-256.
- The not-fitted reference designators for that selection, from KiCad's `.no_pop`
  attributes or Altium's variant membership. State when the list is empty.
- The CRC, matrix, board-step and copper-layer checks, plus unresolved design-rule
  findings or missing part numbers.

Keep the selected variant and not-fitted list alongside the archive even when the
archive omits the active variant. Resolve a mismatch between that selection and the
exported assembly before reporting the handoff as complete.

## Optional continuation with Hefex MCP

If the user asks to continue with Hefex MCP, pass this local handoff to the connected
assistant. For example, “Use this verified ODB++ archive with Hefex, keeping the chosen
variant and not-fitted designators from the handoff.” The MCP guide can also return
the export kit files directly.
