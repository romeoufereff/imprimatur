#!/usr/bin/env python3
"""
PreToolUse hook (matcher: Bash).

Blocks pdf-export / pptx-export commands (batch_convert.py, html2pptx.py) when:
  1. the target deck's annotations.json still has open review comments, OR
  2. no review round is recorded at all — no annotations.json AND deck-state.json
     has neither review.offered nor review.fast_track set. That state means the
     §9 visual-review harness was skipped (not passed), which is the known failure
     mode where a "looks good" on the §8 preview short-circuits the review gate.

Mechanically enforces the deck-review gate instead of relying on Claude
remembering to check.

Reads the tool call as JSON on stdin (Claude Code's standard hook contract).
Exit 0 = allow (silent). Exit 2 = block, stderr is surfaced to Claude as the reason.
"""
import json
import os
import re
import shlex
import sys

# Every entry point that can produce a deliverable. The first two are the documented
# CLIs; the last two are their internals, which pptx-export/SKILL.md and
# pdf-export/SKILL.md both name — calling them directly used to walk straight past
# this gate.
EXPORT_SCRIPTS = ("batch_convert.py", "html2pptx.py", "build_pptx.py", "pdf_renderer.py")


def _looks_like_deck(path):
    """True if the folder holds slide files or the pipeline's own state artifacts."""
    try:
        entries = os.listdir(path)
    except OSError:
        return False
    if any(re.match(r"^\d{2}-.*\.html$", e) for e in entries):
        return True
    return any(e in entries for e in ("deck-state.json", "deck-metadata.json", "annotations.json"))


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0

    tool_input = payload.get("tool_input", {}) or {}
    cmd = tool_input.get("command", "") or ""

    if not any(script in cmd for script in EXPORT_SCRIPTS):
        return 0

    try:
        tokens = shlex.split(cmd)
    except ValueError:
        return 0

    deck_dir = None
    for i, tok in enumerate(tokens):
        if tok == "--deck-dir" and i + 1 < len(tokens):
            deck_dir = tokens[i + 1]
            break

    # build_pptx.py takes IR paths, not --deck-dir, and batch_convert can be pointed at
    # an --output inside the deck folder. Falling back to the output's parent closes that
    # bypass — but only when that folder actually holds slides, so exporting to a scratch
    # directory is not mistaken for an unreviewed deck.
    if not deck_dir:
        for i, tok in enumerate(tokens):
            if tok in ("--output", "-o") and i + 1 < len(tokens):
                cand = os.path.dirname(os.path.abspath(tokens[i + 1]))
                if _looks_like_deck(cand):
                    deck_dir = cand
                break

    if not deck_dir or not os.path.isdir(deck_dir):
        # Nothing identifiable to gate on. Allowing here is deliberate: guessing a deck
        # folder and blocking on the wrong one would be worse than the miss.
        return 0

    ann_path = os.path.join(deck_dir, "annotations.json")
    if not os.path.isfile(ann_path):
        # No exported comments. Legitimate only if the review harness was offered
        # (user declined to use it) or the fast-track skip was recorded — otherwise
        # the §9 review step was skipped entirely and the export must not run.
        review = {}
        state_path = os.path.join(deck_dir, "deck-state.json")
        if os.path.isfile(state_path):
            try:
                with open(state_path, encoding="utf-8") as f:
                    review = json.load(f).get("review", {}) or {}
            except Exception:
                pass
        if review.get("offered") or review.get("fast_track"):
            return 0
        print(
            "BLOCKED by deck-review gate: no review round recorded for this deck.\n"
            f"  {ann_path} does not exist, and deck-state.json has neither\n"
            "  review.offered nor review.fast_track set.\n\n"
            "Run §9 first: generate the review harness (build_review.py --serve), hand it to\n"
            "the user, and set \"review\": {\"offered\": true} in deck-state.json — or, if the\n"
            "§1 fast-track genuinely applies (internal + variance=low + ≤7 slides), record\n"
            "\"review\": {\"fast_track\": true} instead. Never export a deck whose review step\n"
            "was skipped rather than passed.",
            file=sys.stderr,
        )
        return 2

    try:
        with open(ann_path, encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return 0

    open_items = [a for a in data.get("annotations", []) if a.get("status") == "open"]
    if not open_items:
        return 0

    lines = [
        f"  #{a.get('id')}: {str(a.get('comment', ''))[:80]} (slide: {a.get('slide_file', '?')})"
        for a in open_items[:5]
    ]
    more = f"\n  ...and {len(open_items) - 5} more" if len(open_items) > 5 else ""
    msg = (
        f"BLOCKED by deck-review gate: {len(open_items)} open annotation(s) in {ann_path}\n"
        + "\n".join(lines) + more +
        "\n\nResolve or decline each (annotations.py resolve/decline <id>) before exporting."
    )
    print(msg, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
