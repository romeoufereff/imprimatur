# Design craft

Craft rules that hold whatever brand is loaded. They came out of a real design system, but
none of them depend on it: every concrete value — a colour, a size, a weight — comes from the
active pack's manifest, and this file only says how to *use* whatever the pack declares.

Read this alongside the pack's own `SKILL.md`, which carries the brand half: the token quick
reference, the gradients, the logo, and the template library. If the two ever disagree about a
number, the pack wins — it is the thing that knows the brand.

## Typography

- Display / section titles: the pack's **lightest** sanctioned weight — the most
  distinctive rule in most systems, and the one most often lost when a slide is
  generated from memory rather than copied
- Slide content titles: its **boldest**
- Body copy: the weight its `body` type step declares
- **Only the weights in `typography.allowedWeights`.** Three may coexist on one slide when
  each plays a role (light display + bold title/emphasis + regular body). Anything outside
  that list is a `validate.py` FAIL, so read the list rather than assuming the usual three.
- Eyebrow: `text-[16px] font-bold uppercase tracking-[0.22em] text-<prefix>-muted`
- Body bullets: `text-[20px] text-<prefix>-body leading-relaxed`
- Sentence case everywhere except eyebrows

### Minimum font sizes

Three tiers, each read from the pack rather than restated here:

| Text role | Minimum |
|---|---|
| Body copy, bullets | the pack's `body` type step |
| Labels, sub-labels, footnotes, pill text, SVG sub-labels | its `label` step |
| Eyebrows and captions (chrome) | its `caption` step |

**The absolute floor is `typography.minFontSizePx`** — `validate.py` FAILs anything below it,
and it is the caption role's size, not a loophole for shrinking content to fit. Print the
current values with `python3 {PLUGIN}/scripts/ds_config.py`; a pack with a larger scale moves
all three.

> These floors (and the whole type scale) were raised in 2026-07 after a full live deck
> review: the previous scale (11px eyebrows, 13px labels, 16–18px body) read fine in a
> browser at 100% but was consistently judged "too small" slide-by-slide by the audience
> the decks are actually built for. Do not quietly shrink text to fit a layout — cut copy
> or change the layout instead.

---


## Layout rules

### Cross-column row alignment: one shared grid

To vertically align paired rows across two columns (risk ↔ mitigation, problem ↔ solution,
before ↔ after), use **ONE CSS Grid** with both members of each pair placed in the **same
explicit `grid-row`** — never two independent per-column grids or flex stacks:

```html
<div class="grid flex-1" style="grid-template-columns: 1fr 1px 1fr; column-gap: 64px;
     row-gap: 36px; grid-template-rows: auto repeat(3, auto) 1fr auto;">
  <p style="grid-column:1; grid-row:1;">LEFT HEADER</p>
  <div class="bg-<prefix>-rule" style="grid-column:2; grid-row:1 / 6;"></div>  <!-- divider -->
  <p style="grid-column:3; grid-row:1;">RIGHT HEADER</p>

  <div style="grid-column:1; grid-row:2;">…left item 1…</div>
  <div style="grid-column:3; grid-row:2;">…right item 1…</div>
  <!-- rows 3, 4 follow the same pattern -->

  <!-- bottom-pinned callout: the 1fr spacer row above absorbs remaining height -->
  <div style="grid-column:3; grid-row:6;">…callout…</div>
</div>
```

Why this is a hard rule: with two independent grids, each column's row heights are driven by
its own content, so matching `gap` values still drift (measured up to 38px of row-center
misalignment in a real deck review). A shared grid forces every row's height to the max of
both cells, and `items-center` inside each cell then gives exact vertical centering for free.

Alignment claims are verified **numerically** — `getBoundingClientRect()` center-diff between
paired elements, target 0px — never by eyeballing a screenshot. `{PLUGIN}/scripts/check_overflow.py`
shows the measurement pattern.

---


## Voice and tone

- Third person, noun-led. No "you", no "we" in body copy.
- Bullets read as **facts that landed**, not promises that aspire.
- **Never use:** "leverage", "synergy", "transformative", "unprecedented", "unlock",
  "ecosystem", "exciting", or exclamation marks (except "Thank you!" on the closing slide).

---


## SVG visuals

Four sanctioned sources, in order of preference:

1. **Template-embedded SVG** — many templates ship with diagrams; adapt labels only.
2. **A pack pipeline/flow snippet**, if the active pack ships one — for data pipelines and
   architecture flows; copy the `<svg>` block, adapt labels/colors/connectors only.
3. **`{PLUGIN}/skills/svg-reconstruct/` skill** — for radial/segmented/repeating-geometry shapes
   (donut, pie, gauge, cycle, hub-and-spoke, org chart, funnel, pyramid, chevron process,
   quadrant matrix, venn, swimlane roadmap, timeline — 20 types) or whenever a reference
   screenshot must be matched. Computes angles via trigonometry and iterates against a
   render-diff loop instead of hand-tuned path strings — use this before hand-authoring
   any shape on its Recipe Index.
4. **Bespoke SVG** — when the message is inherently spatial (flows, layers, rings,
   journeys, relationships, before/after states), build the visual. This is expected,
   not an exception — a deck where every visual idea is flattened into cards and bullets
   is a failure mode. **Build it through svg-reconstruct either way**: from a recipe when
   one fits, and when none does, author it under that skill's rules — `svgkit.geometry`
   for positions, `svgkit.presets` for colour, `svgkit.icons.place` for icons, and its
   **Design Principles** section read first. Crafting a diagram is not a licence to
   eyeball one; typing coordinates and judging the result by impression is the failure
   this routing removes.

### Rules for all SVG (including bespoke)

- Boxes: `<rect rx="16">`, gradient fill `url(#grad-box)`
- Future/inactive step: `fill="url(#grad-tint)"`, dashed connector
- Connectors: cubic bezier `<path d="M x1 y C cx1 cy cx2 cy x2 y">`,
  `stroke="url(#grad-line)"`, `marker-end="url(#arrow)"`
- Arrow marker: `<marker orient="auto-start-reverse">` filled triangle, `<a pack hex>`
- Drop shadow: `<filter id="box-shadow"><feDropShadow flood-color="<a pack hex>" flood-opacity="0.18"/></filter>`
- Step numbers: small white circle top-left of each box
- Sub-labels: `font-size="16" fill="<a pack hex>"` below the main row
- viewBox sized to content; place with `style="width:100%;flex:1"` to fill the content area
- **Any `<linearGradient>`/`<radialGradient>` used as a `stroke` or `fill` on a shape that
  might end up perfectly horizontal or vertical (a straight connector line, an axis-aligned
  divider) must set `gradientUnits="userSpaceOnUse"` with explicit `x1/y1/x2/y2` coordinates
  — never leave it on the SVG default (`objectBoundingBox`).** An objectBoundingBox gradient
  scales its coordinate space by the element's own geometric bounding box; a perfectly
  horizontal or vertical path has zero height or width, which makes that transform
  non-invertible — Chromium silently drops the paint with no console error. This shipped a
  real bug: a straight connector line in a bespoke "converging lanes" diagram rendered
  completely invisible, and it survived two rounds of manual screenshot review because
  nothing *looked* broken — there was just nothing there. `scripts/check_paint.py` catches
  this mechanically (part of `qa.py`, runs automatically on every slide write), but the rule
  is cheaper to just follow than to rely on catching after the fact: pin gradient coordinates
  in `userSpaceOnUse` any time a bespoke shape's geometry isn't guaranteed to have both
  nonzero width and height.

### Bespoke SVG additional rules

- Start from a `<defs>` block in one of the pack's own snippets, if it has one
  (`grad-box`, `grad-tint`, `grad-line`, `arrow`, `box-shadow`) — keep the ids.
- Text inside the SVG follows the type scale: primary labels 20–22px weight 700,
  sub-labels 16px `<a pack hex>`.
- The bespoke SVG **is the slide's focal point** — don't pair it with competing cards.
- Each labeled SVG node counts as one atomic item toward the deck's DENSITY-dial budget
  (sparse ≤8 / balanced ≤12 / dense ≤14 — see `taste-dials.md`, beside this file).
- Auditors judge bespoke SVGs against these rules, not against template mapping.

---

## Where the numbers come from

Nothing here hardcodes a value on purpose. When a rule says "the minimum body size" or "the
primary colour", the answer is in the active pack:

| you need | ask the pack for |
|---|---|
| a colour | `roles.<role>` resolved through `tokens()` in `{PLUGIN}/scripts/ds_config.py` |
| a type step | `typography` + the pack's `fontSize` scale |
| the smallest legal size | `typography.minFontSizePx` |
| allowed weights | `typography.allowedWeights` |
| the brand gradient | `gradients.canonical` |
| the safe canvas | `canvas.width` / `canvas.height` |

That indirection is what lets this file stay true across brands. If you find yourself wanting
to write a hex here, the rule belongs in the pack instead.
