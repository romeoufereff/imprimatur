#!/usr/bin/env python3
"""
SubagentStart hook (matcher: ^imprimatur:) — inject the boot header.

Every imprimatur agent definition opens with "your spawn prompt begins with
PLUGIN=… · PACK=… · DECK=… · DS_NAME=…; if it is missing, ask the
orchestrator". That put a hard dependency on the orchestrator remembering to
paste one line, and on the audit's transcripts it cost 5–8 Bash calls per
agent whenever it forgot. SubagentStart supports `additionalContext`, so the
harness can hand the header to every plugin agent itself — the orchestrator's
prompt no longer needs to carry it, and an agent can never start without it.

DECK resolution, in order: `$DECK` in the environment; the hook's `cwd` if it
looks like a deck folder (deck-state.json or NN-*.html present); else
"<unset>" — the agent then reads DECK from its prompt as before, so this
degrades to the old behaviour rather than inventing a path.

Output: `hookSpecificOutput.additionalContext` (hooks reference, SubagentStart —
context only, no decision control). Exit 0 always; never blocks a spawn.
"""
import json
import os
import re
import subprocess
import sys

PLUGIN_ROOT = os.environ.get(
    "CLAUDE_PLUGIN_ROOT",
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)
SCRIPTS = os.path.join(PLUGIN_ROOT, "scripts")
SLIDE_RE = re.compile(r"^\d{2}-[\w.-]*\.html$")


def looks_like_deck(path):
    try:
        entries = os.listdir(path)
    except OSError:
        return False
    return "deck-state.json" in entries or any(SLIDE_RE.match(e) for e in entries)


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0
    if not str(payload.get("agent_type") or "").startswith("imprimatur:"):
        return 0
    if not os.path.isfile(os.path.join(SCRIPTS, "ds_config.py")):
        return 0

    deck = os.environ.get("DECK")
    cwd = payload.get("cwd") or ""
    if not deck and cwd and looks_like_deck(cwd):
        deck = cwd

    cmd = [sys.executable, os.path.join(SCRIPTS, "ds_config.py"), "--header"]
    if deck:
        cmd += ["--deck-dir", deck]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
        header = out.stdout.strip()
    except Exception:
        return 0
    if not header.startswith("PLUGIN="):
        return 0

    context = (
        f"{header}\n"
        f"Boot header injected by the plugin (SubagentStart). Use these absolute paths for "
        f"every script and file; do not search the filesystem for the plugin or the pack. "
        f"If DECK reads <unset>, take the deck folder from your prompt."
    )
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "SubagentStart",
                                             "additionalContext": context}}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
