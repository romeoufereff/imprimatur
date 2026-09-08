#!/usr/bin/env python3
"""
Hook probe — did the plugin's hooks actually reach Claude?

Claude Code records every hook run in the MAIN session transcript as an
`attachment` record. Two attachment types matter, and they are not the same:

  hook_success            the hook ran; its stdout/stderr/exitCode are recorded.
                          This alone proves NOTHING about what the model saw —
                          a hook that prints the right words in the wrong JSON
                          shape shows up here looking healthy.
  hook_additional_context the harness accepted an `additionalContext` value and
                          injected it into the model's context. This is the only
                          record that means "Claude read it".

The 2026-09-07 audit found the plugin's static verdict in hundreds of
hook_success records and in zero hook_additional_context records: the JSON was
nested at the wrong level and silently dropped for a week. This script exists
so that check takes one command instead of a transcript forensics session.

For each hook command seen in a session it reports: fires, how many produced
additional context, how many errored (non-empty stderr or non-zero exit), the
median duration, and whether the command points at a legacy location outside
the plugin (`~/.claude/hooks/…`) — the double-registration the audit found.
SubagentStop events are listed separately with their decision, because a
stop gate that never appears here never blocked anything.

Usage:
    hook_probe.py <session-id-or-jsonl-path> [--json]
    hook_probe.py --latest            # most recently modified session under ~/.claude/projects

Exit 0 always — this is a report, not a gate. Read the last block: it names the
plugin hooks that fired but never produced context, which is the WP1 failure
signature.
"""
import argparse
import glob
import json
import os
import statistics
import sys
from collections import defaultdict

PLUGIN_HOOKS = (
    "slide_write_check.py", "designer_stop_gate.py", "block_large_template_read.py",
    "block_batch_slide_write.py", "deck_consistency.py", "export_gate.py",
    "export_notify.py", "orchestrator_guard.py", "agent_header.py",
)
CONTEXT_HOOKS = ("slide_write_check.py", "agent_header.py")  # must produce additionalContext


def resolve_main_path(arg):
    if arg == "--latest" or arg is None:
        cands = glob.glob(os.path.expanduser("~/.claude/projects/*/*.jsonl"))
        if not cands:
            sys.exit("error: no session transcripts under ~/.claude/projects")
        return max(cands, key=os.path.getmtime)
    if os.path.isfile(arg):
        return os.path.abspath(arg)
    home = os.path.expanduser("~/.claude/projects")
    matches = glob.glob(os.path.join(home, "*", arg + ".jsonl"))
    if not matches:
        sys.exit(f"error: no session transcript found for {arg!r} under {home}")
    return matches[0]


def short_cmd(cmd):
    """Key a hook by script name, with a [legacy] suffix when it runs from outside the
    plugin — the plugin copy and a leftover ~/.claude/hooks copy of the same script must
    never be merged into one row, or the legacy one's errors get pinned on the plugin."""
    cmd = (cmd or "").strip()
    legacy = "/.claude/hooks/" in cmd or cmd.startswith("python3 ~/.claude/hooks")
    for name in PLUGIN_HOOKS:
        if name in cmd:
            return name + (" [legacy]" if legacy else "")
    return cmd[:60]


DENIAL_PREFIXES = {
    "BLOCKED (orchestrator lane)": "orchestrator_guard.py",
    "BLOCKED by the one-slide-per-turn rule": "block_batch_slide_write.py",
    "BLOCKED by deck-review gate": "export_gate.py",
    "BLOCKED: ": "block_large_template_read.py",
}


def probe(path):
    hooks = defaultdict(lambda: {"fires": 0, "context": 0, "errors": 0, "durations": [],
                                 "legacy": False, "command": None, "events": set()})
    stops = []
    denials = defaultdict(int)
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except Exception:
            continue
        if rec.get("type") == "user":
            # A PreToolUse deny leaves no hook attachment — the reason comes back to the
            # model as the tool_result itself. Count those by their reason prefix.
            content = (rec.get("message") or {}).get("content")
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "tool_result":
                        text = block.get("content")
                        text = text if isinstance(text, str) else (
                            " ".join(c.get("text", "") for c in text if isinstance(c, dict)) if isinstance(text, list) else "")
                        for prefix, hook in DENIAL_PREFIXES.items():
                            if text.startswith(prefix):
                                denials[hook] += 1
                                break
            continue
        if rec.get("type") != "attachment":
            continue
        att = rec.get("attachment") or {}
        kind = att.get("type")
        hook_name = att.get("hookName", "")
        event = att.get("hookEvent") or hook_name.split(":")[0]
        if kind == "hook_success":
            key = short_cmd(att.get("command"))
            h = hooks[key]
            h["fires"] += 1
            h["command"] = att.get("command")
            h["events"].add(event)
            if key.endswith("[legacy]"):
                h["legacy"] = True
            if (att.get("stderr") or "").strip() or (att.get("exitCode") not in (0, None)):
                h["errors"] += 1
            if att.get("durationMs") is not None:
                h["durations"].append(att["durationMs"])
            if event == "SubagentStop":
                try:
                    out = json.loads(att.get("stdout") or "{}")
                except Exception:
                    out = {"_raw": (att.get("stdout") or "")[:120]}
                stops.append({"hook": key, "decision": out.get("decision"),
                              "raw": out if "_raw" in out else None})
        elif kind == "hook_additional_context":
            # Attributed by hookName only — the harness does not echo the command here.
            # Match it to the plugin hook that runs on that event and produces context.
            content = " ".join(att.get("content") or []) if isinstance(att.get("content"), list) \
                else str(att.get("content") or "")
            matched = None
            for name in CONTEXT_HOOKS:
                if name == "slide_write_check.py" and "STATIC " in content:
                    matched = name
                elif name == "agent_header.py" and "PLUGIN=" in content:
                    matched = name
            hooks[matched or f"(other) {hook_name}"]["context"] += 1
    return hooks, stops, denials


def main():
    ap = argparse.ArgumentParser(description=__doc__.strip().split("\n")[0])
    ap.add_argument("session", nargs="?", help="Session id, path, or --latest")
    ap.add_argument("--latest", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    path = resolve_main_path("--latest" if args.latest else args.session)
    hooks, stops, denials = probe(path)

    if args.json:
        out = {k: {**v, "durations": None, "median_ms": statistics.median(v["durations"]) if v["durations"] else None,
                   "events": sorted(v["events"])} for k, v in hooks.items()}
        print(json.dumps({"session": path, "hooks": out, "subagent_stops": stops,
                          "pretooluse_denials": dict(denials)}, indent=2))
        return 0

    print(f"session: {path}\n")
    print(f"{'hook':34s} {'fires':>5s} {'ctx':>5s} {'err':>4s} {'med_ms':>7s}  events / notes")
    for name, h in sorted(hooks.items(), key=lambda kv: -kv[1]["fires"]):
        med = f"{statistics.median(h['durations']):.0f}" if h["durations"] else "-"
        notes = ", ".join(sorted(h["events"]))
        if h["legacy"]:
            notes += "  ← LEGACY path outside the plugin (remove from ~/.claude/settings.json)"
        print(f"{name:34.34s} {h['fires']:5d} {h['context']:5d} {h['errors']:4d} {med:>7s}  {notes}")

    print()
    if denials:
        print("PreToolUse denials (returned to the model as the tool result):")
        for hook, n in sorted(denials.items()):
            print(f"  {hook}: {n}")
    else:
        print("PreToolUse denials: none")
    if stops:
        print("SubagentStop events:")
        for s in stops:
            print(f"  {s['hook']}: decision={s['decision']!r}" + (f" raw={s['raw']}" if s["raw"] else ""))
    else:
        print("SubagentStop events: none (no designer chunk was stop-gated in this session)")

    print()
    problems = []
    for name in CONTEXT_HOOKS:
        h = hooks.get(name)
        if h and h["fires"] and not h["context"]:
            problems.append(f"{name} fired {h['fires']}× and produced additionalContext 0× — "
                            f"its JSON is not in the shape the harness accepts "
                            f"(hookSpecificOutput.additionalContext).")
    for name, h in hooks.items():
        if h["legacy"]:
            problems.append(f"{name} is running from a legacy path: {h['command']}")
        if h["errors"] and name in PLUGIN_HOOKS and not h["legacy"]:
            problems.append(f"{name} errored {h['errors']}/{h['fires']} times (stderr or non-zero exit).")
    if problems:
        print("PROBLEMS")
        for p in problems:
            print(f"  ✗ {p}")
    else:
        print("no problems detected")
    return 0


if __name__ == "__main__":
    sys.exit(main())
