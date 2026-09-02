#!/usr/bin/env python3
"""Smoke test for slide_write_check.py — run any time the hook changes.

WP1: the PostToolUse hook must emit a JSON `additionalContext` verdict the
model actually sees (STATIC PASS/FAIL), never plain stdout text, and it must
run ONLY the instant static check (validate.py) — no browser launch, no
fix_font_paths rescan.

Usage:  python3 hooks/test_slide_write_check.py
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN = os.path.dirname(HERE)
SCRIPTS = os.path.join(PLUGIN, "scripts")
HOOK = os.path.join(HERE, "slide_write_check.py")

sys.path.insert(0, SCRIPTS)
from ds_config import load  # noqa: E402


def run_hook(file_path):
    payload = {"tool_input": {"file_path": file_path}}
    env = dict(os.environ)
    env["CLAUDE_PLUGIN_ROOT"] = PLUGIN
    t0 = time.time()
    proc = subprocess.run([sys.executable, HOOK], input=json.dumps(payload),
                          capture_output=True, text=True, env=env, timeout=30)
    elapsed = time.time() - t0
    context = None
    if proc.stdout.strip():
        try:
            context = json.loads(proc.stdout).get("additionalContext")
        except Exception:
            context = f"<unparsable: {proc.stdout[:200]}>"
    return context, elapsed, proc.stderr


def main():
    results = []
    ds = load()
    with tempfile.TemporaryDirectory() as tmp:
        deck_dir = os.path.join(tmp, "deck")
        os.makedirs(deck_dir)
        if os.path.isdir(ds.fonts_dir):
            shutil.copytree(ds.fonts_dir, os.path.join(deck_dir, "fonts"))

        clean_path = os.path.join(ds.templates_dir, "01-cover.html")
        clean = open(clean_path, encoding="utf-8").read()

        # ── Case 1: clean slide -> STATIC PASS, fast (no browser) ──
        clean_slide = os.path.join(deck_dir, "01-cover.html")
        with open(clean_slide, "w", encoding="utf-8") as f:
            f.write(clean)
        context, elapsed, err = run_hook(clean_slide)
        ok = context == "STATIC PASS 01-cover.html" and elapsed < 5
        results.append(ok)
        print(f"{'PASS' if ok else 'FAIL'}  [clean slide -> STATIC PASS, <5s]  "
              f"context={context!r} elapsed={elapsed:.2f}s" + ("" if ok else f" stderr={err!r}"))

        # ── Case 2: off-brand class -> STATIC FAIL, names the violation ──
        bad_slide = os.path.join(deck_dir, "02-bad.html")
        bad = clean.replace("bg-epam-cover", "bg-blue-500", 1)
        with open(bad_slide, "w", encoding="utf-8") as f:
            f.write(bad)
        context, elapsed, err = run_hook(bad_slide)
        ok = bool(context) and context.startswith("STATIC FAIL 02-bad.html") and "bg-blue-500" in context
        results.append(ok)
        print(f"{'PASS' if ok else 'FAIL'}  [off-brand class -> STATIC FAIL names it]  "
              f"context={context!r}" + ("" if ok else f" stderr={err!r}"))

        # ── Case 3: non-slide file -> silent no-op ──
        other = os.path.join(deck_dir, "deck-state.json")
        with open(other, "w") as f:
            f.write("{}")
        context, elapsed, err = run_hook(other)
        ok = context is None
        results.append(ok)
        print(f"{'PASS' if ok else 'FAIL'}  [non-slide file -> no-op]  context={context!r}")

    failed = results.count(False)
    print(f"\n{results.count(True)}/{len(results)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
