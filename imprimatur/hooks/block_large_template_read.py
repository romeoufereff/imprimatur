#!/usr/bin/env python3
"""
PreToolUse hook (matcher: Read)  —  WP7.

Blocks a whole-file `Read` of any pack template larger than 100 KB (e.g. the
827 KB world-map templates `10-split-metrics.html` / `-compact`) and tells the
model to use `new_slide.py` instead. A `Read` that already passes `offset`/
`limit` (a deliberate body-region peek) is allowed through — the rule is
"never load the whole 827 KB file," not "never look at it."

Why this exists: those two templates stay exactly as they are (Roman's
decision, 2026-09-02 — the map's quality matters more than the file size), so
the fix has to be on the engine side. `new_slide.py` (WP2) already copies a
template byte-for-byte without a `Read`, but nothing stopped an agent from
`Read`-ing the template directly out of habit or curiosity first — one Nordex
designer transcript did this 12 times, ~2M tokens. This hook makes the byte-
for-byte copy path the only path.

Reads the tool call as JSON on stdin. Exit 0 with no output = allow. JSON with
`hookSpecificOutput.permissionDecision: "deny"` blocks the Read and shows
`permissionDecisionReason` to the model as the reason (verified against the
current Claude Code hooks reference, 2026-09: PreToolUse's decision field is
`permissionDecision`, not the plan's earlier "decision"/"block" wording).
"""
import json
import os
import sys

PLUGIN_ROOT = os.environ.get(
    "CLAUDE_PLUGIN_ROOT",
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)
SCRIPTS = os.path.join(PLUGIN_ROOT, "scripts")
sys.path.insert(0, SCRIPTS)

SIZE_LIMIT = 100 * 1024  # 100 KB, matches check_engine_clean.py's WARN threshold


def deny(reason):
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }))


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0

    if payload.get("tool_name") != "Read":
        return 0

    tool_input = payload.get("tool_input", {}) or {}
    file_path = tool_input.get("file_path") or ""
    if not file_path or not os.path.isfile(file_path):
        return 0

    # offset/limit means a deliberate partial read — allowed. The rule blocks
    # loading the WHOLE file, not looking at any of it.
    if tool_input.get("offset") is not None or tool_input.get("limit") is not None:
        return 0

    try:
        size = os.path.getsize(file_path)
    except OSError:
        return 0
    if size <= SIZE_LIMIT:
        return 0

    try:
        import ds_config
        pack_root = ds_config.find_root()
    except Exception:
        pack_root = None
    if not pack_root:
        return 0  # can't identify the active pack — fail open

    templates_dir = os.path.join(pack_root, "templates")
    try:
        under_templates = os.path.commonpath(
            [os.path.abspath(file_path), os.path.abspath(templates_dir)]
        ) == os.path.abspath(templates_dir)
    except ValueError:
        under_templates = False
    if not under_templates:
        return 0

    stem = os.path.splitext(os.path.basename(file_path))[0]
    kb = size // 1024
    deny(
        f"BLOCKED: {os.path.basename(file_path)} is {kb} KB — larger than the "
        f"{SIZE_LIMIT // 1024} KB threshold for a whole-file Read of a pack template.\n\n"
        f"This template is intentionally large (a high-quality asset, not a defect) and "
        f"must never enter a model's context whole. Use the copy-then-edit path instead:\n\n"
        f"  python3 {os.path.join(SCRIPTS, 'new_slide.py')} --deck-dir <DECK> "
        f"--template {stem} --n <NN> --slug <slug>\n\n"
        f"That copies the template byte-for-byte and prints only the <body> region with "
        f"line numbers — no Read of the source file needed. If you genuinely need to peek "
        f"at a specific region of THIS file, pass `offset`/`limit` to Read instead of a "
        f"whole-file read."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
