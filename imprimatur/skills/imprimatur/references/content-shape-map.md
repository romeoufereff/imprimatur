# Content-shape → layout map

Used twice in the pipeline:

- **Orchestrator, phase 4a (design plan).** For every SLIDE BRIEF in `narrative-outline.md`,
  read the `Structure:` + `Visual:` lines, find the content shape below, and pick the pack
  template that provides that layout from `python3 {PLUGIN}/scripts/pack_inventory.py`. Lock
  the choice in `design-decisions.md` before any designer is spawned.
- **Designer, only on escalation.** A designer re-maps a slide only when the locked template
  cannot hold the brief (density overflow, no focal point) — it says so in its report and
  proposes the alternative from this table; the orchestrator re-locks.

The table maps a shape to the LAYOUT it needs, not to a filename — filenames belong to
whichever pack is loaded. A rich pack may offer three candidates (base / `-asymmetric` /
`-focal` / `-compact` variants — the variants usually carry stronger hierarchy, so prefer
them over the base file when the VARIANCE dial is `high`); a lean one may offer a single
flexible layout; if nothing matches, that is a legitimate case for a bespoke visual rather
than forcing the content into the wrong frame.

| Content shape | Layout it needs |
|---|---|
| Hero metric / single big idea | One focal element, large, with room around it |
| Two states: AS-IS vs TO-BE, risks vs mitigations, challenges vs benefits | Two balanced columns sharing one grid |
| 2–4 equal capability or feature columns | Equal-width columns, same vertical rhythm |
| Process flow, 3–5 ordered steps | Ordered horizontal sequence with connectors |
| Architecture pipeline, data flow diagram | Large open visual area beneath a title block |
| Chart plus commentary | Split: visual on one side, text on the other |
| Initiative rows with sub-items | Stacked rows, each with a heading and children |
| Use-case grid (4–8 cards) | Uniform card grid |
| Capability matrix, RACI, or structured comparison (phases/packages/SLAs) — row and column headers | Grid/matrix: row × column headers, cells hold short content |
| Platform or technology stack layers | Stacked horizontal layers, one per tier, top-to-bottom or reverse |
| Methodology with circular/orbital structure | Radial: a center hub with items arranged in a ring around it |
| Chapter break / section opener | Minimal: a large section label and little else — a breather between dense stretches |
| Cover | Title-only: deck/company name and a one-line descriptor, nothing competing |
| 8–12 KPI metrics in a scattered, non-linear field | Many small metrics arranged around a center or field, each its own weight |
| Partnership / capability overlap, or a 2×2 relationship | Overlapping circles (Venn) or a four-quadrant grid |
| Goals + category breakdown + one large metric callout | Mixed: a hero metric alongside a supporting breakdown list |
| Maturity levels ascending in sequence (5–6 steps) | Ascending staircase: steps rising left-to-right, each a level |
| Team roster or meeting participants | Uniform person-card grid: photo/name/role repeated |
| Agenda or table of contents | Numbered list of upcoming sections, minimal decoration |
| Pyramid / hierarchy / northstar goal | Pyramid: narrowing tiers stacked vertically, apex = top goal |
| Swim-lane engagement or project tier diagram, or ownership across tiers × phases | Swim lanes: horizontal bands, each a tier/role, content flows across |
| Client/stakeholder quote, social proof breather | Large quotation as the focal element, attribution below — a breather |
| Closing slide: decisions, next steps, the ask | Recap plus an explicit next step — ends on an action, not a restatement |
| Narrative + photo/screenshot | Image on one side (or full-bleed) with adjacent or overlaid narrative |
| Time-phased roadmap with date ranges (Gantt), or a milestone list | Horizontal timeline with bars (or dated line items) spanning a date axis |
| Donut/pie/gauge/cycle/hub-spoke/org-chart/funnel/pyramid/chevron-process/matrix/venn/swimlane-roadmap, or matching a reference screenshot | **`{PLUGIN}/skills/svg-reconstruct/`** inside the closest host template — see `designer-bespoke-svg.md`; never hand-author these |
| Spatial concept with no template match and no svg-reconstruct recipe (rings, custom flows, ecosystems, before/after) | **Bespoke SVG** inside the closest host template — see `designer-bespoke-svg.md` |

## Locking the plan — what goes in `design-decisions.md`

For each slide the plan row carries `# | File | Template | Visual | Focal | Status`:

- **File** — `NN-<slug>.html`; the slug is the skeleton's kebab-case title.
- **Template** — the pack stem exactly as `pack_inventory.py` lists it (`03-two-column-asymmetric`,
  not "two column"). For a bespoke/chart slide, the HOST template.
- **Visual** — `none | chart | pipeline | bespoke`, copied from the brief's `Visual:` line.
- **Focal** — ≤ 12 words, from the brief's `Emphasis:` line.
- **Status** — `planned` until a designer logs it `written`.

The cover row also locks the accent colour as a `Locked choices` bullet
(`- accent: <pack role name>`), so no chunk agent re-decides it. Then run
`python3 {PLUGIN}/scripts/plan_check.py --deck-dir D` — it checks the table against the
VARIANCE dial (`taste-dials.md`: max repeats, adjacent-repeat rule for `high`, min visual
slides, breather cadence, hero moment) and prints PASS or the exact violation. Pass
`--breather <stems>` for the slides you planned as breathers (chapter break, big idea,
pull quote, big stat) — without it the script falls back to a filename guess. Fix the plan
(swap a variant, re-insert a breather) until it passes; only then spawn designers.
