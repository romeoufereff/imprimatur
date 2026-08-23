#!/usr/bin/env bash
#
# Everything, in one command.
#
# Four documents used to carry their own copy of "the acceptance test", with three
# different working directories and two different expected outputs between them. This
# is the one that runs, and the others link here.
#
# Usage:
#   scripts/validate_all.sh              # full run
#   scripts/validate_all.sh --fast       # skip the browser-rendered checks
#
# Exit 0 only if every stage passes.

set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN="$(dirname "$HERE")"
REPO="$(dirname "$PLUGIN")"
PY="${PYTHON:-python3}"
FAST=0
[[ "${1:-}" == "--fast" ]] && FAST=1

pass=0; fail=0
bold=$'\033[1m'; red=$'\033[31m'; green=$'\033[32m'; dim=$'\033[2m'; off=$'\033[0m'
[[ -t 1 ]] || { bold=""; red=""; green=""; dim=""; off=""; }

stage() {  # stage "name" command...
  local name="$1"; shift
  local out rc
  out="$("$@" 2>&1)"; rc=$?
  if [[ $rc -eq 0 ]]; then
    printf "  %s✓%s %-42s %s\n" "$green" "$off" "$name" "${dim}$(tail -1 <<<"$out")${off}"
    pass=$((pass+1))
  else
    printf "  %s✗%s %-42s\n" "$red" "$off" "$name"
    sed 's/^/      /' <<<"$out" | tail -20
    fail=$((fail+1))
  fi
}

echo "${bold}Imprimatur — full check${off}"
echo "  plugin: $PLUGIN"
"$PY" "$HERE/ds_config.py" | sed 's/^/  /'
echo

# ── 1. structure ──────────────────────────────────────────────────────────
# Every skill must be exactly one SKILL.md at skills/<name>/, with frontmatter the
# Skills API accepts. Nested SKILL.md files load in Claude Code but are rejected on
# upload, so this is what stops the plugin being unpublishable.
echo "${bold}structure${off}"
VALIDATOR=""
shopt -s nullglob
for cand in \
  "$HOME"/Library/Application\ Support/Claude/local-agent-mode-sessions/*/*/*/skills/skill-creator \
  "$HOME"/.claude/skills/skill-creator \
  "$HOME"/.claude/plugins/*/*/skills/skill-creator; do
  if [[ -f "$cand/scripts/quick_validate.py" ]]; then VALIDATOR="$cand"; break; fi
done
shopt -u nullglob
if [[ -n "$VALIDATOR" ]]; then
  for s in "$PLUGIN"/skills/*/; do
    stage "skill: $(basename "$s")" env -C "$VALIDATOR" "$PY" -m scripts.quick_validate "$s"
  done
else
  echo "  ${dim}- skill-creator not found; skipping frontmatter validation${off}"
fi
stage "agents have valid frontmatter" "$PY" - "$PLUGIN" <<'EOF'
import glob, re, sys, os
try:
    import yaml
except ImportError:
    print("pyyaml not installed — skipped"); sys.exit(0)
plugin = sys.argv[1]
found = sorted(glob.glob(os.path.join(plugin, "agents", "*.md")))
bad = [] if found else ["no agent definitions found under agents/"]
for p in found:
    m = re.match(r'^---\n(.*?)\n---', open(p, encoding="utf-8").read(), re.S)
    if not m:
        bad.append(f"{p}: no frontmatter"); continue
    try:
        fm = yaml.safe_load(m.group(1))
    except Exception as e:
        bad.append(f"{p}: {e}"); continue
    missing = {"name", "description", "tools", "model"} - set(fm)
    if missing:
        bad.append(f"{os.path.basename(p)}: missing {sorted(missing)}")
for b in bad:
    print(b)
print(f"{len(found)} agent(s), {len(bad)} problem(s)")
sys.exit(1 if bad else 0)
EOF

# ── 2. the engine must not know a brand ───────────────────────────────────
# Nothing ever checked that the engine obeys its own brand-agnosticism rule, which is
# how a retired palette accumulated across 72 sites in engine code.
echo
echo "${bold}brand firewall${off}"
stage "no unexplained hexes in engine code" "$PY" "$HERE/check_engine_clean.py"

# ── 3. the pack ───────────────────────────────────────────────────────────
echo
echo "${bold}pack${off}"
stage "brand rules (templates + snippets + charts)" "$PY" "$HERE/validate.py"
if [[ $FAST -eq 0 ]]; then
  # No mapfile here: macOS ships bash 3.2. Plain globbing, with nullglob so an absent
  # directory yields nothing rather than a literal pattern.
  shopt -s nullglob
  SLIDES=( "$REPO"/imprimatur-design-system/templates/*.html \
           "$REPO"/imprimatur-design-system/charts/*.html \
           "$REPO"/imprimatur-design-system/snippets/*.html )
  shopt -u nullglob
  if [[ ${#SLIDES[@]} -eq 0 ]]; then
    echo "  ${red}✗${off} no slides found under $REPO/imprimatur-design-system"
    fail=$((fail+1))
  else
    stage "WCAG AA contrast"         "$PY" "$HERE/check_contrast.py" "${SLIDES[@]}"
    stage "canvas bounds+collisions" "$PY" "$HERE/check_overflow.py" "${SLIDES[@]}"
    stage "silent paint"             "$PY" "$HERE/check_paint.py"    "${SLIDES[@]}"
  fi
else
  echo "  ${dim}- browser checks skipped (--fast)${off}"
fi
stage "audit eval: recall + precision" "$PY" "$HERE/run_evals.py" audit
stage "acceptance: templates pass, fixture fails" \
  "$PY" "$PLUGIN/skills/design-system-forge/scripts/verify_pack.py" \
  --pack "$REPO/imprimatur-design-system" --orchestrator "$PLUGIN"

# ── 4. the gates themselves ───────────────────────────────────────────────
# A gate that cannot fail is worse than no gate, so the gates have their own tests.
echo
echo "${bold}gates${off}"
stage "export gate"             "$PY" "$PLUGIN/hooks/test_export_gate.py"
stage "batch-slide-write block" "$PY" "$PLUGIN/hooks/test_block_batch_slide_write.py"
stage "svg-reconstruct unit tests" env -C "$PLUGIN/skills/svg-reconstruct" "$PY" -m pytest tests/ -q
stage "svg recipes build"       env -C "$PLUGIN/skills/svg-reconstruct" "$PY" -c '
import sys, glob, json; sys.path.insert(0, ".")
from recipes.registry import get_builder
n = 0
for c in sorted(glob.glob("configs/example_*.json")):
    get_builder(json.load(open(c))["type"])(c, "/tmp/_validate_all.svg"); n += 1
print(f"{n}/20 recipes build")'

echo
if [[ $fail -eq 0 ]]; then
  echo "${green}${bold}All $pass stage(s) pass.${off}"
else
  echo "${red}${bold}$fail stage(s) FAILED${off} ($pass passed)."
fi
exit $(( fail > 0 ))
