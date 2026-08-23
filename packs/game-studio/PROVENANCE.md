# Provenance — Game Studio Deck System

**Authored, not extracted.** No brand artefact was probed; every token below is a design decision made by whoever wrote this pack. Treat it as a starting point to be replaced by a real brand, not as a record of one.

| token | hex |
|---|---|
| `gs-primary` | #C40F4C |
| `gs-primary-mid` | #E8175D |
| `gs-accent` | #4F31D9 |
| `gs-deep` | #0A1026 |
| `gs-support-1` | #D18A00 |
| `gs-support-2` | #00A3AE |
| `gs-ink` | #0A1026 |
| `gs-body` | #1B2347 |
| `gs-muted` | #5B6486 |
| `gs-muted-soft` | #9AA1BE |
| `gs-rule` | #D9DCEA |
| `gs-tint` | #EDEFF7 |
| `gs-surface` | #F6F7FB |
| `gs-white` | #ffffff |
| `gs-viz-rose` | #E8175D |
| `gs-viz-amber` | #FFB000 |
| `gs-viz-cyan` | #00D3E0 |
| `gs-viz-violet` | #6B4DFF |
| `gs-viz-lime` | #B6F02E |
| `gs-viz-green` | #12B76A |
| `gs-viz-rose-soft` | #FF7FA6 |

Dropped as noise during probing: 0 colour cluster(s).

## Probe notes

- Pack was authored, not extracted. Every value here is a design decision, so the usual question 'is this really the brand's?' is answered by whoever wrote it, not by a source file.

## Amendments

### v1.1 — removed the left-accent-bar pattern; added 3 templates

**Removed the decorative rounded vertical bar next to text** (`w-[6px] rounded-[3px] bg-gs-*`),
present in exactly two places — `templates/05-quote.html:89` (beside the pull quote) and
`templates/04-two-column.html:106` (beside the "design pillar" callout). This is the pattern
`rules.banLeftAccentBars` exists to catch; the fixture already exercised it but neither shipped
template had tripped it before now. Replaced with the alternatives this skill's own
`references/amendment-patterns.md` documents as sanctioned:

- `05-quote.html`: an oversized decorative quotation mark (`text-[280px]`, 18% opacity,
  `data-decor-text="ok"`) sized against the real precedent for this pattern elsewhere in the
  ecosystem (`imprimatur-build`'s `34-pull-quote.html` uses `text-[320px]` for the same
  treatment) rather than guessed — an earlier 120px attempt at this size was visually
  negligible once rendered and corrected before shipping.
- `04-two-column.html`: the accent colour moved into the "Design pillar 01" label text itself
  (now `text-gs-accent`, matching this pack's own eyebrow-above-headline convention used on
  `01-title.html`/`02-section.html`), with a plain `border-t border-gs-rule` divider replacing
  the bar's role of separating it from the paragraph above.

Re-verified with `verify_pack.py` against the installed orchestrator: all templates pass,
`off-brand-fixture.html` still fails on all 11 rules it always has (the bar's removal did not
weaken `banLeftAccentBars` — the fixture still trips it).

**Added three templates** to fill real gaps in the deck as a pitch narrative: `09-agenda.html`
(numbered two-column contents list), `10-feature-grid.html` (design-pillar cards with outline
SVG icons — no accent bars, no emoji, per `iconPolicy`), `11-big-statement.html` (a full-bleed
thesis/vision breather slide, distinct in purpose from `02-section.html`'s divider and
`08-closing.html`'s ask). All three follow the existing templates' exact chrome (1920×1080
canvas, scaler, footer) and token usage; icons use `stroke="currentColor"` with a `text-gs-*`
class rather than literal hex, to stay inside the palette census.

**Also fixed in passing:** this pack's own `SKILL.md` template-library table was already stale
before this amendment — it listed six generic filenames (`01-cover.html`, `04-statement.html`,
`05-metrics.html`, …) that matched no file in `templates/`, and omitted `07-team.html` and
`08-closing.html` entirely. Corrected to the actual 11 files, since that table is what a deck
designer consults to pick a template and a wrong one actively misleads.

Verified: `audit_pack.py` clean (0 problems, 0 warnings) and `verify_pack.py` ACCEPTED —
templates pass, fixture fails on all 11 rules — after these changes.

### v1.2 — added 10 more templates (11 → 21)

The 3 templates added in v1.1 weren't enough for a full pitch deck; added 10 more to round out
the narrative arc a game-studio raise actually needs: `12-market-size.html` (TAM/SAM/SOM),
`13-comparison-table.html` (competitive feature grid), `14-timeline.html` (dated milestones),
`15-use-of-funds.html` (the ask, broken down), `16-media-showcase.html` (full-bleed gameplay
capture placeholder), `17-testimonial-grid.html` (short social-proof quotes, distinct from the
single hero pull-quote in `05-quote.html`), `18-process-flow.html` (pipeline diagram),
`19-org-chart.html` (studio structure), `20-risk-table.html` (risk/mitigation/owner), and
`21-platforms.html` (target-platform status badges).

None use the left-accent-bar pattern removed in v1.1. Icons and connector lines use
`stroke="currentColor"`/`fill="currentColor"` with a `text-gs-*` class rather than literal hex,
so they stay inside the palette census — an early draft of `18-process-flow.html` used literal
hex on its connector arrows and was corrected before shipping.

Two templates needed measured, not eyeballed, geometry rather than hand-guessed pixel offsets:
`14-timeline.html`'s dots sit in a fixed-height zone below a fixed-height date zone specifically
so every dot's centre lands on the connecting line regardless of label length (confirmed by
script: 0.00003px offset from the line's centre — effectively exact); `19-org-chart.html`'s
three child boxes are spaced so the middle child's centre lands exactly under the parent by
construction (400px boxes, 134px gaps), confirmed the same way (425.49998px vs 425.49998px).
Both were checked with a `getBoundingClientRect()` measurement in-browser, not by eye.

Verified: `audit_pack.py` clean (0 problems, 0 warnings) across all 22 files; `verify_pack.py`
ACCEPTED — all 21 templates pass against the installed orchestrator, fixture still fails on all
11 rules. Every new template was also screenshotted and visually reviewed before being counted
as done.
