#!/usr/bin/env python3
"""Tests for orchestrator_guard.py — the orchestrator's lane, mechanically.

Cases: main session (no agent_type) is denied a slide Write, an outline Write in
a deck folder, and an image Read in a deck folder; Edit is never touched; the
same calls inside a subagent (agent_type present) pass; anything outside a deck
folder passes; the deny shape is the PreToolUse contract.

Usage:  python3 hooks/test_orchestrator_guard.py
"""
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
HOOK = os.path.join(HERE, "orchestrator_guard.py")


def run(tool, file_path, agent_type=None):
    payload = {"hook_event_name": "PreToolUse", "tool_name": tool, "tool_input": {"file_path": file_path}}
    if agent_type:
        payload["agent_type"] = agent_type
    proc = subprocess.run([sys.executable, HOOK], input=json.dumps(payload), capture_output=True, text=True)
    if not proc.stdout.strip():
        return None
    out = json.loads(proc.stdout)
    hso = out["hookSpecificOutput"]
    assert hso["hookEventName"] == "PreToolUse" and hso["permissionDecision"] == "deny" and hso["permissionDecisionReason"]
    return "deny"


def main():
    results = []

    def check(name, ok):
        results.append(ok)
        print(f"{'PASS' if ok else 'FAIL'}  {name}")

    with tempfile.TemporaryDirectory() as tmp:
        deck = os.path.join(tmp, "deck")
        os.makedirs(deck)
        open(os.path.join(deck, "deck-state.json"), "w").write("{}")
        open(os.path.join(deck, "01-cover.html"), "w").write("<html></html>")
        open(os.path.join(deck, "01-cover.png"), "wb").write(b"\x89PNG")
        other = os.path.join(tmp, "elsewhere")
        os.makedirs(other)
        open(os.path.join(other, "shot.png"), "wb").write(b"\x89PNG")

        check("main: Write slide file -> deny", run("Write", os.path.join(deck, "02-new.html")) == "deny")
        check("main: Write narrative-outline.md in deck -> deny",
              run("Write", os.path.join(deck, "narrative-outline.md")) == "deny")
        check("main: Read slide render in deck -> deny", run("Read", os.path.join(deck, "01-cover.png")) == "deny")
        check("main: Edit slide file -> allowed (text-only fixes)", run("Edit", os.path.join(deck, "01-cover.html")) is None)
        check("main: Write deck-brief.md -> allowed", run("Write", os.path.join(deck, "deck-brief.md")) is None)
        check("main: Read image outside a deck -> allowed", run("Read", os.path.join(other, "shot.png")) is None)
        check("main: Write narrative-outline.md outside a deck -> allowed",
              run("Write", os.path.join(other, "narrative-outline.md")) is None)
        check("designer subagent: Write slide file -> allowed",
              run("Write", os.path.join(deck, "02-new.html"), agent_type="imprimatur:deck-designer") is None)
        check("narrative subagent: Write outline -> allowed",
              run("Write", os.path.join(deck, "narrative-outline.md"), agent_type="imprimatur:deck-narrative") is None)
        check("brand-audit subagent: Read render -> allowed (capped by doctrine, not here)",
              run("Read", os.path.join(deck, "01-cover.png"), agent_type="imprimatur:brand-audit") is None)
        # a Read of a render one level below the deck (scratch renders in deck/_renders/)
        sub = os.path.join(deck, "_renders")
        os.makedirs(sub)
        open(os.path.join(sub, "03.png"), "wb").write(b"\x89PNG")
        check("main: Read render in a deck subfolder -> deny", run("Read", os.path.join(sub, "03.png")) == "deny")

    failed = results.count(False)
    print(f"\n{results.count(True)}/{len(results)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
