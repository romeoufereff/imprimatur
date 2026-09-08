#!/usr/bin/env bash
#
# Release checklist, in one command — encodes the install-topology lessons so
# they stop recurring:
#   * the installed copy is keyed by the version string in plugin.json, so an
#     unbumped edit is a silent no-op for the running plugin;
#   * the cache can drift AHEAD of source when a fix is hot-patched there
#     (2026-09-03), so the diff must be checked in both directions;
#   * a hook can pass its own tests and still be ignored by Claude Code, so the
#     last step is a live probe Roman runs after restarting.
#
# Usage:
#   scripts/release.sh <new-version>            # e.g. 1.3.0
#   scripts/release.sh <new-version> --fast     # skip browser stages in validate_all
#
# Steps: bump → hook tests + validate_all → engine-clean → reinstall →
#        diff cache vs source → print the post-restart probe command.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN="$(dirname "$HERE")"
MANIFEST="$PLUGIN/.claude-plugin/plugin.json"
PY="${PYTHON:-python3}"
NEW="${1:-}"
FAST="${2:-}"
[[ -z "$NEW" ]] && { echo "usage: release.sh <new-version> [--fast]"; exit 2; }

CUR="$("$PY" -c "import json;print(json.load(open('$MANIFEST'))['version'])")"
echo "current version: $CUR → $NEW"

# 1 · bump
"$PY" - "$MANIFEST" "$NEW" <<'EOF'
import json, sys
p, new = sys.argv[1], sys.argv[2]
d = json.load(open(p)); d["version"] = new
json.dump(d, open(p, "w"), indent=2, ensure_ascii=False); open(p, "a").write("\n")
print("bumped")
EOF

# 2 · gates
echo; echo "== gates =="
"$HERE/validate_all.sh" ${FAST:+--fast} || { echo "validate_all FAILED — not releasing"; exit 1; }

# 3 · reinstall
echo; echo "== reinstall =="
if command -v claude >/dev/null 2>&1; then
  claude plugin update imprimatur@imprimatur || { echo "plugin update failed"; exit 1; }
else
  echo "claude CLI not on PATH — run: claude plugin update imprimatur@imprimatur"
fi

# 4 · verify the cache matches the source, both directions
CACHE="$HOME/.claude/plugins/cache/imprimatur/imprimatur/$NEW"
echo; echo "== cache vs source =="
if [[ -d "$CACHE" ]]; then
  if diff -rq "$PLUGIN" "$CACHE" -x __pycache__ -x .in_use -x .DS_Store -x .pytest_cache; then
    echo "cache == source ($CACHE)"
  else
    echo "DRIFT between source and $CACHE — resolve before using the plugin"; exit 1
  fi
else
  echo "no cache dir at $CACHE yet (plugin update did not run?)"
fi

# 5 · the live probe — only a real session proves the hooks reach the model
echo
echo "== after restarting Claude Code, prove the hooks reach a real session: =="
echo "  $HERE/telemetry/live_probe.sh            # three headless sessions (needs: claude login)"
echo "or, in a fresh interactive session: Edit a slide (expect STATIC PASS), try to Write a"
echo "slide and to Read a .png in a deck folder (expect two BLOCKED errors), spawn an"
echo "imprimatur agent (it echoes PLUGIN=…), then:"
echo "  python3 \"$HERE/telemetry/hook_probe.py\" --latest"
echo "expect slide_write_check.py: fires ≥ 1, ctx ≥ 1, no LEGACY rows, no PROBLEMS."
