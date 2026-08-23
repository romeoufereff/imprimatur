# Design Decisions Template

The orchestrator creates an empty copy of this as `design-decisions.md` in the deck folder
alongside `deck-brief.md`, before the designer agent writes slide 1. The **designer agent**
appends to it after every slide; the **design-crit agent** reads it before reviewing every
slide.

**Why this file exists, and why it isn't just the designer's own memory:** the designer
agent is spawned once and continued via `SendMessage` across the whole deck, so in the
common case it *does* remember its own earlier choices without needing a file. This file
exists for the cases where that isn't enough on its own:

- **Resuming a deck** in a new session — a fresh designer agent has no memory of a
  previous session's choices; this file is what lets it pick up consistently instead of
  re-deciding the accent color from scratch.
- **The design-crit agent** is a *different* agent from the designer — it never had the
  designer's memory in the first place, and needs an explicit, durable record to check
  slide 5 against what was decided for slide 1, rather than trusting its own read of five
  slides' worth of implicit pattern-matching.
- **A human (or a future Claude session) auditing the deck later** can see *why* a slide
  looks the way it does without reverse-engineering it from the HTML.

Keep it short — a running log, not prose. Update it, don't rewrite it from scratch each
time — later entries can supersede earlier ones (e.g. a template originally meant to be a
one-off gets reused; note that here rather than silently exceeding the variance dial).

---

```markdown
# Design Decisions — <Deck Title>

## Locked choices (do not deviate without a documented reason)
- Accent color: <e.g. "ds-blue only — no navy/purple/teal substitutes" — set at slide 1,
  binding for the rest of the deck>
- <other cross-slide constraints as they emerge — a recurring icon style, a specific chart
  color mapping, a decision to always left-align titles even where a template defaults to
  centered>

## Templates used (variance-dial tally)
| Slide | Template | Notes |
|---|---|---|
| 1 | 01-cover | — |
| 2 | 04-big-idea | breather |
| 3 | 02-content-bullets-asymmetric | — |

## Deviations
- <if a later slide had to break a locked choice, record why here — e.g. "slide 6 uses a
  bespoke SVG gradient instead of a flat accent fill because the convergence visual needs
  gradient direction to read as flow; still uses the locked accent color's hex as one
  gradient stop">
```
