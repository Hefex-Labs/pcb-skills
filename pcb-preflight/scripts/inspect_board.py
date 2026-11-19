#!/usr/bin/env python3
"""Inventory saved KiCad board assembly properties without changing the source."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys


TOKEN = re.compile(r'\s*(\(|\)|"(?:\\.|[^"\\])*"|[^()\s"]+)')
MPN_FIELDS = {"mpn", "manufacturerpartnumber", "mfrpartnumber"}
PLACEHOLDERS = {"?", "-", "n/a", "na", "none", "tbd", "unknown"}


def parse(text: str) -> list:
    """Read only S-expression structure. Quoted text is data, never executed."""
    root: list = []
    stack = [root]
    offset = 0
    while offset < len(text):
        match = TOKEN.match(text, offset)
        if match is None:
            if text[offset:].isspace():
                break
            raise ValueError(f"Invalid or unterminated string at character {offset}")
        token = match[1]
        offset = match.end()
        if token == "(":
            node: list = []
            stack[-1].append(node)
            stack.append(node)
        elif token == ")":
            if len(stack) == 1:
                raise ValueError("Unmatched closing parenthesis")
            stack.pop()
        else:
            if token.startswith('"'):
                escapes = {"n": "\n", "r": "\r", "t": "\t"}
                token = re.sub(r"\\(.)", lambda m: escapes.get(m[1], m[1]), token[1:-1])
            stack[-1].append(token)
    if len(stack) != 1 or len(root) != 1 or not isinstance(root[0], list):
        raise ValueError("Incomplete or multiple S-expressions")
    return root[0]


def children(node: list, name: str) -> list[list]:
    return [item for item in node if isinstance(item, list) and item and item[0] == name]


def value(node: list, name: str, default=None):
    entries = children(node, name)
    return entries[0][1] if entries and len(entries[0]) > 1 else default


def normalized(name: str) -> str:
    return re.sub(r"[\s_.-]", "", name.casefold())


def inventory(path: Path, *, variant: str | None = None, base: bool = False,
              mpn_fields: tuple[str, ...] = ()) -> dict:
    raw = path.read_bytes()
    board = parse(raw.decode("utf-8-sig"))
    if not board or board[0] != "kicad_pcb":
        raise ValueError("Expected a native .kicad_pcb board")
    groups = children(board, "variants")
    variants = [value(item, "name") for group in groups for item in children(group, "variant")]
    variants = [name for name in variants if isinstance(name, str)]
    if variants and variant is None and not base:
        raise ValueError("Select --variant or --base. Available variants: " + ", ".join(variants))
    if variant is not None and variant not in variants:
        raise ValueError(f"Unknown variant {variant!r}. Available variants: {variants}")
    selected_fields = MPN_FIELDS | {normalized(name) for name in mpn_fields}
    footprints = []
    findings = []
    for footprint in children(board, "footprint") + children(board, "module"):
        if len(footprint) < 2 or not isinstance(footprint[1], str):
            raise ValueError("Footprint has no name")
        properties = {p[1]: p[2] for p in children(footprint, "property")
                      if len(p) > 2 and isinstance(p[1], str) and isinstance(p[2], str)}
        legacy = {p[1]: p[2] for p in children(footprint, "fp_text")
                  if len(p) > 2 and isinstance(p[1], str) and isinstance(p[2], str)}
        reference = properties.get("Reference", legacy.get("reference", ""))
        anchor = {"reference": reference, "uuid": value(footprint, "uuid", value(footprint, "tstamp"))}
        attrs = [a for group in children(footprint, "attr") for a in group[1:]]
        dnp = "dnp" in attrs
        mpn_assessment = "board_properties"
        matched_variant = [v for v in children(footprint, "variant")
                           if variant is not None and value(v, "name") == variant]
        for override in matched_variant:
            dnp_override = value(override, "dnp")
            if dnp_override is not None and dnp_override not in ("yes", "no"):
                raise ValueError(f"Invalid DNP override for {reference!r} in variant {variant!r}")
            if dnp_override in ("yes", "no"):
                dnp = dnp_override == "yes"
            if any(isinstance(v, list) and v and v[0] not in {"name", "dnp"} for v in override):
                mpn_assessment = "unassessed_variant_properties"
                findings.append({"kind": "variant_properties_need_review", **anchor})
        mpn_properties = {k: v for k, v in properties.items() if normalized(k) in selected_fields}
        identifiers = sorted({v.strip() for v in mpn_properties.values()
                              if v.strip() and v.strip().casefold() not in PLACEHOLDERS})
        if mpn_assessment == "board_properties" and len(identifiers) > 1:
            findings.append({"kind": "conflicting_mpn_fields", **anchor, "properties": mpn_properties})
        excluded = "exclude_from_bom" in attrs
        if excluded and not dnp:
            findings.append({"kind": "excluded_from_bom_needs_assembly_intent", **anchor})
        if mpn_assessment == "board_properties" and not dnp and not excluded and not identifiers:
            findings.append({"kind": "missing_populated_mpn", **anchor})
        if not reference or reference.endswith("**"):
            findings.append({"kind": "unassigned_reference", **anchor})
        positions = children(footprint, "at")
        footprints.append({
            **anchor, "footprint": footprint[1], "layer": value(footprint, "layer"),
            "position": positions[0][1:] if positions else None,
            "dnp": dnp, "excluded_from_bom": excluded, "mpn_properties": mpn_properties,
            "mpn_assessment": mpn_assessment,
        })
    return {
        "schema": "pcb-preflight-inventory-v1", "source": str(path.resolve()),
        "sha256": hashlib.sha256(raw).hexdigest(), "board_format": value(board, "version"),
        "assembly_variant": variant, "available_variants": variants,
        "scope": "Saved board properties only. Electrical, layout and schematic parity checks require KiCad.",
        "footprints": footprints, "findings": findings,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("board", type=Path)
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument("--variant")
    selection.add_argument("--base", action="store_true", help="Explicitly review base assembly state")
    parser.add_argument("--mpn-field", action="append", default=[], help="Additional manufacturer MPN property")
    args = parser.parse_args()
    try:
        result = inventory(args.board, variant=args.variant, base=args.base, mpn_fields=tuple(args.mpn_field))
    except (OSError, UnicodeError, ValueError) as exc:
        print(f"Board inventory unavailable: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
