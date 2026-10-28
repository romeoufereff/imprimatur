#!/usr/bin/env python3
"""Tests for agent_header.py (SubagentStart) — the injected boot header.

Cases: an imprimatur agent gets `hookSpecificOutput.additionalContext` starting
with the PLUGIN=… header; DECK resolves from the spawn prompt's DECK= line
(payload `prompt`, the subagent transcript, or the parent transcript's Agent
call), else $DECK, else a deck-shaped cwd, else prints <unset>; PACK follows the
resolved deck's deck-state.json, or the prompt's PACK= when no deck resolves;
a non-imprimatur agent gets nothing.

Regression (2026-10-23, a client demo deck): the deck folder sat outside
the session cwd, the hook printed DECK=<unset> and the default EPAM pack while
the orchestrator's prompt named the client deck and pack.

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


def run(agent_type, cwd, deck_env=None, **extra):
    env = dict(os.environ)
    env["CLAUDE_PLUGIN_ROOT"] = PLUGIN
    env.pop("DECK", None)
    env.pop("DECK_DESIGN_SYSTEM", None)
    if deck_env:
        env["DECK"] = deck_env
    payload = {"hook_event_name": "SubagentStart", "agent_type": agent_type, "agent_id": "a1", "cwd": cwd}
    payload.update(extra)
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

        # ── deck outside the cwd, declaring its own pack ─────────────────
        default_pack = json.load(open(os.path.join(os.path.dirname(PLUGIN), "imprimatur-design-system",
                                                   "design-system.json")))
        pack = os.path.join(tmp, "packs", "client pack")      # spaces, like the vault paths
        os.makedirs(pack)
        json.dump(dict(default_pack, name="Regression Client Pack"),
                  open(os.path.join(pack, "design-system.json"), "w"))
        cdeck = os.path.join(tmp, "Work", "Client", "Slides", "Demo Deck")
        os.makedirs(cdeck)
        json.dump({"design_system": pack}, open(os.path.join(cdeck, "deck-state.json"), "w"))
        cwd = os.path.join(tmp, "session-cwd")
        os.makedirs(cwd)
        prompt = (f"PLUGIN={PLUGIN} · PACK={pack} · DECK={cdeck} · DS_NAME=Regression Client Pack\n\n"
                  f"Design slides 1-3 per {{DECK}}/design-decisions.md.")

        def is_client(ctx):
            return (bool(ctx) and f"DECK={cdeck} ·" in ctx and f"PACK={pack} ·" in ctx
                    and "DS_NAME=Regression Client Pack" in ctx)

        check("DECK + deck's PACK from payload prompt",
              is_client(run("imprimatur:deck-designer", cwd=cwd, prompt=prompt)))

        session = os.path.join(tmp, "proj", "s1.jsonl")
        sub = os.path.join(tmp, "proj", "s1", "subagents")
        os.makedirs(sub)
        with open(os.path.join(sub, "agent-a1.jsonl"), "w") as f:
            f.write(json.dumps({"type": "user", "isSidechain": True,
                                "message": {"role": "user", "content": prompt}}) + "\n")
        open(session, "w").write("")
        check("DECK + deck's PACK from the subagent transcript",
              is_client(run("imprimatur:design-crit", cwd=cwd, transcript_path=session)))

        call = {"type": "assistant", "message": {"role": "assistant", "content": [
            {"type": "text", "text": "Spawning the designer."},
            {"type": "tool_use", "id": "t1", "name": "Agent",
             "input": {"subagent_type": "imprimatur:brand-audit", "prompt": prompt}}]}}
        other = {"type": "assistant", "message": {"role": "assistant", "content": [
            {"type": "tool_use", "id": "t0", "name": "Agent",
             "input": {"subagent_type": "imprimatur:deck-narrative", "prompt": "DECK=/nowhere"}}]}}
        with open(session, "w") as f:
            f.write(json.dumps(call) + "\n" + json.dumps(other) + "\n")
        check("DECK + deck's PACK from the parent transcript's Agent call",
              is_client(run("imprimatur:brand-audit", cwd=cwd, transcript_path=session, agent_id="zz")))

        check("prompt DECK beats a stale $DECK",
              is_client(run("imprimatur:deck-designer", cwd=cwd, deck_env=deck, prompt=prompt)))

        bare = f"PLUGIN={PLUGIN} · PACK={pack} · DECK=<unset> · DS_NAME=x\n\nbuild the pack demo"
        ctx = run("imprimatur:deck-designer", cwd=cwd, prompt=bare)
        check("prompt PACK used when no deck resolves",
              bool(ctx) and f"PACK={pack} ·" in ctx and "DECK=<unset>" in ctx)

        ctx = run("imprimatur:deck-designer", cwd=cwd, prompt="no header here")
        check("no header in the prompt degrades to <unset>", bool(ctx) and "DECK=<unset>" in ctx)

    failed = results.count(False)
    print(f"\n{results.count(True)}/{len(results)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
