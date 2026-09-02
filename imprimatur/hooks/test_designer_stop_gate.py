#!/usr/bin/env python3
"""Smoke test for designer_stop_gate.py — run any time the hook or qa.py changes.

Builds a fake subagent transcript (JSONL) with Write tool_use entries pointing at
real slide files in a scratch deck dir, then invokes the hook exactly as Claude
Code would (JSON payload on stdin) and checks the permissionDecision it emits.

WP1 acceptance: a chunk with one seeded failure must be blocked; a clean chunk
must pass. Requires the active design-system pack (DECK_DESIGN_SYSTEM env, or
the default sibling pack) and Playwright/Chromium (qa.py's render checks run
for real — this is a smoke test, not a mock).

Usage:  python3 hooks/test_designer_stop_gate.py
"""
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN = os.path.dirname(HERE)
SCRIPTS = os.path.join(PLUGIN, "scripts")
HOOK = os.path.join(HERE, "designer_stop_gate.py")

sys.path.insert(0, SCRIPTS)
from ds_config import load  # noqa: E402


def clean_and_overflow_slides():
    """A genuinely pack-valid slide (a real template file, which already passes
    validate.py + every render check) as the clean case, and the same content
    with one element pushed 400px past the right edge as the seeded-failure
    case. Using a real template — rather than a hand-rolled stub — means the
    'clean' case is only clean because of the overflow check, not because it
    skips every other rule the pack declares (footer text, scaler, data-template,
    font marker, etc.), which a minimal stub would have to fake or dodge.
    """
    import re
    ds = load()
    template_path = os.path.join(ds.templates_dir, "01-cover.html")
    with open(template_path, encoding="utf-8") as f:
        clean = f.read()
    # Insert the overflowing element right after the OPENING #slide tag, so it is
    # a child of #slide (the overflow/collision checkers only walk #slide's own
    # subtree) — not merely appended near </body>, which would land outside it.
    injected = (
        '<div style="position:absolute;left:2200px;top:60px;width:600px;'
        'color:#1A1A1A;font-size:28px">Deliberately overflowing test element.</div>'
    )
    overflow, n = re.subn(r'(<div id="slide"[^>]*>)', r'\1' + injected, clean, count=1)
    assert n == 1, "could not locate the #slide opening tag in the template"
    return clean, overflow


def make_transcript(path, deck_dir, filenames):
    """One JSONL line per Write tool_use, matching Claude Code's transcript shape
    closely enough for touched_slides()'s parser (message.content[].tool_use)."""
    with open(path, "w", encoding="utf-8") as f:
        for fn in filenames:
            rec = {
                "type": "assistant",
                "message": {
                    "content": [
                        {"type": "tool_use", "name": "Write",
                         "input": {"file_path": os.path.join(deck_dir, fn), "content": "..."}}
                    ]
                },
            }
            f.write(json.dumps(rec) + "\n")


def run_hook(transcript_path, agent_type="imprimatur:deck-designer"):
    payload = {"transcript_path": transcript_path, "agent_type": agent_type,
              "cwd": os.getcwd(), "session_id": "test", "hook_event_name": "SubagentStop"}
    env = dict(os.environ)
    env["CLAUDE_PLUGIN_ROOT"] = PLUGIN
    proc = subprocess.run([sys.executable, HOOK], input=json.dumps(payload),
                          capture_output=True, text=True, env=env, timeout=60)
    decision = None
    if proc.stdout.strip():
        try:
            decision = json.loads(proc.stdout)["hookSpecificOutput"]["permissionDecision"]
        except Exception:
            decision = f"<unparsable: {proc.stdout[:200]}>"
    return decision, proc.stdout, proc.stderr


def main():
    import shutil
    results = []
    ds = load()
    with tempfile.TemporaryDirectory() as tmp:
        deck_dir = os.path.join(tmp, "deck")
        os.makedirs(deck_dir)
        # Fonts must resolve locally (checkFontUrlsResolve) or validate.py FAILs
        # every case on an unrelated rule — copy them in, same as new_slide.py does.
        if os.path.isdir(ds.fonts_dir):
            shutil.copytree(ds.fonts_dir, os.path.join(deck_dir, "fonts"))

        clean_html, overflow_html = clean_and_overflow_slides()

        # ── Case 1: clean chunk -> allow (or no decision at all, both fine) ──
        with open(os.path.join(deck_dir, "01-clean.html"), "w", encoding="utf-8") as f:
            f.write(clean_html)
        transcript = os.path.join(tmp, "clean.jsonl")
        make_transcript(transcript, deck_dir, ["01-clean.html"])
        decision, out, err = run_hook(transcript)
        ok = decision in (None, "allow")
        results.append(ok)
        print(f"{'PASS' if ok else 'FAIL'}  [clean chunk -> allow]  decision={decision!r}"
              + ("" if ok else f"  stdout={out!r} stderr={err!r}"))

        # ── Case 2: chunk with a seeded overflow -> deny ──
        with open(os.path.join(deck_dir, "02-overflow.html"), "w", encoding="utf-8") as f:
            f.write(overflow_html)
        transcript2 = os.path.join(tmp, "overflow.jsonl")
        make_transcript(transcript2, deck_dir, ["02-overflow.html"])
        decision, out, err = run_hook(transcript2)
        ok = decision == "deny"
        results.append(ok)
        print(f"{'PASS' if ok else 'FAIL'}  [chunk with seeded overflow -> deny]  decision={decision!r}"
              + ("" if ok else f"  stdout={out!r} stderr={err!r}"))

        # ── Case 3: wrong agent_type -> no-op (never even runs qa.py) ──
        decision, out, err = run_hook(transcript2, agent_type="imprimatur:brand-audit")
        ok = decision is None and not out.strip()
        results.append(ok)
        print(f"{'PASS' if ok else 'FAIL'}  [non-designer agent_type -> no-op]  decision={decision!r}")

        # ── Case 4: no transcript / nothing touched -> no-op ──
        empty_transcript = os.path.join(tmp, "empty.jsonl")
        open(empty_transcript, "w").close()
        decision, out, err = run_hook(empty_transcript)
        ok = decision is None
        results.append(ok)
        print(f"{'PASS' if ok else 'FAIL'}  [empty transcript -> no-op]  decision={decision!r}")

    failed = results.count(False)
    print(f"\n{results.count(True)}/{len(results)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
