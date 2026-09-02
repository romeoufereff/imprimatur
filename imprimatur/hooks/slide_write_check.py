#!/usr/bin/env python3
"""
PostToolUse hook (matcher: Write|Edit)  —  WP1.

Whenever a deck slide file (NN-slug.html, e.g. 01-cover.html) is written or
edited, runs ONLY the instant static check — validate.py (~0.1s, no browser) —
and reports the verdict back to the model via `additionalContext`, so a
`STATIC FAIL` is fixed before the designer copies the same mistake into the
next slide.

This hook used to also run fix_font_paths.py and the full qa.py (contrast +
overflow + paint — three Chromium launches) on every single Write/Edit. That
cost 7s of browser time per write that NO ONE EVER READ: PostToolUse hooks
that print to stdout are shown in transcript mode only, never fed back to the
model, which is why every designer transcript in the optimization-plan review
showed a manual `qa.py` re-run after every write. The browser checks now run
once per chunk, in one launch, via `render_checks.py` / `qa.py --deck-dir`,
gated at chunk-end by `designer_stop_gate.py` (SubagentStop). Font-path
localisation is now `new_slide.py`'s job per file at creation time, not a
whole-deck rescan after every edit.

Reads the tool call as JSON on stdin. Always exits 0 — this hook informs, it
never blocks (WP1's blocking gate is the SubagentStop hook, not this one).

Verified against the current Claude Code hooks reference (2026-09): PostToolUse
hookSpecificOutput carries NO decision fields, but the universal top-level
`additionalContext` field IS supported on PostToolUse and reaches the model's
context (less prominently than `systemMessage`). The plan's draft JSON shape —
nesting `additionalContext` inside `hookSpecificOutput` — does not match the
current contract; see HANDOFF-code-to-doctrine.md for the corrected shape used
here: `{"additionalContext": "STATIC PASS <file>" | "STATIC FAIL <file>: ..."}`
at the TOP level of the hook's stdout JSON.
"""
import json
import os
import re
import sys

# The engine lives beside this hook inside the plugin. CLAUDE_PLUGIN_ROOT is set by
# Claude Code for plugin hooks; the relative fallback keeps the hook working when it
# is run directly (tests, or a manual settings.json registration).
PLUGIN_ROOT = os.environ.get(
    "CLAUDE_PLUGIN_ROOT",
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)
SCRIPTS = os.path.join(PLUGIN_ROOT, "scripts")
sys.path.insert(0, SCRIPTS)


def emit(context):
    print(json.dumps({"additionalContext": context}))


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0

    file_path = payload.get("tool_input", {}).get("file_path", "") or ""
    name = os.path.basename(file_path)
    if not re.match(r"^\d{2}-.*\.html$", name):
        return 0
    if not os.path.isfile(file_path):
        return 0

    if not os.path.isdir(SCRIPTS):
        return 0  # engine not where we expect it — inform-only hook, stay silent

    try:
        import validate  # noqa: E402
        from ds_config import load  # noqa: E402
    except Exception as e:
        # Never let an engine import problem look like a slide defect.
        emit(f"STATIC SKIP {name}: validator unavailable ({e})")
        return 0

    try:
        ds = load()
        tokens, gradients = validate.canonical_tokens(ds)
        palette = validate.allowed_hexes(ds)
        import glob
        template_stems = {os.path.splitext(os.path.basename(p))[0]
                          for p in glob.glob(os.path.join(ds.templates_dir, "*.html"))}
        fails, warns = validate.check_file(file_path, ds, tokens, gradients, palette, template_stems)
    except SystemExit as e:
        emit(f"STATIC SKIP {name}: {e}")
        return 0
    except Exception as e:
        emit(f"STATIC SKIP {name}: validator error ({e})")
        return 0

    if fails:
        lines = "; ".join(fails)
        emit(f"STATIC FAIL {name}: {lines}")
    else:
        emit(f"STATIC PASS {name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
