#!/usr/bin/env python3
"""
SubagentStop hook (matcher: agent type `imprimatur:deck-designer`)  —  WP1.

When a deck-designer chunk agent tries to finish, this hook finds every slide
file it wrote or edited during this run (by scanning its OWN transcript for
Write/Edit tool calls on `NN-*.html`, plus `new_slide.py`/`log_slide.py`
Bash invocations) and runs the batch `qa.py --json` on exactly those files —
ONE Chromium launch for the whole chunk. If any file FAILs, the agent is
blocked from stopping until it fixes it: this is the same "cannot hand back
a chunk that hasn't passed" guarantee the old per-write hook was meant to
give, now enforced once at chunk-end instead of interrupting every write.

Why scan the transcript instead of trusting deck-state.json's `written` rows:
`written` may include slides from an EARLIER chunk agent that already passed
and moved to `revised`/`approved` by the time this agent stops — re-checking
those wastes a browser launch on files this agent never touched. The
transcript is the ground truth for "what did THIS run touch."

Verified against the current Claude Code hooks reference (2026-09): SubagentStop
CAN block (`hookSpecificOutput.permissionDecision: "deny"` +
`permissionDecisionReason: "<text>"`) — NOT `decision`/`reason` as an earlier
draft of the optimization plan assumed; see HANDOFF-code-to-doctrine.md.
SubagentStop's matcher DOES support targeting one agent type by name
(`^imprimatur:deck-designer$`, the plugin-scoped form), so the plan's stated
fallback ("gate on deck-state.json `written` rows if the matcher can't target
one agent") was not needed — but this hook still defensively no-ops if
`agent_type` doesn't look like deck-designer, in case it is ever registered
with a broader matcher.

Reads the hook payload as JSON on stdin: `transcript_path`, `agent_type`,
`cwd`. Exit 0 with no output (or `permissionDecision: allow`) lets the agent
stop; JSON with `permissionDecision: deny` blocks it and shows
`permissionDecisionReason` to the agent as the reason to keep working.
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
NEW_SLIDE_BASH_RE = re.compile(r"new_slide\.py\b.*?--deck-dir\s+(\S+).*?--n\s+(\d+).*?--slug\s+(\S+)")


def emit(decision, reason=None):
    out = {"hookSpecificOutput": {"hookEventName": "SubagentStop", "permissionDecision": decision}}
    if reason:
        out["hookSpecificOutput"]["permissionDecisionReason"] = reason
    print(json.dumps(out))


def touched_slides(transcript_path):
    """Scan a subagent transcript JSONL for Write/Edit calls on NN-*.html.

    Returns a set of absolute file paths. Best-effort: a transcript line that
    fails to parse is skipped rather than aborting the scan.
    """
    touched = set()
    if not transcript_path or not os.path.isfile(transcript_path):
        return touched
    try:
        with open(transcript_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                msg = rec.get("message") or {}
                content = msg.get("content")
                if not isinstance(content, list):
                    continue
                for block in content:
                    if not isinstance(block, dict) or block.get("type") != "tool_use":
                        continue
                    name = block.get("name")
                    inp = block.get("input") or {}
                    if name in ("Write", "Edit"):
                        fp = inp.get("file_path") or ""
                        if SLIDE_RE.match(os.path.basename(fp)) and os.path.isfile(fp):
                            touched.add(os.path.abspath(fp))
                    elif name == "Bash":
                        cmd = str(inp.get("command") or "")
                        if "new_slide.py" in cmd:
                            m = NEW_SLIDE_BASH_RE.search(cmd)
                            if m:
                                deck_dir, n, slug = m.groups()
                                cand = os.path.join(deck_dir, f"{n}-{slug}.html")
                                if os.path.isfile(cand):
                                    touched.add(os.path.abspath(cand))
    except Exception:
        pass
    return touched


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0

    agent_type = str(payload.get("agent_type") or "")
    # Defensive no-op if this hook is ever wired to a broader matcher than
    # `^imprimatur:deck-designer$` — the matcher should already restrict this,
    # but a hook that silently misfires on the wrong agent is worse than one
    # that does nothing.
    if "deck-designer" not in agent_type:
        return 0

    if not os.path.isdir(SCRIPTS):
        return 0  # engine not where expected — fail open, never block on our own bug

    transcript_path = payload.get("transcript_path")
    files = sorted(touched_slides(transcript_path))
    if not files:
        return 0  # nothing this agent wrote — nothing to gate

    deck_dirs = {os.path.dirname(f) for f in files}
    deck_dir = sorted(deck_dirs)[0] if len(deck_dirs) == 1 else None

    cmd = [sys.executable, os.path.join(SCRIPTS, "qa.py"), "--files", *files, "--json"]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    except Exception as e:
        # A gate that can't run must not silently pass — but it also must not
        # hard-block the pipeline on an infra problem it can't explain. Allow,
        # and say why in the transcript via stderr (informational only).
        print(f"designer_stop_gate: qa.py failed to run ({e}); allowing stop.", file=sys.stderr)
        return 0

    try:
        data = json.loads(result.stdout)
    except Exception:
        print("designer_stop_gate: qa.py --json produced unparsable output; allowing stop.",
              file=sys.stderr)
        return 0

    if data.get("pass"):
        emit("allow")
        return 0

    # Build a compact reason: filenames + counts, not the full verdict dump.
    lines = []
    for fname, v in data.get("validate", {}).items():
        if v.get("fails"):
            lines.append(f"{fname}: {len(v['fails'])} static FAIL(s) — {'; '.join(v['fails'][:3])}")
    for fname, v in data.get("render_checks", {}).items():
        # contrast_fails is deliberately excluded: qa.py --files (this chunk-level
        # call) does not count contrast toward pass/fail by default — it's brand-
        # audit's whole-deck judgment call — so a count that included it here
        # would not match data['total_failures'] and would misattribute why the
        # gate fired.
        n_render_fails = (len(v.get("overflow", [])) + len(v.get("collisions", []))
                          + len(v.get("paint", [])))
        if n_render_fails:
            lines.append(f"{fname}: {n_render_fails} render-check FAIL(s)")
    reason = (
        f"qa.py --json found {data.get('total_failures', '?')} failure(s) across "
        f"{len(files)} slide(s) this chunk wrote. Fix them, re-run "
        f"`qa.py --files {' '.join(os.path.basename(f) for f in files)}` on the touched "
        f"files only, then report back.\n" + "\n".join(lines[:10])
    )
    emit("deny", reason)
    return 0


if __name__ == "__main__":
    sys.exit(main())
