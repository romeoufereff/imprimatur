#!/usr/bin/env bash
#
# Live hook probe — proves the installed plugin's hooks reach a real Claude Code
# session, not just their own tests. Runs three tiny headless sessions
# (`claude -p`) in a scratch deck folder and inspects their transcripts:
#
#   1. one Edit on a slide         → slide_write_check.py must produce a
#                                    hook_additional_context with STATIC PASS/FAIL
#   2. one Write of a slide file   → orchestrator_guard.py must deny it (main session)
#   3. one imprimatur agent spawn  → agent_header.py must inject PLUGIN=… into the agent
#
# Why this exists: the 1.2.0 hooks passed their own tests for a week while the
# harness silently dropped their output (wrong JSON nesting). Only a transcript
# proves delivery. Run it after every `release.sh` / reinstall.
#
# Usage:  scripts/telemetry/live_probe.sh [--keep]
# Needs:  the `claude` CLI on PATH, the plugin installed and enabled.
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN="$(dirname "$(dirname "$HERE")")"
PY="${PYTHON:-python3}"
KEEP="${1:-}"

command -v claude >/dev/null || { echo "claude CLI not on PATH"; exit 2; }

D="$(mktemp -d "${TMPDIR:-/tmp}/imprimatur-live-probe.XXXXXX")"
echo "scratch deck: $D"
"$PY" "$PLUGIN/scripts/new_slide.py" --deck-dir "$D" --template 01-cover --n 1 --slug cover >/dev/null || exit 2
printf '{"deck":"live probe","slides":[{"n":1,"file":"01-cover.html","title":"Cover","status":"written","template":"01-cover","visual":"none"}]}\n' > "$D/deck-state.json"
SLOT="$("$PY" - "$D/01-cover.html" <<'EOF'
import re,sys
html=open(sys.argv[1],encoding="utf-8").read()
body=html[html.find("<body"):]
m=re.search(r">\s*([A-Za-z][^<>{}]{8,60}?)\s*<", body)
print(m.group(1).strip() if m else "")
EOF
)"
[[ -z "$SLOT" ]] && { echo "could not find a text slot in the slide"; exit 2; }

run_session() {  # run_session <label> <allowed-tools> <prompt>  → prints session id
  local label="$1" tools="$2" prompt="$3" out sid
  out="$(cd "$D" && claude -p "$prompt" --allowedTools "$tools" --output-format json 2>/dev/null)"
  if printf '%s' "$out" | grep -q "Not logged in"; then
    echo >&2
    echo "The headless CLI (claude -p) is not logged in on this machine, so it cannot run the" >&2
    echo "probe sessions. Two alternatives that prove the same thing:" >&2
    echo "  a) in an interactive session (restarted after the install): Edit any NN-*.html," >&2
    echo "     try to Write one, try to Read a .png in a deck folder, spawn an imprimatur agent —" >&2
    echo "     you should see 'STATIC PASS', two BLOCKED (orchestrator lane) errors, and the agent" >&2
    echo "     echoing a PLUGIN= header; then: hook_probe.py <that-session-id>" >&2
    echo "  b) run \`claude login\` once, then re-run this script." >&2
    [[ -z "$KEEP" ]] && rm -rf "$D"
    exit 2
  fi
  sid="$(printf '%s' "$out" | "$PY" -c 'import json,sys
try:
    d=json.load(sys.stdin); print(d.get("session_id",""))
except Exception: print("")')"
  echo "  [$label] session=$sid" >&2
  printf '%s' "$sid"
}

echo "1/3 slide Edit (static verdict must reach the model)…"
S1="$(run_session edit "Edit,Read" "In the file $D/01-cover.html replace the exact text \"$SLOT\" with \"Live probe\" using the Edit tool (Read it first with offset 1 limit 40 if the tool requires). Make exactly one Edit, then reply with the single word DONE.")"

echo "2/3 slide Write from the main session (guard must deny)…"
S2="$(run_session write "Write" "Use the Write tool to create $D/02-probe.html with the content <html></html>. If the tool is refused, reply with the first line of the refusal verbatim; otherwise reply CREATED.")"

echo "3/3 imprimatur agent spawn (header must be injected)…"
S3="$(run_session spawn "Agent" "Use the Agent tool with subagent_type imprimatur:design-crit and this prompt: 'Do not run any tool. Reply with every line of your context that begins with PLUGIN= — verbatim — or NONE.' Then reply with the agent's answer verbatim.")"

echo
fail=0
probe() { "$PY" "$HERE/hook_probe.py" "$1" 2>/dev/null; }

echo "== 1. static verdict =="
P1="$(probe "$S1")"
echo "$P1" | grep -E "^slide_write_check.py|^\(other\)" || true
if echo "$P1" | grep -qE "^slide_write_check.py +[1-9][0-9]* +[1-9]"; then echo "PASS  STATIC verdict delivered as additionalContext"; else echo "FAIL  static verdict not delivered (fires>0, ctx=0 → JSON shape or 'if' scope)"; fail=1; fi
[[ ! -f "$D/02-probe.html" ]] && echo "PASS  guard: 02-probe.html was not created" || { echo "FAIL  guard: 02-probe.html exists — orchestrator_guard.py did not deny the Write"; fail=1; }
echo "== 2. guard denial (a PreToolUse deny is the tool result, not a hook record) =="
P2="$(probe "$S2")"
if echo "$P2" | grep -qE "^\s*orchestrator_guard.py: [1-9]"; then echo "PASS  orchestrator_guard.py denied the Write"; else echo "FAIL  no orchestrator_guard.py denial recorded for the Write"; fail=1; fi
echo "== 3. header injection =="
P3="$(probe "$S3")"; echo "$P3" | grep -E "^agent_header.py" || echo "(no agent_header row in the main transcript)"
MAIN3="$(ls -t "$HOME"/.claude/projects/*/"$S3".jsonl 2>/dev/null | head -1)"
if [[ -n "$MAIN3" ]] && grep -rq "PLUGIN=" "${MAIN3%.jsonl}/subagents/" 2>/dev/null && grep -rq "hook_additional_context\|Boot header injected" "${MAIN3%.jsonl}/subagents/" 2>/dev/null; then
  echo "PASS  agent received the injected header"
elif grep -q "PLUGIN=" "$MAIN3" 2>/dev/null; then
  echo "PASS  header text present in the session (agent echoed it)"
else
  echo "FAIL  no PLUGIN= header reached the agent"; fail=1
fi
echo "== legacy =="
if { probe "$S1"; probe "$S2"; } | grep -q "LEGACY"; then echo "FAIL  legacy hook still registered"; fail=1; else echo "PASS  no legacy hook rows"; fi

[[ -z "$KEEP" ]] && rm -rf "$D"
echo; [[ $fail -eq 0 ]] && echo "LIVE PROBE: all pass" || echo "LIVE PROBE: FAILURES — see above (sessions $S1 $S2 $S3)"
exit $fail
