#!/usr/bin/env python3
"""
PostToolUse hook (matcher: Write|Edit).

Whenever deck-metadata.json is written/edited, verifies its slide_count against
the actual NN-*.html slide files present in the same folder — catching the exact
drift the orchestrator's own "adding/removing a slide" checklist
warns about (metadata, index.html, and disk falling out of sync).

Reads the tool call as JSON on stdin. Exit 0 = silent (in sync, or nothing to check).
Exit 2 = mismatch found; stderr is surfaced to Claude as a correction nudge.
"""
import json
import os
import re
import sys


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0

    file_path = payload.get("tool_input", {}).get("file_path", "") or ""
    if os.path.basename(file_path) != "deck-metadata.json":
        return 0
    if not os.path.isfile(file_path):
        return 0

    deck_dir = os.path.dirname(file_path)
    try:
        with open(file_path, encoding="utf-8") as f:
            meta = json.load(f)
    except Exception:
        return 0

    declared = meta.get("slide_count")
    if declared is None:
        return 0

    try:
        actual_files = sorted(
            f for f in os.listdir(deck_dir) if re.match(r"^\d{2}-.*\.html$", f)
        )
    except Exception:
        return 0

    actual = len(actual_files)
    if actual == declared:
        return 0

    print(
        f"WARNING: {file_path} declares slide_count={declared} but {deck_dir} "
        f"actually contains {actual} NN-*.html slide file(s) "
        f"({', '.join(actual_files) or 'none'}). Update slide_count, the index.html "
        f"slides array, and any shifted page-number footers before proceeding.",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
