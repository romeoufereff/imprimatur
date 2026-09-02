# Phase 4 — Design coordination (detail)

Read on entering phase 4. `SKILL.md` §4 carries the procedure; this file carries the plan
step in full, the spawn prompt, the archive step, and why the constraints exist.

## 4a · The design plan — before any slide

The orchestrator, not the designer, decides accent and template for every slide, once.
Chunk agents then run in parallel without needing each other's output.

1. `python3 {PLUGIN}/scripts/pack_inventory.py` — what this pack actually ships. Never name
   a template you did not see listed.
2. For each SLIDE BRIEF in `narrative-outline.md`, map `Structure:` + `Visual:` to a layout
   via `content-shape-map.md`, pick the pack template that provides it (prefer `-focal` /
   `-asymmetric` / `-compact` variants on a `high`-variance deck), and write the row into
   `design-decisions.md` (`| # | NN-slug.html | <stem> | <visual> | <focal ≤ 12 words> | planned |`).
3. Lock the accent as a `Locked choices` bullet (`- accent: <role>`) plus any cross-slide
   constraint the brief implies (icon style, chart colour mapping).
4. `python3 {PLUGIN}/scripts/plan_check.py --deck-dir D` — fix every violation it prints
   (max repeats, adjacent repeat on `high`, min visual slides, breather cadence, hero moment).
   Pass the breather slides explicitly — `--breather <stem1,stem2>` from your own plan — so
   the check is exact; the pack does not declare which templates are breathers.
   until it says PASS. This replaces the designer's old "rhythm check" and design-crit's
   manual tally.
5. Seed `deck-state.json` with one `pending` entry per slide (`n`, `file`, `title`,
   `template`, `visual`).

Suspect the pack lacks a component? Note it in the row's Focal cell ("confirm pack has no
map component") — the designer confirms from the anatomy doc; you do not substitute an
external asset (`phase-1-intake.md` § boundary).

## 4b · Archive stale slides

List `NN-*.html` in the deck folder that are not in `deck-state.json`. If any exist (a
previous run, a renumbered deck), tell the user once and move them:
`mkdir -p "<deck>/_archive/<YYYY-MM-DD>" && mv <deck>/<stale>.html "<deck>/_archive/<YYYY-MM-DD>/"`.
`build_review.py`, `qa.py --deck-dir`, `batch_convert.py` and `html2pptx.py` take the slide
list from `deck-state.json` when present, so an orphan cannot reach the harness or the
export — on a real deck eight orphans did, and the user annotated the wrong slides.

## 4c · Chunk and spawn — all chunks at once

Chunks are **always ≤ 5 slides** (slides 1–5, 6–10, 11–15 …), regardless of deck size. One
fresh `deck-designer` per chunk, **all spawned in the same turn** with
`run_in_background: true`. Each prompt is ≤ 3 KB, paths only:

```
PLUGIN=<abs> · PACK=<abs> · DECK=<abs> · DS_NAME=<name>      ← python3 {PLUGIN}/scripts/ds_config.py --header
Chunk: slides 6–10 of 12
Brief: <deck>/deck-brief.md
Briefs: <deck>/narrative-outline.md  (SLIDE 6 … SLIDE 10)
Plan:  <deck>/design-decisions.md   (locked — templates and accent are not yours to change)
Do: per slide new_slide.py → Edits → log_slide.py; static verdict fixed before moving on;
    then ONE `qa.py --deck-dir DECK --files <your five> --json`, fix, re-run on touched files
    only; report = `log_slide.py --summary` + escalations. No per-slide prose.
```

Never paste HTML, briefs, or the plan into the prompt; the agent reads the files. Never
omit the header — an agent without it spends 5–8 Bash calls locating the plugin.

## 4d · Wait, then verify from the files

When every chunk agent has reported (or been blocked by the stop gate and fixed itself):

```bash
python3 {PLUGIN}/scripts/log_slide.py --deck-dir D --summary        # the designers' batch report
python3 - <<'EOF'   # deck-state vs disk, one call
import json,glob,os; D="<deck>"
s={x["file"]:x["status"] for x in json.load(open(f"{D}/deck-state.json"))["slides"]}
disk=sorted(os.path.basename(p) for p in glob.glob(f"{D}/[0-9][0-9]-*.html"))
print("missing on disk:",[f for f in s if f not in disk]); print("not in state:",[f for f in disk if f not in s]); print(s)
EOF
python3 {PLUGIN}/scripts/qa.py --deck-dir D --json                    # whole deck, one browser launch
```

Never trust an agent's claim that it logged a slide — the summary and the state file are
what the auditors and any resumed session will see. A row missing that a report claims →
that chunk is not done; the same agent fixes the log (SendMessage) before you proceed. A
`written` slide with no file → same. Any deck-level `qa.py` FAIL → route to the owning
chunk agent as a revision before the audits.

## Revision routing

`SendMessage` the chunk agent that owns the slide if it is still alive (it has the slide in
context); otherwise a fresh `deck-designer` spawn with the header block, the plan path, and
≤ 3 numbered fixes with exact lines. Fixes on different slides with no contradictory intent
go in **one** spawn — each spawn re-pays the boot cost. Do not batch a fix that needs its
own focused loop, or two fixes touching the same region with opposite intents.

## Why it is built this way

- **One slide per Write/Edit, never a script.** On a real deck the session string-templated
  all N slides in one pass: inconsistent accent colours and an invisible bespoke SVG. The fix
  is not "broker every slide" — it is "no tool call produces more than one slide", enforced
  by `block_batch_slide_write.py` (`hooks.md`).
- **Copy-then-edit.** Retyping a template as output was 50 % of every slide's cost and the
  mechanism behind brand drift. `new_slide.py` byte-copies; `validate.py` FAILs a head that
  differs from the head of the template it names in `data-template` (additions tolerated,
  deletions/rewrites FAIL).
- **≤ 5-slide chunks, parallel.** One agent kept alive for a 23-slide deck peaked at 548 K
  context and 338 min; every session crash happened on a long-lived agent. Small parallel
  chunks bound context (≤ 150 K) and make wall-clock flat in slide count. The pre-locked plan
  is what makes parallelism safe: no chunk depends on another's decisions.
- **Batch QA + stop gate.** The per-write browser check ran 7 s per write and its output
  never reached the model; the static verdict now does, and the browser checks run once per
  chunk with the stop gate guaranteeing a chunk cannot report unless clean.

## Done when

- [ ] Plan locked in `design-decisions.md`, `plan_check.py` PASS, `deck-state.json` seeded
- [ ] Stale slides archived (or none found)
- [ ] All chunk agents spawned in parallel with the header block, ≤ 3 KB prompts
- [ ] `log_slide.py --summary` shows every slide `written`; state matches disk
- [ ] Whole-deck `qa.py --json` clean (or FAILs routed and re-cleared)
- [ ] Ready to spawn both auditors
