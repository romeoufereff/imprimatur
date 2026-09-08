# Phases 2–3 — Structure planning and narrative handoff (detail)

## Phase 2 — default skeletons

| Deck type | Default skeleton |
|---|---|
| **Pitch (9–11)** | Cover → Agenda → Big Idea (hero metric) → 3× content → Architecture/Pipeline → Chart (proof) → Pull-quote (breather) → Two-column (risks + mitigations) → Closing (decisions + ask) |
| **Status update (6–8)** | Cover → Big Idea (status summary) → 2× detail → Roadmap-Gantt or Milestones → Two-column (risks + mitigations) → Closing (next steps + decisions) |
| **Capability brief (8–12)** | Cover → Big Idea or Big-Stat → 3–4 pillars → Methodology → Success stories / Pull-quote → Two-column comparison → Roadmap-Gantt → Closing |
| **Executive Readout (9–11)** | Cover → Situation → Proposed solution → Architecture (Pipeline-cards) → Risk mitigation (Two-column) → Investment (Table or Data-chart) → Timeline (Roadmap-Gantt) → Governance (Phase-leadership matrix) → Closing → Appendix |

**Build in variety up front** per the VARIANCE dial (`taste-dials.md`): the skeleton must
already include enough breathers (divider / big-idea / big-stat / pull-quote) and visual
slides (chart / pipeline / bespoke) to meet the dial's cadence and min-visual-slides count.
For a `high`-variance pitch that means at least one bespoke-visual moment and one
typographic hero moment in the outline. It is far cheaper to plan a breather here than to
discover a wall-of-cards deck after generation.

The skeleton is titles/messages only:

```
1. COVER: [deck title + engagement context]
2. BIG IDEA: [hero metric or situation summary]
3. PROBLEM: [current-state pain]
4. SOLUTION: [proposed vision]
5. ARCHITECTURE: [how it works]
6. PROOF: [metric, chart, or success story]
7. RISKS: [mitigation plan]
8. NEXT STEPS: [timeline, decision, CTA]
```

Ask: *"Does this skeleton work, or would you reorder anything?"* Lock it on approval.

**Done when:** skeleton within ±1 slide of the brief · includes every must-have · meets the
VARIANCE dial's breather cadence and min-visual count · user approved · ready for narrative.

## Phase 3 — narrative handoff

Spawn `deck-narrative` once (`Agent`, `subagent_type: deck-narrative`). The prompt opens
with the header block and carries paths, not pasted content:

```
PLUGIN=… · PACK=… · DECK=… · DS_NAME=…
Brief: <deck>/deck-brief.md
Sources: <deck>/Input/source-notes.md   (if any)
Skeleton (approved): 1. COVER … 8. NEXT STEPS …   (the numbered list, ≤ 1 KB)
Write the outline + one SLIDE BRIEF per slide to <deck>/narrative-outline.md and report
the path plus any gaps.
```

The structured brief the agent expects (audience, outcome, length, context, must-haves,
dials, anti-references) is all in `deck-brief.md` — do not restate it. **The narrative
agent writes `narrative-outline.md` itself** (it has `Write`); you never retype it. On a
real deck the orchestrator rewrote it twice (57 s + 52 s) for nothing.

**Narrative returns:** the outline (slide-by-slide arc with flow notes) and one SLIDE BRIEF
per slide, each with a `Visual:` line (`none` / `chart` / `pipeline` / `bespoke + metaphor`).

**Check the visual rhythm before phase 4a:** count briefs with `Visual:` ≠ `none` against
the VARIANCE dial's minimum (low ≥ 1, medium ≥ 2, high ≥ 3 incl. ≥ 1 bespoke for decks ≥ 8).
If short, push back to narrative — an all-cards deck is the `wall-of-cards` tell in
`anti-slop-tells.md`, and it is cheaper to fix in the briefs than after generation.
`plan_check.py` re-checks this mechanically at 4a; this is the human-readable early warning.

You do not edit the briefs — they are the source of truth for content strategy.

**Done when:** `narrative-outline.md` exists with one complete SLIDE BRIEF per slide ·
briefs cover every must-have · visual count meets the dial · no narrative gaps.
