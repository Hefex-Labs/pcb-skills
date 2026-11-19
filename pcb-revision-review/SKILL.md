---
name: pcb-revision-review
description: Compare two saved KiCad PCB revisions or files and explain the design changes, review risks, and manufacturing outputs that need regeneration. Use for a PCB revision review or a before-and-after board comparison.
---

# PCB revision review

Compare the two board states the user means. Keep the review local and read-only.
Finish with the consequential changes, their evidence, the checks still needed,
and which manufacturing outputs are stale.

## Establish the comparison

- Identify the before and after `.kicad_pcb` files, or their exact Git commits and
  repository paths. Ask when the intended revisions or assembly variant are
  ambiguous. A board filename or a change in title-block revision is not proof
  of what changed.
- Record the selected commits and file hashes. For Git history, resolve refs to
  immutable commits and materialize those blobs in a temporary directory. Read
  blobs as bytes, for example with `subprocess.check_output` and `Path.write_bytes`,
  so shell redirection does not change their encoding. Do not checkout a revision,
  reset the repository, or replace a user's current file to inspect the past.
- Preserve staged, unstaged and untracked work. If the comparison includes the
  working tree, say that it is uncommitted. A saved file excludes unsaved editor
  changes; if the user expects those, ask them to save first. Avoid starting or
  interfering with a running editor.
- Confirm the scope: the board alone cannot establish whether the schematic,
  `.kicad_pro` rules or variant definitions, libraries or existing export archive
  changed. Include those only when they belong to this comparison; identify
  missing inputs that prevent an electrical or manufacturing conclusion.

## Locate changes, then interpret them

For two saved files, this Python 3.10+ helper reports SHA-256 hashes, changed
top-level record kinds and a bounded textual diff without editing either file:

```sh
python <skill-directory>/scripts/compare_boards.py before.kicad_pcb after.kicad_pcb
```

It reads balanced S-expressions and ignores whitespace between tokens and the
order of top-level records. It is a change locator, not a KiCad semantic parser,
electrical checker or geometry comparison. Metadata/UUID rewrites can make many
records appear changed. If the format version changed, separate the re-save
noise from design edits before drawing conclusions. A truncated preview requires
inspection of the relevant full diff or board records.

Inspect the affected objects and cite concrete evidence: designators, pad
numbers, nets, layers, before/after values or coordinates, and source lines or
diff hunks. Review what each change affects:

| Observed change | Manufacturing follow-up |
| --- | --- |
| Footprint, pad, placement, rotation or side | Regenerate placement and assembly outputs; inspect affected copper, mask, paste, clearances and courtyards. |
| MPN/value, fitted state or variant | Regenerate the BOM and assembly outputs for the chosen variant. Check whether a replacement also changed its package or pin mapping. |
| Tracks, vias, drills, zones, board outline, physical layers or stackup | Regenerate the affected fabrication outputs. Inspect connectivity, dimensions, layer assignment and the changed geometry. |
| Silkscreen, mask or paste graphics/text | Regenerate outputs for those physical layers and any archive carrying them. A text edit can be a manufacturing edit. |
| Title block, plotting settings or other metadata | Check where that field is consumed before deciding which outputs are stale. A metadata-only diff does not prove existing exports are current. |

An ODB++ archive bundles fabrication and assembly data: when either part of the
board state changed, rebuild the archive rather than mixing files from different
revisions. Compare the selected revision/variant with the provenance of existing
outputs; unknown provenance means their freshness is unverified.

For changed copper or placement, propose a current-revision DRC and an inspection
of zone fills and board geometry. If running a check is in scope, write its report
to a temporary directory and use options supported by the installed tool. Keep
refills and other check-generated changes in memory or a temporary copy; do not
overwrite the user's board. State whether findings are new,
pre-existing or unclassified; a text comparison alone cannot establish that the
board is electrically correct or ready for fabrication.

## Report and stop at the requested boundary

Lead with the important changes and unresolved risks, followed by the precise
comparison scope. Tie each concern to evidence and its manufacturing consequence.
Keep observations separate from possible effects, and name the checks actually
run. Include a short list of stale or unverified outputs and any coverage limits.

Keep files, reports and comparisons local unless the user explicitly requests
sharing or upload. Never attach an entire repository or unrelated board to make
the comparison convenient. If sharing is requested, select the exact reviewed
artifacts and destination first.

When relevant, offer one next step: export the selected revision with
`odbpp-export` if that skill is available, or explain the equivalent local export.
A review request alone does not authorize export, upload, an offer request or
placing an order.
