"""Read-only change locator for two saved KiCad PCB files; prints JSON."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import difflib
import hashlib
from itertools import islice
import json
from pathlib import Path
import re

TOKEN = re.compile(r'"(?:\\.|[^"\\])*"|[()]|[^\s()"]+')


def records(text: str) -> dict[str, Counter]:
    """Compare top-level token records; make no claim about KiCad semantics."""
    text = text.removeprefix("\ufeff")
    tokens = []
    cursor = 0
    for match in TOKEN.finditer(text):
        if text[cursor:match.start()].strip():
            raise ValueError("Unrecognized or unterminated token")
        tokens.append(match.group())
        cursor = match.end()
    if text[cursor:].strip() or tokens[:2] != ["(", "kicad_pcb"]:
        raise ValueError("Expected a saved KiCad PCB S-expression")
    result = defaultdict(Counter)
    depth = 1
    start = None
    for index in range(2, len(tokens)):
        token = tokens[index]
        if token == "(":
            if depth == 1:
                start = index
            depth += 1
        elif token == ")":
            depth -= 1
            if depth == 1 and start is not None:
                record = tuple(tokens[start:index + 1])
                if len(record) < 3 or record[1] in {"(", ")"}:
                    raise ValueError("Malformed board record")
                result[record[1]][record] += 1
            elif depth == 0 and index != len(tokens) - 1:
                raise ValueError("Content after the PCB root")
            elif depth < 0:
                raise ValueError("Unbalanced board expression")
        elif depth == 1:
            raise ValueError("Unexpected atom outside a board record")
    if depth != 0:
        raise ValueError("Unbalanced board expression")
    return dict(result)


def compare(before: Path, after: Path, max_diff_lines: int = 120) -> dict:
    if max_diff_lines < 0:
        raise ValueError("max_diff_lines must be nonnegative")
    before_bytes, after_bytes = before.read_bytes(), after.read_bytes()
    before_text, after_text = before_bytes.decode("utf-8"), after_bytes.decode("utf-8")
    old, new = records(before_text), records(after_text)
    changed = []
    for kind in sorted(old.keys() | new.keys()):
        prior, current = old.get(kind, Counter()), new.get(kind, Counter())
        if prior != current:
            changed.append({
                "kind": kind, "before": prior.total(), "after": current.total(),
                "removed_records": (prior - current).total(), "added_records": (current - prior).total(),
            })
    preview = list(islice(difflib.unified_diff(
        before_text.splitlines(), after_text.splitlines(), fromfile="before", tofile="after", lineterm="",
    ), max_diff_lines + 1))
    return {
        "before": {"path": str(before.resolve()), "sha256": hashlib.sha256(before_bytes).hexdigest()},
        "after": {"path": str(after.resolve()), "sha256": hashlib.sha256(after_bytes).hexdigest()},
        "raw_bytes_equal": before_bytes == after_bytes,
        "normalized_record_content_equal": not changed,
        "record_changes": changed,
        "diff_preview": preview[:max_diff_lines], "diff_truncated": len(preview) > max_diff_lines,
        "scope": "Top-level token records only; no electrical or geometry validation.",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("before", type=Path)
    parser.add_argument("after", type=Path)
    parser.add_argument("--max-diff-lines", type=int, default=120)
    arguments = parser.parse_args()
    try:
        report = compare(arguments.before, arguments.after, arguments.max_diff_lines)
    except (OSError, ValueError) as error:
        parser.exit(1, f"{error}\n")
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
