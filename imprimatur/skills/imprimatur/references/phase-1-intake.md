# Phase 1 — Intake & diagnosis (detail)

Read on entering phase 1. `SKILL.md` §1 carries the procedure; this file carries the
questions in full, the boundaries, and the fast-track rule.

## The questions, in order (ask only what you do not already have)

1. **Audience** — executive / mixed (engineers + PMs + execs) / technical. Sets depth, jargon, pacing.
2. **Outcome** — status update / pitch / capability brief / Executive Readout / proposal / case study. Sets opening, structure, closing.
3. **Length** — target 7–15 slides (cover + N content + close).
4. **Context** — client, project, your role, key constraint. Used on the cover and in eyebrows.
5. **Must-haves** — 3–6 things that MUST appear regardless of structure.
6. **Anti-references** *(optional, valuable)* — what the deck must NOT look or sound like
   ("not a wall of identical cards", "no hypey sales tone"). Recorded in `deck-brief.md` so
   every agent steers clear.

Example: *"Got it. Before we start — will the client team be mostly executives, technical
leads, or mixed? 8, 12 or 15+ slides? What are the non-negotiables (e.g. 'show current SAP
pain', 'prove ROI in 18 months')?"* Do not proceed on a vague brief; five minutes here
saves thirty of rework.

## Source materials — delegate the reading

Never `Read` a PDF, DOCX, PPTX or VTT transcript into your own context: a 2.5 MB PDF is
the single largest tool result ever seen in an orchestrator transcript, and it stays in
context for the rest of the session. Instead spawn an **`Explore` subagent** (medium
breadth) with the file paths and this instruction: *extract the facts, figures, quotes and
named entities a deck could use, with a citation (file + page/slide/timestamp) on every
line, and write them to `<deck>/Input/source-notes.md`; keep it under 6 KB; do not
interpret.* `python-pptx` / `python-docx` are installed for it; `markitdown` is not assumed
— it should check before reaching for it. You read `source-notes.md` (small), the narrative
agent reads it too and may open the raw sources itself when a fact it needs is missing.

## External content vs internal design mechanism — a boundary you hold all pipeline long

Everything a deck needs falls into one of two buckets, sourced by different people.
*External content* — client facts, logos, quotes, verified data, screenshots, the source
materials above — the pack cannot contain any of that; gathering it is your job. *Internal
design mechanism* — which template a content shape maps to, whether the pack ships a
component for it — belongs to whoever has actually looked at the pack: you at phase 4a via
`pack_inventory.py` + `content-shape-map.md`, and the designer when it escalates. On a
real deck a shallow `find -iname "*map*"` over the pack came up empty, an external map
image was pasted in, and the host template already carried a purpose-built native
component. If you suspect the pack lacks something, say so in the plan and let the designer
confirm from the anatomy doc; never assert the negative yourself and substitute an
external asset.

## Set the taste dials

Default them, then surface for confirmation (`taste-dials.md` has the full table):

- **Density** (`sparse` / `balanced` / `dense`) — from audience: executive → sparse, mixed →
  balanced, technical → dense.
- **Variance** (`low` / `medium` / `high`) — from outcome: pitch / capability brief /
  Executive Readout → high, status update → medium, internal update → low.

One line: *"For an executive pitch I'd set density **sparse**, variance **high** — want it
denser or more uniform?"* The dials are how this pipeline prevents its #1 failure mode
(a monotonous wall of card slides); whatever is agreed is the source of truth.

## Write the two files

- **`deck-brief.md`** from `templates/deck-brief-template.md`, in the deck folder, before the
  narrative handoff: intake + dials + anti-references + per-deck voice, so narrative,
  designer and design-crit read the same locked intent instead of re-deriving it from chat.
- **`design-decisions.md`** from `templates/design-decisions-template.md`, title filled,
  otherwise empty. Phase 4a fills the plan into it; `log_slide.py` updates it per slide;
  design-crit and every fresh designer read it. It is the durable record that makes
  parallel chunk agents and a resumed session behave like one designer.

## Fast-track for small internal decks

The full ceremony (separate skeleton approval, review-harness offer) is sized for
client-facing pitches. Fast-track applies only when **all three** hold: the deck is
**internal**, AND variance is **`low`**, AND it has **7 or fewer slides**. A client-facing
deck never fast-tracks, however small. When it applies: present intake summary + skeleton in
**one** message for a single approval, and at §9 offer a plain "look at the preview and tell
me what to change" instead of generating the click-to-comment harness (generate it if the
user asks or has more than a couple of comments). Skipping the harness must be a **recorded
decision, never a drift**: say *"fast-track applies (internal, variance=low, N≤7)"* and set
`"review": { "fast_track": true }` in `deck-state.json` — `export_gate.py` blocks an export
with neither a review round nor this record. What does **not** shrink: the gates — static
check per write, batch QA per chunk, both audits, and export still requires explicit
acceptance with zero open comments.

## Done when

- [ ] Audience, outcome, length, context, must-haves locked; anti-references captured or explicitly skipped
- [ ] Taste dials defaulted, stated, confirmed
- [ ] Sources (if any) extracted to `Input/source-notes.md` by an Explore subagent — not read by you
- [ ] `deck-brief.md` and an empty `design-decisions.md` written to the deck folder
- [ ] User confirms readiness for structure planning
