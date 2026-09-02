# Design Decisions Template

`design-decisions.md` lives in the deck folder beside `deck-brief.md`. It is written by
scripts and read by everyone:

- **Orchestrator, phase 1** — creates it from this template, title filled, sections empty.
- **Orchestrator, phase 4a** — fills `Locked choices` and one `planned` row per slide (the
  design plan), then runs `plan_check.py --deck-dir D` against it.
- **Designer chunks, phase 4** — `log_slide.py --locked` before each slide (prints only the
  `Locked choices` block, ≤ 600 B); `log_slide.py --n N … --status written|revised` after
  each slide upserts that slide's row and appends a `Deviations` line if given.
  `log_slide.py --summary` prints the whole file — that is the designer's batch report.
- **design-crit and brand-audit** — read it for the locked accent and the template tally.
- **A fresh agent or a resumed session** — its entire memory of cross-slide decisions.

**The structure is fixed.** No prose paragraphs, no extra sections, no free-text entries:
`log_slide.py` parses it, and a 12-slide deck must stay under 4 KB so every agent can read
it on every boot. `Locked choices` ≤ 10 bullets; one table row per slide; one line per
deviation. If something does not fit this shape, it belongs in `deck-brief.md` (intent) or
in the chat report (escalation), not here.

---

```markdown
# Design Decisions — <Deck Title>

## Locked choices
- accent: <pack role, e.g. blue — no navy/purple/teal substitutes>
- <key>: <value>

## Slides
| # | File | Template | Visual | Focal | Status |
|---|---|---|---|---|---|
| 1 | 01-cover.html | 01-cover | none | Deck title | planned |
| 2 | 02-big-idea.html | 04-big-idea | none | The 4× gap number | planned |
| 3 | 03-problem.html | 03-two-column-asymmetric | none | AS-IS vs TO-BE columns | planned |

## Deviations
- 03: <one line — e.g. "full Write: >50 % of body replaced for the AS-IS/TO-BE pairing">
```

Column rules: `#` integer · `File` = `NN-slug.html` · `Template` = pack stem exactly as
`pack_inventory.py` lists it (host template for bespoke/chart slides) · `Visual` =
`none | chart | pipeline | bespoke` · `Focal` ≤ 12 words · `Status` =
`planned | written | revised` (the orchestrator writes `planned`; `log_slide.py` writes
the other two). `Deviations` lines are `- NN: <one line>` and are written only via
`log_slide.py --deviation`.
