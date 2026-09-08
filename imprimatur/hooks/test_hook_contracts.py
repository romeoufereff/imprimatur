#!/usr/bin/env python3
"""Contract tests: every hook's JSON output must use the shape Claude Code
actually reads for that event — taken from the hooks reference, NOT from the
hook. Written after the 2026-09-07 audit found two hooks that passed their own
behaviour tests for a week while the harness silently ignored their output.

Reference (code.claude.com/docs/en/hooks, "JSON output" table, 2026-09-07):

  event            decision channel                    context channel
  PreToolUse       hookSpecificOutput.permissionDecision (allow|deny|ask)
                   + permissionDecisionReason           hookSpecificOutput.additionalContext
  PostToolUse      top-level decision:"block" + reason   hookSpecificOutput.additionalContext
  Stop/SubagentStop top-level decision:"block" + reason  hookSpecificOutput.additionalContext
  SubagentStart    (none)                                hookSpecificOutput.additionalContext

Input fields: SubagentStop carries the subagent's transcript in
`agent_transcript_path`; `transcript_path` is the MAIN session's.

These tests feed each hook a payload that must produce output and assert the
nesting, without needing a browser (the stop gate is exercised with a
transcript naming a file that fails the instant static check, so qa.py fails
on validate alone; Playwright still launches — this is a real run).

Usage:  python3 hooks/test_hook_contracts.py
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(PLUGIN, "scripts"))
from ds_config import load  # noqa: E402


def run(hook, payload):
    env = dict(os.environ)
    env["CLAUDE_PLUGIN_ROOT"] = PLUGIN
    proc = subprocess.run([sys.executable, os.path.join(HERE, hook)], input=json.dumps(payload),
                          capture_output=True, text=True, env=env, timeout=180)
    out = json.loads(proc.stdout) if proc.stdout.strip() else None
    return out, proc


def main():
    results = []

    def check(name, ok, detail=""):
        results.append(ok)
        print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  {detail}" if detail and not ok else ""))

    ds = load()
    with tempfile.TemporaryDirectory() as tmp:
        deck = os.path.join(tmp, "deck")
        os.makedirs(deck)
        if os.path.isdir(ds.fonts_dir):
            shutil.copytree(ds.fonts_dir, os.path.join(deck, "fonts"))
        template = open(os.path.join(ds.templates_dir, "01-cover.html"), encoding="utf-8").read()
        slide = os.path.join(deck, "01-cover.html")
        open(slide, "w", encoding="utf-8").write(template)

        # ── PostToolUse: slide_write_check ──
        out, proc = run("slide_write_check.py", {"hook_event_name": "PostToolUse", "tool_name": "Edit",
                                                 "tool_input": {"file_path": slide}})
        hso = (out or {}).get("hookSpecificOutput") or {}
        check("PostToolUse verdict is hookSpecificOutput.additionalContext",
              hso.get("hookEventName") == "PostToolUse" and str(hso.get("additionalContext", "")).startswith("STATIC "),
              f"stdout={proc.stdout!r}")
        check("PostToolUse output has no top-level additionalContext (the dropped shape)",
              out is not None and "additionalContext" not in out)

        # ── SubagentStop: designer_stop_gate on a slide with a seeded static FAIL ──
        bad = os.path.join(deck, "02-bad.html")
        open(bad, "w", encoding="utf-8").write(template.replace("<body", "<body class=\"bg-blue-500\"", 1))
        transcript = os.path.join(tmp, "subagents", "agent-x.jsonl")
        os.makedirs(os.path.dirname(transcript))
        with open(transcript, "w") as f:
            f.write(json.dumps({"type": "assistant", "message": {"content": [
                {"type": "tool_use", "name": "Write", "input": {"file_path": bad, "content": "x"}}]}}) + "\n")
        payload = {"hook_event_name": "SubagentStop", "agent_type": "imprimatur:deck-designer",
                   "transcript_path": os.path.join(tmp, "main.jsonl"),  # must NOT be scanned
                   "agent_transcript_path": transcript, "cwd": tmp}
        out, proc = run("designer_stop_gate.py", payload)
        check("SubagentStop blocks with top-level decision:'block'",
              out is not None and out.get("decision") == "block", f"stdout={proc.stdout!r} stderr={proc.stderr[-300:]!r}")
        check("SubagentStop block carries a top-level reason", bool((out or {}).get("reason")))
        check("SubagentStop output has no hookSpecificOutput.permissionDecision (PreToolUse vocabulary)",
              "permissionDecision" not in json.dumps(out or {}))

        # the same payload with ONLY transcript_path (main session) must not gate anything
        payload2 = dict(payload)
        del payload2["agent_transcript_path"]
        out, proc = run("designer_stop_gate.py", payload2)
        check("SubagentStop never scans the main transcript_path", out is None and not proc.stdout.strip())

        # ── PreToolUse: block_large_template_read uses permissionDecision ──
        big = os.path.join(ds.templates_dir, "10-split-metrics.html")
        if os.path.isfile(big) and os.path.getsize(big) > 100 * 1024:
            out, proc = run("block_large_template_read.py", {"hook_event_name": "PreToolUse", "tool_name": "Read",
                                                             "tool_input": {"file_path": big}})
            hso = (out or {}).get("hookSpecificOutput") or {}
            check("PreToolUse deny is hookSpecificOutput.permissionDecision",
                  hso.get("hookEventName") == "PreToolUse" and hso.get("permissionDecision") == "deny"
                  and bool(hso.get("permissionDecisionReason")))

    failed = results.count(False)
    print(f"\n{results.count(True)}/{len(results)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
