# Phases 5–6 — Audit management and revision loops (detail)

## The two halves of compliance

**(a) Mechanical — already done by the time you get here.** Every slide write carried a
static verdict (`validate.py`: tokens, classes, floors, weights, `data-template`, head
identical to the pack base); every chunk ran one `qa.py` batch (overflow + collision on
every slide, paint on chart/pipeline/bespoke slides) and was stop-gated on it; you ran one
whole-deck `qa.py --deck-dir D --json` at 4d, which is also where contrast hard-FAILs
surface. Nothing is re-run per slide by anyone. Never hand a deck to the auditors with an
open `qa.py` FAIL.

**(b) Judgment — two read-only agents, spawned together.** Several rules have no script:
logo placement and sizing, eyebrow format, acronym expansion, contrast over gradient
backgrounds (which `check_contrast.py` defers), any content-traceability check you name
(a number on a slide must appear in `source-notes.md`). That is `brand-audit`. The ten
design frameworks, the named tells and the deck-level variance verdict are `design-crit`.

## Spawn both in parallel

Both prompts ≤ 3 KB, header block first, paths only:

```
PLUGIN=… · PACK=… · DECK=… · DS_NAME=…
Deck brief: <deck>/deck-brief.md · Plan: <deck>/design-decisions.md
Slides: <deck>/deck-state.json lists them (N slides); read bodies with slide_body.py
QA: run `qa.py --deck-dir DECK --json` once and treat FAILs as audit FAILs   (brand-audit only)
Plan check: `plan_check.py --deck-dir DECK` output is your deck-level tally   (design-crit only)
Extra checks: <content-traceability or client-specific rules, if any>         (brand-audit only)
Report once, in your definition's table format.
```

`run_in_background: true` for both; neither modifies files, so they cannot step on each
other. Do not restate the ten frameworks or the nine checks — they are in the agent
definitions.

## Merge into one revision batch

When both reports land, build one numbered fix list per slide: brand-audit FAILs (always
fix, exact line + token), design-crit `REVISE` rows you accept (judgment — accept the top
finding unless it contradicts the brief; document a decline in `design-decisions.md`
§ Deviations), and any deck-level finding (template swap, re-inserted breather → re-lock the
plan row and re-run `plan_check.py`). Route per `phase-4-design.md` § Revision routing —
one designer pass for the whole batch, ≤ 3 fixes per spawn/message, several spawns in
parallel if the fixes span chunks.

## Re-check discipline

After the designer reports `revised`:

- **Script-only re-check** is the default: `qa.py --deck-dir D --files <touched> --json`.
  A token swap, a reworded label, a resized element needs nothing more.
- **Judgment re-check** only when the finding was judgment-type (logo, eyebrow, focal point,
  narrative role) **and** the fix changed layout: one targeted `SendMessage` to the auditor
  that raised it, with `slide_body.py <slide>` output for that slide only. Never re-spawn an
  auditor for a re-check; never re-review the whole deck.
- **Deck-level tally** after a template swap comes from `plan_check.py`, not a second crit.

**Max 2 revision rounds per deck stage**, and the per-slide cap of 2 cycles still holds — a
slide needing a third cycle, or the same finding failing twice, escalates
(`escalation-and-errors.md`). Approved slides are frozen unless a §9 comment touches them.

## Examples of routing

- Brand-audit: *"Subtitle contrast fails — `muted-soft` is decorative-only below 18px; use
  `muted` on line 67."* → fix as given → script re-check.
- Design-crit: *"Title reads as label ('Status Update'); assertion: 'Q2 delivery on track:
  87 % sprint completion.'"* → accept unless narrative intended a label → designer edits
  the title → script re-check (a title edit does not change layout).
- Design-crit deck-level: *"template-monotony: slides 4, 5, 6 all `02-content-bullets`."* →
  re-lock slide 5 to `02-content-bullets-focal` in the plan → `plan_check.py` → the owning
  chunk agent re-creates slide 5 with `new_slide.py --force` → script re-check.

## Why parallel auditing is safe now

The old pitfall ("brand-audit finds a colour issue → designer fixes → design-crit reviews
old HTML") described a flow where fixes were applied *between* the two audits. They are
not: both audits read the same frozen set, and fixes are applied once, afterwards. Serial
audits cost 20 min per deck for no additional coverage.

## Done when

- [ ] Both auditors spawned in the same turn with the header block; both reports in
- [ ] One merged fix list routed in one designer pass (≤ 2 rounds)
- [ ] Touched slides re-checked by script (judgment re-check only where warranted)
- [ ] Deck-level verdict PASS (from `plan_check.py` + design-crit's named tells) or resolved
- [ ] `deck-state.json` shows every slide `approved`; no `pending`/`written`/`revised` left
