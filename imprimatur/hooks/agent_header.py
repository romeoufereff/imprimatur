#!/usr/bin/env python3
"""
SubagentStart hook (matcher: ^imprimatur:) — inject the boot header.

Every imprimatur agent definition opens with "your spawn prompt begins with
PLUGIN=… · PACK=… · DECK=… · DS_NAME=…; if it is missing, ask the
orchestrator". That put a hard dependency on the orchestrator remembering to
paste one line, and on the audit's transcripts it cost 5–8 Bash calls per
agent whenever it forgot. SubagentStart supports `additionalContext`, so the
harness can hand the header to every plugin agent itself — the orchestrator's
prompt no longer needs to carry it, and an agent can never start without it.

DECK resolution, in order: the spawn prompt's `DECK=` line (the payload's
`prompt` when the harness sends one, else the subagent's own transcript
`<session>/subagents/agent-<agent_id>.jsonl`, else the newest Agent/Task call
for this agent type in the parent `transcript_path`); `$DECK` in the
environment; the hook's `cwd` if it looks like a deck folder (deck-state.json
or NN-*.html present); else "<unset>". Deck folders live outside the session's
cwd (vault `Work/<client>/Slides/...`), so without the prompt the hook used to
print DECK=<unset> and the plugin's default pack — the EPAM pack on a
client deck (2026-10-23). When no deck resolves but the prompt names
`PACK=`, that pack is passed on as $DECK_DESIGN_SYSTEM, so the header never
contradicts the orchestrator's own line.

Output: `hookSpecificOutput.additionalContext` (hooks reference, SubagentStart —
context only, no decision control). Exit 0 always; never blocks a spawn.
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


def looks_like_deck(path):
    try:
        entries = os.listdir(path)
    except OSError:
        return False
    return "deck-state.json" in entries or any(SLIDE_RE.match(e) for e in entries)


# "PLUGIN=… · PACK=… · DECK=… · DS_NAME=…" — paths carry spaces, the separator is " · ".
FIELD_RE = {k: re.compile(rf"(?:^|\s){k}=(.+?)(?=\s+·\s|\s*$)", re.M) for k in ("DECK", "PACK")}
TAIL_BYTES = 4 << 20


def field(prompt, key):
    m = FIELD_RE[key].search(prompt or "")
    if not m:
        return None
    path = os.path.expanduser(m.group(1).strip().strip("`'\""))
    return path if os.path.isdir(path) else None


def _text(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(b.get("text", "") for b in content if isinstance(b, dict))
    return ""


def _tail_lines(path):
    try:
        with open(path, "rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            f.seek(max(0, size - TAIL_BYTES))
            data = f.read()
    except OSError:
        return []
    return data.decode("utf-8", "replace").splitlines()


def prompt_from_subagent_transcript(transcript, agent_id):
    """The first user message of this agent's own transcript, if already written."""
    if not transcript or not agent_id:
        return None
    stem = os.path.splitext(transcript)[0]
    path = os.path.join(stem, "subagents", f"agent-{agent_id}.jsonl")
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                try:
                    o = json.loads(line)
                except ValueError:
                    continue
                msg = o.get("message") or {}
                if o.get("type") == "user" and msg.get("role") == "user":
                    return _text(msg.get("content"))
    except OSError:
        pass
    return None


def prompt_from_parent_transcript(transcript, agent_type):
    """The newest Agent/Task tool call that spawns `agent_type` in the parent transcript."""
    for line in reversed(_tail_lines(transcript)):
        if agent_type not in line:
            continue
        try:
            o = json.loads(line)
        except ValueError:
            continue
        content = (o.get("message") or {}).get("content")
        if not isinstance(content, list):
            continue
        for b in reversed(content):
            if (isinstance(b, dict) and b.get("type") == "tool_use"
                    and b.get("name") in ("Agent", "Task")
                    and (b.get("input") or {}).get("subagent_type") == agent_type):
                return (b.get("input") or {}).get("prompt")
    return None


def spawn_prompts(payload, agent_type):
    """Candidate spawn prompts, most specific first (lazily — the parent scan reads a tail)."""
    if isinstance(payload.get("prompt"), str):
        yield payload["prompt"]
    transcript = payload.get("transcript_path") or ""
    yield prompt_from_subagent_transcript(transcript, payload.get("agent_id"))
    yield prompt_from_parent_transcript(transcript, agent_type)


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0
    agent_type = str(payload.get("agent_type") or "")
    if not agent_type.startswith("imprimatur:"):
        return 0
    if not os.path.isfile(os.path.join(SCRIPTS, "ds_config.py")):
        return 0

    deck = pack = None
    for prompt in spawn_prompts(payload, agent_type):
        if prompt:
            deck, pack = field(prompt, "DECK"), field(prompt, "PACK")
            if deck or pack:
                break
    deck = deck or os.environ.get("DECK")
    cwd = payload.get("cwd") or ""
    if not deck and cwd and looks_like_deck(cwd):
        deck = cwd

    env = dict(os.environ)
    if deck:
        env["DECK"] = deck
    elif pack:
        env["DECK_DESIGN_SYSTEM"] = pack
    cmd = [sys.executable, os.path.join(SCRIPTS, "ds_config.py"), "--header"]
    if deck:
        cmd += ["--deck-dir", deck]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=20, env=env)
        header = out.stdout.strip()
    except Exception:
        return 0
    if not header.startswith("PLUGIN="):
        return 0

    context = (
        f"{header}\n"
        f"Boot header injected by the plugin (SubagentStart). Use these absolute paths for "
        f"every script and file; do not search the filesystem for the plugin or the pack. "
        f"If DECK reads <unset>, take the deck folder from your prompt."
    )
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "SubagentStart",
                                             "additionalContext": context}}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
