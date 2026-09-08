#!/usr/bin/env python3
"""
PreToolUse hook (matcher: Write|Read) — the orchestrator's lane, mechanically.

Every invariant that protects the designer is a hook; every rule that protects
the ORCHESTRATOR was prose — and the 2026-09-07 audit found the prose lost
whenever a review loop got messy: one session's main agent wrote five slide
files and the narrative outline itself, another read 32 slide renders
(94 % of everything that entered its context), and the main sessions ended
at 3–20× the cost of all their subagents combined. This hook turns three of
those rules into denials:

  1. Write of a slide file (NN-slug.html) from the main session
     → slides come into being only inside a deck-designer spawn (new_slide.py
       + Edit). Edit is deliberately NOT blocked: the doctrine allows the
       orchestrator text-only Edits on ≤ 3 slides in a review round.
  2. Write of narrative-outline.md from the main session
     → the deck-narrative agent writes it; a gap goes back to that agent.
  3. Read of an image file that sits in a deck folder, from the main session
     → the designer and design-crit already looked; the orchestrator consumes
       qa.py --json and slide_body.py, never pixels.

"Main session" = the hook input carries no `agent_type` (the reference
documents `agent_id`/`agent_type` as present only inside a subagent). Inside
any subagent the hook is a no-op, so designers keep writing and auditors keep
their (capped) renders.

"Deck folder" = the file's directory (or a parent within 2 levels) holds
deck-state.json or NN-*.html files. Anything else — a screenshot in
Downloads, an html file in an unrelated project — is untouched: this guard
fails open outside deck work.

Output: PreToolUse deny is `hookSpecificOutput.permissionDecision: "deny"` +
`permissionDecisionReason` (hooks reference, PreToolUse decision control).
Exit 0 always.
"""
import json
import os
import re
import sys

SLIDE_RE = re.compile(r"^\d{2}-[\w.-]*\.html$")
IMAGE_RE = re.compile(r"\.(?:png|jpe?g|gif|webp)$", re.I)


def deny(reason):
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": reason,
    }}))


def is_deck_folder(path):
    """True if `path` or a parent up to 2 levels above looks like a deck folder."""
    probe = os.path.abspath(path)
    for _ in range(3):
        try:
            entries = os.listdir(probe)
        except OSError:
            entries = []
        if "deck-state.json" in entries or any(SLIDE_RE.match(e) for e in entries):
            return True
        parent = os.path.dirname(probe)
        if parent == probe:
            break
        probe = parent
    return False


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0

    if payload.get("agent_type"):
        return 0  # inside a subagent — not the orchestrator's lane

    tool = payload.get("tool_name")
    file_path = (payload.get("tool_input") or {}).get("file_path") or ""
    if not file_path:
        return 0
    base = os.path.basename(file_path)
    folder = os.path.dirname(os.path.abspath(file_path))

    if tool == "Write":
        if SLIDE_RE.match(base):
            deny(
                f"BLOCKED (orchestrator lane): {base} is a slide file. Slides are created "
                f"only inside a deck-designer spawn (new_slide.py → Edits → log_slide.py), "
                f"never by the orchestrator — a full Write here is how five hand-typed "
                f"slides and a retyped head ended up in one real deck. Route it: spawn or "
                f"SendMessage the owning designer with ≤ 3 numbered fixes. Text-only fixes "
                f"on ≤ 3 slides may use Edit directly."
            )
            return 0
        if base == "narrative-outline.md" and is_deck_folder(folder):
            deny(
                "BLOCKED (orchestrator lane): narrative-outline.md is written by the "
                "deck-narrative agent, which has Write and owns the briefs. Send the gap back "
                "to it (SendMessage if alive, else a fresh spawn) instead of retyping the "
                "outline — that cost 26 KB of output tokens in one real session."
            )
            return 0
        return 0

    if tool == "Read" and IMAGE_RE.search(base) and is_deck_folder(folder):
        deny(
            f"BLOCKED (orchestrator lane): {base} is a slide render inside a deck folder. "
            f"The designer looked at it when it built the slide and design-crit judges "
            f"composition; the orchestrator verifies from files — `qa.py --deck-dir D --json` "
            f"for geometry, `slide_body.py` for content, the review harness for the user's "
            f"eyes. Reading renders is what filled two orchestrator sessions to 600–800 K "
            f"context. If a human needs to see it, hand over the preview URL."
        )
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
