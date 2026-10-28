# Automation — Claude Code hooks

Hooks ship **inside the plugin** at `{PLUGIN}/hooks/`, registered by `hooks/hooks.json` and
pathed through `${CLAUDE_PLUGIN_ROOT}`. Installing the plugin installs them — nothing to copy
into `~/.claude/`, no absolute path to fix up. They match by filename convention
(`NN-slug.html`), not by deck path, so they apply to any deck this skill produces. Hooks on
tool events are additionally scoped with the `if` field (`Edit(**/*.html)`,
`Bash(*batch_convert.py*)` …) so a non-deck session never spawns a hook process.

| Hook | Fires on | Enforces |
|---|---|---|
| `slide_write_check.py` | `PostToolUse` · `Write`/`Edit` of any `*.html` (acts on `NN-slug.html` only) | Runs **only** `scripts/validate.py` (~0.2 s, no browser) on the written file and returns `STATIC PASS <file>` or `STATIC FAIL <file>: <lines>` as `hookSpecificOutput.additionalContext`, which Claude Code injects into the model's context beside the tool result. Catches the cheap-to-fix-now class — off-palette hex, banned class, missing `data-template`, weight/size floors, a head that differs from its template's — before it is copied into the next slide |
| `designer_stop_gate.py` | `SubagentStop` · matcher `^imprimatur:deck-designer$` | Collects the `NN-*.html` files that agent wrote or edited (from **its own** transcript, `agent_transcript_path` — not `deck-state.json`, whose `written` rows may belong to an earlier chunk) and runs `scripts/qa.py --files … --json` on exactly those. Any FAIL → `{"decision": "block", "reason": …}`, so a designer cannot hand back a chunk that has not passed the browser checks. With the QA cache, a chunk the designer already checked costs ~1 s here |
| `orchestrator_guard.py` | `PreToolUse` · `Write`, `Read` | In the **main session only** (no `agent_type` in the hook input): denies a `Write` of a slide file, a `Write` of `narrative-outline.md` inside a deck folder, and a `Read` of an image inside a deck folder. `Edit` is untouched (text-only fixes on ≤ 3 slides stay allowed). Inside any subagent it is a no-op. The three rules were prose until the 2026-09-07 audit measured what losing them cost |
| `agent_header.py` | `SubagentStart` · matcher `^imprimatur:` | Injects `PLUGIN=… · PACK=… · DECK=… · DS_NAME=…` as `additionalContext` into every plugin agent at spawn. `DECK` comes from the spawn prompt's `DECK=` line (payload `prompt`, else the subagent's own transcript, else the parent transcript's newest Agent call for that type), else `$DECK`, else a deck-shaped `cwd`, else `<unset>`; `PACK` follows that deck's `deck-state.json`, or the prompt's `PACK=` when no deck resolves |
| `block_large_template_read.py` | `PreToolUse` · `Read` | **Blocks** reading any file under `{PACK}/templates/` larger than 100 KB (the two world-map templates are 827 KB each) and replies with the exact `new_slide.py` command to use instead. A body-region peek with `offset`/`limit` is allowed |
| `block_batch_slide_write.py` | `PreToolUse` · `Bash` | **Blocks** any Bash command that writes slide HTML — redirection, heredoc, `cp` onto a slide path, `sed -i`, or a loop writing `.html`. Slide files are created only via `new_slide.py` (one slide per invocation; a loop over it is still blocked) and edited only via `Write`/`Edit`. Engine scripts are allowlisted. Note for plugin maintainers: it also blocks a *maintenance* script whose text merely mentions a loop and a slide-shaped filename — write those with the `Edit` tool |
| `deck_consistency.py` | `PostToolUse` · `Write`/`Edit` of `deck-metadata.json` | Flags `slide_count` drift against the `NN-*.html` files actually on disk — the add/remove-a-slide checklist in `phase-7-8-assembly-preview.md` |
| `export_gate.py` | `PreToolUse` · `Bash` matching `batch_convert.py`, `html2pptx.py`, `build_pptx.py`, `pdf_renderer.py` | **Blocks** export if `annotations.json` has any `"status": "open"`, **or** if no review round is recorded — no `annotations.json` and neither `review.offered` nor `review.fast_track` in `deck-state.json`. The §9/§10 gate, mechanically |
| `export_notify.py` | `PostToolUse` · `Bash` matching the export scripts | macOS notification when an export finishes |

## Output contracts — copy them from the reference, not from another hook

Claude Code reads a different JSON shape per event, and a hook that uses the wrong one is
recorded as healthy (`hook_success` in the transcript) while its output is silently
dropped. Both 1.2.0 gates shipped that way and ran for a week doing nothing. The shapes
this plugin uses, per the hooks reference (2026-09-07):

| Event | Decision | Context |
|---|---|---|
| `PreToolUse` | `hookSpecificOutput.permissionDecision: "deny"` + `permissionDecisionReason` | `hookSpecificOutput.additionalContext` |
| `PostToolUse` | top-level `decision: "block"` + `reason` | `hookSpecificOutput.additionalContext` |
| `SubagentStop` / `Stop` | top-level `decision: "block"` + `reason`; print nothing to allow | `hookSpecificOutput.additionalContext` |
| `SubagentStart` | none | `hookSpecificOutput.additionalContext` |

`hooks/test_hook_contracts.py` pins these; `scripts/telemetry/hook_probe.py <session>` proves
them on a real session — a `hook_additional_context` attachment is the only record that the
model saw the text. After every reinstall, restart Claude Code and either run
`scripts/telemetry/live_probe.sh` (three headless sessions; needs `claude login`) or do the
four moves by hand in a fresh session — Edit a slide (expect `STATIC PASS`), try to Write
one and to Read a `.png` in a deck folder (expect two `BLOCKED (orchestrator lane)`
errors), spawn an imprimatur agent (it echoes a `PLUGIN=` header) — then run
`hook_probe.py` on that session. Verified this way for 1.3.0 on 2026-09-07.

## What the designer actually sees

The static verdict is the only per-write feedback. It arrives as a system reminder beside
every `Write`/`Edit` result on a slide, so a designer fixes a `STATIC FAIL` before moving on
and never needs to run `validate.py` by hand — if it ever does, the hook is broken and the
right move is to say so. Browser checks (overflow + collision on every slide, paint on
chart/pipeline/bespoke slides, logo geometry, gradient contrast, contrast hard-FAILs in the
orchestrator's whole-deck run) happen once per chunk via `qa.py --deck-dir D --files … --json`,
and the stop gate re-runs them (from cache when nothing changed) before the agent's report
is accepted.

## deck-motion and the hooks

`choreograph.py` rewrites every slide's `<head>` in one pass, which is exactly the shape
`block_batch_slide_write.py` exists to block — it is allowlisted (`ENGINE_SCRIPTS`) because
it appends an insert-only block to already-designed, already-audited slides: housekeeping,
no design judgment (the same argument that sanctions `_archive/` moves). The per-write
static check tolerates the block (insert-only head diff, nth-child selectors that no palette
or class regex can match); `qa.py` gains the motion row (`check_motion.py`) only for slides
that carry the block. A deck that declined motion at §1 never meets any of this.

## Maintenance

If a script moves or is renamed, update the matching `command` entry in `hooks/hooks.json`.
Running the skill *without* installing the plugin (a bare symlink into `~/.claude/skills/`)
means the hooks do not fire — install the plugin. Never keep a second copy of these hooks
registered in `~/.claude/settings.json`: the pre-plugin copies double-fired on every tool
call for two weeks and one of them errored on every write. Hook tests live in
`hooks/test_*.py` and run from `scripts/validate_all.sh` (also `pytest hooks/` via
`hooks/test_hooks_pytest.py`).
