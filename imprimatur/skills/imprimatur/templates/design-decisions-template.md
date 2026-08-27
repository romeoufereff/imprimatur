# Design Decisions Template

The orchestrator creates an empty copy of this as `design-decisions.md` in the deck folder
alongside `deck-brief.md`, before the designer agent writes slide 1. The **designer agent**
appends to it after every slide; the **design-crit agent** reads it before reviewing every
slide.

**Why this file exists, and why it isn't just the designer's own memory:** for decks of
10 or fewer slides, one designer agent handles the whole batch in its own sequence of
turns, so in that case it *does* remember its own earlier choices without needing a file.
But that's no longer the only case this file has to serve:

- **Decks over ~10 slides get a fresh designer agent every 4–6 slides** (SKILL.md §4's
  agent-lifetime cap — kept lean because cost-per-turn grows with an agent's own
  accumulating transcript, and it's also where real session crashes happened). A chunk-2
  agent has *zero* memory of chunk 1's choices — this file, plus 2–3 sample slides the
  orchestrator points it at, is its entire onboarding. It is the **resumption contract
  between chunks**, not an optional backup: if it isn't current, the next chunk's agent
  has nothing correct to inherit and will re-decide (or contradict) earlier choices. This
  is exactly how a real deck lost a slide's content — a crashed agent's unlogged work left
  the file behind reality, and the next agent trusted the file over what had actually been
  decided. The orchestrator reads this file back to confirm it, rather than trusting a
  report that claims it was updated.
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
