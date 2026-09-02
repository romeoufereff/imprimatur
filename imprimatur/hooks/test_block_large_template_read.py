#!/usr/bin/env python3
"""Smoke test for block_large_template_read.py — run any time the hook changes.

WP7: a whole-file Read of a pack template > 100 KB must be blocked with a
new_slide.py hint; a Read with offset/limit, a Read of a small template, and a
Read of anything outside templates/ must all be allowed through untouched.

Usage:  python3 hooks/test_block_large_template_read.py
"""
import glob
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN = os.path.dirname(HERE)
SCRIPTS = os.path.join(PLUGIN, "scripts")
HOOK = os.path.join(HERE, "block_large_template_read.py")

sys.path.insert(0, SCRIPTS)
from ds_config import load  # noqa: E402


def run_hook(file_path, offset=None, limit=None, tool_name="Read"):
    tool_input = {"file_path": file_path}
    if offset is not None:
        tool_input["offset"] = offset
    if limit is not None:
        tool_input["limit"] = limit
    payload = {"tool_name": tool_name, "tool_input": tool_input}
    env = dict(os.environ)
    env["CLAUDE_PLUGIN_ROOT"] = PLUGIN
    proc = subprocess.run([sys.executable, HOOK], input=json.dumps(payload),
                          capture_output=True, text=True, env=env, timeout=15)
    decision = None
    if proc.stdout.strip():
        try:
            decision = json.loads(proc.stdout)["hookSpecificOutput"]["permissionDecision"]
        except Exception:
            decision = f"<unparsable: {proc.stdout[:200]}>"
    return decision, proc.stdout


def main():
    ds = load()
    large = sorted(
        (p for p in glob.glob(os.path.join(ds.templates_dir, "*.html"))
         if os.path.getsize(p) > 100 * 1024),
        key=os.path.getsize, reverse=True,
    )
    small = sorted(
        (p for p in glob.glob(os.path.join(ds.templates_dir, "*.html"))
         if os.path.getsize(p) <= 100 * 1024),
        key=os.path.getsize,
    )
    if not large:
        print("SKIP  no template > 100KB found in the active pack — nothing to test against")
        return 0

    results = []

    decision, out = run_hook(large[0])
    ok = decision == "deny" and "new_slide.py" in out
    results.append(ok)
    print(f"{'PASS' if ok else 'FAIL'}  [whole-file Read of {os.path.basename(large[0])} -> deny, "
          f"names new_slide.py]  decision={decision!r}")

    decision, out = run_hook(large[0], offset=1, limit=50)
    ok = decision is None
    results.append(ok)
    print(f"{'PASS' if ok else 'FAIL'}  [Read with offset/limit -> allow]  decision={decision!r}")

    if small:
        decision, out = run_hook(small[0])
        ok = decision is None
        results.append(ok)
        print(f"{'PASS' if ok else 'FAIL'}  [Read of small template {os.path.basename(small[0])} -> allow]  "
              f"decision={decision!r}")

    ds_json = os.path.join(ds.root, "design-system.json")
    decision, out = run_hook(ds_json)
    ok = decision is None
    results.append(ok)
    print(f"{'PASS' if ok else 'FAIL'}  [Read outside templates/ -> allow]  decision={decision!r}")

    decision, out = run_hook(large[0], tool_name="Grep")
    ok = decision is None
    results.append(ok)
    print(f"{'PASS' if ok else 'FAIL'}  [non-Read tool -> no-op]  decision={decision!r}")

    failed = results.count(False)
    print(f"\n{results.count(True)}/{len(results)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
