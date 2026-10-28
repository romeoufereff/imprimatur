# Design Decisions — Bookkeeping regression fixture

## Locked choices
- accent: primary — gradient only per pack canon
- canvas: light throughout (no dark variants)
- cobrand: declared in deck-state.json (assets/client-logo.png, left) — never touch the logo row
- loop vocabulary: need → evidence → meaning → contract → spec → product → certify → release → steer (same words on 7 and 9)

## Slides
| # | File | Template | Visual | Focal | Status |
|---|---|---|---|---|---|
| 01 | 01-cover.html | 01-cover | none | Title and presenters | approved |
| 02 | 02-at-scale.html | 47-key-facts | none | Four profile facts | written |
| 03 | 03-why-now.html | 03-two-column | none | Meaning has no owner | revised |
| 04 | 04-engagement.html | 44-side-panel-narrative-left | none | Six certified products by year end | revised |
| 05 | 05-one-platform.html | 12-process-flow-diagram | bespoke | Layered platform map | revised |
| 06 | 06-control-plane.html | 05-section-divider-panel | none | Nothing changes silently | revised |
| 07 | 07-one-loop.html | 17-orbital-methodology | bespoke | Infinity loop crossing at the Contract node | revised |
| 08 | 08-change-gates.html | 38-table | none | Every gate is a person | revised |
| 09 | 09-accelerators.html | 08-product-cards-focal | none | Three accelerators, one loop | written |

## Deviations
- 02: 4th sub-metric added by duplicating the template's metric+rule pair; commodity lines moved to eyebrow
- 03: Review r1: split title kept; left rows = 154 use cases on 28 products (§8); proof panel → meaning has no owner
- 04: Review r2: rebuilt on 44-side-panel-narrative-left (old file in _archive/r2/); panel = delivery model
- 09: export: background layers split from text
- 05: Review r1: hub-and-loop SVG replaced by layered platform map (§8): 3 bands + foundation, the only accent fills
- 07: Bespoke host (full Write): orbital grid replaced by a computed infinity loop (two R220 circles + crossed internal tangents) - crossing = enlarged Contract node ('agent drafts · person approves'); review r1: oval -> infinity loop
- 08: Table cut to 3 rows x 3 cols; rule callout right of table and conformance ladder footer strip (brief structure, not in template); review r1: every Gate marker is a person
- 01: Round 1: title + accent line, subtitle and presenters/date; h1 width 1400→1760px so the title holds two lines
