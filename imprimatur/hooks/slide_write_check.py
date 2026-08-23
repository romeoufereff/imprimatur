#!/usr/bin/env python3
"""
PostToolUse hook (matcher: Write|Edit).

Whenever a deck slide file (NN-slug.html, e.g. 01-cover.html) is written or
edited, automatically:
  1. Fixes font paths for the whole deck folder (idempotent, cheap) —
     fix_font_paths.py, the manual step that used to run once per deck.
  2. Runs mechanical QA on the slide that just changed — qa.py
     (validate.py + check_contrast.py + check_overflow.py).

Both scripts audit against whichever design system is active, so this hook stays
correct when the design-system folder is swapped.

Reads the tool call as JSON on stdin. Always exits 0 — this hook informs
(prints the QA report to stdout), it never blocks.
"""
import json
import os
import re
import subprocess
import sys

# The engine lives beside this hook inside the plugin. CLAUDE_PLUGIN_ROOT is set by
# Claude Code for plugin hooks; the relative fallback keeps the hook working when it
# is run directly (tests, or a manual settings.json registration).
PLUGIN_ROOT = os.environ.get(
    "CLAUDE_PLUGIN_ROOT",
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)
SCRIPTS = os.path.join(PLUGIN_ROOT, "scripts")


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0

    file_path = payload.get("tool_input", {}).get("file_path", "") or ""
    if not re.match(r"^\d{2}-.*\.html$", os.path.basename(file_path)):
        return 0
    if not os.path.isfile(file_path):
        return 0

    deck_dir = os.path.dirname(file_path)

    if not os.path.isdir(SCRIPTS):
        return 0  # engine not where we expect it — inform-only hook, stay silent

    subprocess.run(
        [
            sys.executable,
            os.path.join(SCRIPTS, "fix_font_paths.py"),
            "--deck-dir", deck_dir,
        ],
        capture_output=True, text=True,
    )

    result = subprocess.run(
        [sys.executable, os.path.join(SCRIPTS, "qa.py"), file_path],
        capture_output=True, text=True,
    )
    if result.stdout:
        print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, file=sys.stderr, end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
