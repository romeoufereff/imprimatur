# Automation — Claude Code hooks

Hooks ship **inside the plugin** at `{PLUGIN}/hooks/`, registered by `hooks/hooks.json` and
pathed through `${CLAUDE_PLUGIN_ROOT}`. Installing the plugin installs them — nothing to copy
into `~/.claude/`, no absolute path to fix up. They match by filename convention
(`NN-slug.html`), not by deck path, so they apply to any deck this skill produces.

| Hook | Fires on | Enforces |
|---|---|---|
| `slide_write_check.py` | `PostToolUse` · `Write`/`Edit` of any `NN-slug.html` | Runs **only** `scripts/validate.py` (~0.1 s, no browser) on the written file and returns the verdict to the model as `STATIC PASS <file>` or `STATIC FAIL <file>: <lines>` attached to the tool result. Catches the cheap-to-fix-now class — off-palette hex, banned class, missing `data-template`, weight/size floors, a head that differs from the pack's `slide-base.html` — before it is copied into the next slide. No browser checks here any more |
| `designer_stop_gate.py` | `SubagentStop` · matcher `^imprimatur:deck-designer$` | Collects the `NN-*.html` files that agent wrote or edited (from its own transcript — not from `deck-state.json`, whose `written` rows may belong to an earlier chunk) and runs `scripts/qa.py --files … --json` on exactly those. Any FAIL → the stop is refused with the failing verdicts and the re-run command as the reason, so a designer cannot hand back a chunk that has not passed the browser checks. The per-slide guarantee the old hook meant to give, enforced once at the end |
| `block_large_template_read.py` | `PreToolUse` · `Read` | **Blocks** reading any file under `{PACK}/templates/` larger than 100 KB (the two world-map templates are 827 KB each) and replies with the exact `new_slide.py` command to use instead. A body-region peek with `offset`/`limit` is allowed |
| `block_batch_slide_write.py` | `PreToolUse` · `Bash` | **Blocks** any Bash command that writes slide HTML — redirection, heredoc, `cp` onto a slide path, `sed -i`, or a loop writing `.html`. Slide files are created only via `new_slide.py` (one slide per invocation; a `for … new_slide.py` loop is still blocked) and edited only via `Write`/`Edit`. Engine rewriters (`new_slide.py`, `render_checks.py`, `log_slide.py`, `slide_body.py`, `pack_brief.py`, `fix_font_paths.py`, `apply_edits.py`) are allowlisted |
| `deck_consistency.py` | `PostToolUse` · `deck-metadata.json` write/edit | Flags `slide_count` drift against the `NN-*.html` files actually on disk — the add/remove-a-slide checklist in `phase-7-8-assembly-preview.md` |
| `export_gate.py` | `PreToolUse` · `Bash` matching `batch_convert.py`, `html2pptx.py`, `build_pptx.py`, `pdf_renderer.py` | **Blocks** export if `annotations.json` has any `"status": "open"`, **or** if no review round is recorded — no `annotations.json` and neither `review.offered` nor `review.fast_track` in `deck-state.json`. The §9/§10 gate, mechanically |
| `export_notify.py` | `PostToolUse` · `Bash` (same export scripts) | macOS notification when an export finishes |

## What the designer actually sees

The static verdict is the only per-write feedback. It arrives in the tool result of every
`Write`/`Edit` on a slide, so a designer fixes a `STATIC FAIL` before moving on and never
needs to run `validate.py` by hand. Browser checks (overflow + collision on every slide,
paint on chart/pipeline/bespoke slides, contrast hard-FAILs in the orchestrator's whole-deck
run) happen once per chunk via `qa.py --deck-dir D --files … --json`, and the stop gate
re-runs them before the agent's report is accepted. There is no "hook output" to read after
each slide — any sentence elsewhere claiming so is stale.

## Maintenance

If a script moves or is renamed, update the matching `command` entry in `hooks/hooks.json`.
Running the skill *without* installing the plugin (a bare symlink into `~/.claude/skills/`)
means the hooks do not fire — register them manually in `~/.claude/settings.json` with
absolute paths, or install the plugin. Hook tests live in `hooks/test_*.py`
(`pytest {PLUGIN}/hooks/ -q`): the JSON static verdict, the stop gate (a chunk with one
seeded overflow is blocked; a clean chunk passes), the batch-write allowlist, and the export
gate's allow/block cases.
