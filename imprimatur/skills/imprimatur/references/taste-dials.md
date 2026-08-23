# Taste Dials

Two per-deck dials make *density* and *layout variety* explicit, tunable settings
instead of an implicit hope. The orchestrator sets them once at intake, records them in
`deck-brief.md`, and threads them into the narrative briefs and the designer's
self-check. Every sub-skill that judges density or visual rhythm reads the **deck's dial
values** rather than a hard-coded number.

**Why this exists:** the pipeline's most common failure mode is a deck of near-identical
card slides — every slide passes brand-audit, yet the deck reads as generic AI output.
That happens because "vary the layout" and "let it breathe" were advisory, not measured.
A dial turns them into a target the designer can hit and an auditor can check. The dials
are a *floor for quality*, not a license to cram: the absolute brand rules (body ≥20px,
nothing below the pack's `typography.minFontSizePx`, only its `allowedWeights`, and the
DENSITY dial's own bullets-per-column ceiling) always win. Density tunes
*how much content per slide is appropriate* — it never authorizes shrinking type to fit.

---

## DENSITY — how much per slide

Controls the atomic-item budget (headings + bullets + KV rows + cards + chart bars +
named people + labeled SVG nodes) and bullets-per-column.

| Setting | Atomic-item budget | Bullets / column | Feel |
|---|---|---|---|
| `sparse` | ≤ 8 | ≤ 4 | One hero element per slide; lots of air; executive-readout pacing |
| `balanced` | ≤ 12 | ≤ 5 | The system default; comfortable but substantive |
| `dense` | ≤ 14 | ≤ 6 | Detail-tolerant; for readers who want the data on the slide |

`balanced` keeps the ≤12 atomic-item budget the pipeline used before the dials existed, so
nothing regresses if a deck stays balanced. Bullets-per-column is the one number the dials
changed: it was a flat ≤6, and is now 4/5/6 across sparse/balanced/dense.

**Default from audience:** executive → `sparse` · mixed → `balanced` · technical → `dense`.

When the designer reports density, it cites the dial: e.g. *"7 items, budget 8 (sparse) ✓"*.
If a brief's content can't fit the dial's budget, that is a content problem to resolve
with narrative (cut, split, or appendix) — never a font-size problem.

---

## VARIANCE — how much the layouts vary

Controls template-repetition tolerance, breather cadence, and how many slides must carry
a real visual (chart / pipeline / bespoke SVG — i.e. a brief with `Visual:` ≠ `none`).

| Setting | Max same template | Adjacent repeats? | Breather cadence | Min visual slides (deck ≥ 8) |
|---|---|---|---|---|
| `low` | ≤ 3× | allowed | ≥1 per 5 dense slides | ≥ 1 |
| `medium` | ≤ 2× | allowed | ≥1 per 4 dense slides | ≥ 2 |
| `high` | ≤ 2× | **not allowed** (no two adjacent slides share a template) | ≥1 per 3 dense slides | ≥ 3, including ≥ 1 bespoke SVG |

A "breather" is a section divider, big-idea, big-stat, or pull-quote slide — one big
thing after a run of dense slides. A "visual slide" is any slide whose primary content
is a chart, pipeline, or bespoke SVG rather than cards/bullets.

**Default from outcome:** pitch → `high` · capability brief → `high` · Executive Readout
→ `high` · status update → `medium` · internal / quick update → `low`.

`high` is the right default for anything client-facing: the cost of a monotonous pitch is
high, and forcing one bespoke visual + no adjacent repeats is the cheapest reliable way
to break the "wall of cards" pattern. Pair this dial with
[anti-slop-tells.md](anti-slop-tells.md) — `template-monotony` and `wall-of-cards` are
exactly the tells VARIANCE is tuned to prevent.

---

## Who reads the dials

| Sub-skill | Uses DENSITY for | Uses VARIANCE for |
|---|---|---|
| **orchestrator** | Defaulting + surfacing at intake; recording in `deck-brief.md` | Shaping the skeleton: enough breathers + visual slides for the setting |
| **deck-narrative** | The `Density:` line of each SLIDE BRIEF | Spreading visual concepts so the deck hits the min-visual-slides count and avoids same-shape adjacency |
| **deck-designer** | The density budget in the Step-4 self-check | The rhythm check (Step 2) + template-repetition tally |
| **design-crit** | Framework 3 (Whitespace/Density) & 7 (Cognitive Load) targets | Flagging template monotony / missing breathers as a deck-level tell |

## Overriding the defaults

The defaults are a starting point, not a verdict. At intake the orchestrator states the
chosen dials and invites a change: *"For an executive pitch I'd set density **sparse**,
variance **high** — want it denser or more uniform?"* Whatever is agreed is written to
`deck-brief.md` as the source of truth for the rest of the run.
