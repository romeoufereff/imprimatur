#!/usr/bin/env python3
"""Tests for agent_header.py (SubagentStart) — the injected boot header.

Cases: an imprimatur agent gets `hookSpecificOutput.additionalContext` starting
with the PLUGIN=… header; DECK resolves from $DECK, else from a deck-shaped cwd,
else prints <unset>; a non-imprimatur agent gets nothing.

Usage:  python3 hooks/test_agent_header.py
"""
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN = os.path.dirname(HERE)
HOOK = os.path.join(HERE, "agent_header.py")


def run(agent_type, cwd, deck_env=None):
    env = dict(os.environ)
    env["CLAUDE_PLUGIN_ROOT"] = PLUGIN
    env.pop("DECK", None)
    if deck_env:
        env["DECK"] = deck_env
    payload = {"hook_event_name": "SubagentStart", "agent_type": agent_type, "agent_id": "a1", "cwd": cwd}
    proc = subprocess.run([sys.executable, HOOK], input=json.dumps(payload), capture_output=True, text=True,
                          env=env, timeout=60)
    if not proc.stdout.strip():
        return None
    out = json.loads(proc.stdout)
    hso = out["hookSpecificOutput"]
    assert hso["hookEventName"] == "SubagentStart"
    return hso["additionalContext"]


def main():
    results = []

    def check(name, ok):
        results.append(ok)
        print(f"{'PASS' if ok else 'FAIL'}  {name}")

    with tempfile.TemporaryDirectory() as tmp:
        deck = os.path.join(tmp, "deck")
        os.makedirs(deck)
        open(os.path.join(deck, "deck-state.json"), "w").write("{}")

        ctx = run("imprimatur:deck-designer", cwd=tmp, deck_env=deck)
        check("imprimatur agent gets a PLUGIN=… header", bool(ctx) and ctx.startswith("PLUGIN="))
        check("DECK from $DECK", bool(ctx) and f"DECK={deck}" in ctx)
        check("header names PACK and DS_NAME", bool(ctx) and "PACK=" in ctx and "DS_NAME=" in ctx)

        ctx = run("imprimatur:brand-audit", cwd=deck)
        check("DECK from a deck-shaped cwd when $DECK is unset", bool(ctx) and f"DECK={deck}" in ctx)

        ctx = run("imprimatur:deck-narrative", cwd=tmp)
        check("DECK=<unset> when nothing identifies the deck", bool(ctx) and "DECK=<unset>" in ctx)

        check("non-imprimatur agent gets nothing", run("Explore", cwd=deck) is None)

    failed = results.count(False)
    print(f"\n{results.count(True)}/{len(results)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
