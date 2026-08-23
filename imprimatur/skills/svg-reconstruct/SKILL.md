---
name: svg-reconstruct
description: |
  Rebuilds a diagram as near-pixel-perfect SVG from computed geometry rather than hand-tuned
  path strings — donut, pie, gauge, cycle, hub-and-spoke, org chart, funnel, pyramid,
  process chevron, matrix, venn, roadmap, timeline, flowchart and more, 20 recipe types in
  all. Uses trigonometry plus a render-versus-reference diff loop instead of eyeballing
  angles and iterating blind inside a slide's HTML.

  Use whenever a slide needs a radial, segmented or repeating-geometry visual, and always
  when the user has pasted or referenced a screenshot the diagram must match. Trigger on:
  "rebuild this SVG", "recreate this diagram", "here's a screenshot, make it look like this",
  "the donut/wheel/gauge diagram doesn't look right", "reconstruct this chart", or any
  request to match an existing visualization. Hand-authoring these shapes inline is what
  produces the rebuilt-three-times-because-the-angles-were-eyeballed failure this prevents.
license: MIT for the pipeline logic; the design-system pack it drives carries its own terms — see LICENSE.md
metadata:
  author: Roman Iuferev
---

# SVG Reconstruct

You rebuild reference visualizations as SVG for deck slides — geometry
computed, never eyeballed; gradients assumed present until proven flat;
icons reconstructed with real detail; curved/rotated text actually follows
its arc. This is a specialist sub-skill of `deck-designer`'s "Bespoke SVG
visuals" step (see `.{PLUGIN}/agents/deck-designer.md`), not a replacement for it:
deck-designer still owns the slide's chrome, title, and template choice —
this skill owns the diagram that fills the content area.

**Origin note:** this skill exists because a live donut-diagram rebuild
(a client deck, slide 8, "Data products are the building blocks") took three
manual iterations to get right — horizontal labels clipping segment edges,
then clipping the wrong direction, then finally correct once rotated along
the arc tangent. Every one of those iterations was a geometry problem that
trigonometry solves in one shot. That's the whole reason this skill is
parametric-config-first instead of "author inline SVG and eyeball it."

---

## Hard rules

- **Geometry only via `svgkit.geometry`.** Hand-written arc/path strings
  for a radial or segmented shape are a failure, full stop — even a
  perfect-looking one, because the next edit (a label, an added segment)
  will break in a way trig would have caught immediately.
- **Icons only via `svgkit.icons.place`** (the built-in curated Lucide set,
  or an injected resolver). No hand-drawn icon substitutes.
- **Assume gradients until proven flat.** Inspect every colored region in
  the reference before deciding it's a solid fill.
- **All image-specific values live in a config JSON** under `configs/` —
  never hard-code a reconstruction's numbers into a recipe's `.py` file.
  A recipe is reusable across every image of that diagram TYPE; a config
  is specific to ONE reconstruction.
- **The first render is always wrong. Always iterate** via the render-diff
  loop (`svgkit.render.verify_loop`) — do not ship round 1.
- **Design-system tokens only** for colors (`svgkit/presets.py`, which resolves them
  from the active pack), the pack's font stack
  for text (the module default), and the existing minimum type sizes
  (`presets.MIN_LABEL_PX` = 16, `presets.MIN_BODY_PX` = 20). This skill
  produces a diagram that still has to pass `brand-audit` once it's
  embedded in a slide — matching tokens from the start avoids a revision
  loop there.

---

## Workflow

### 1 · CLASSIFY

Identify the diagram type from the reference screenshot, or — for a
freeform diagram with no reference (a data-driven donut, a generated
flowchart from a described process) — from the data/labels themselves.
Check the Recipe Index below. If nothing matches, use `recipes/_generic.md`'s
decomposition approach — and if this exact shape recurs a second time,
graduate it to a real recipe (see README.md "Extending") instead of
re-improvising.

### 2 · MEASURE — write the Build Spec before any code

This is the step that most determines whether the reconstruction lands in
1 round or 5. Before writing the config JSON, state explicitly (as your
response to the user, or as a comment block if working unattended):

- **Canvas**: size, viewBox
- **Center point, all radii, corner radius** (for radial shapes)
- **Segment/node count, per-segment start/end angles, gap angle**
- **Gradient definitions**: type (linear/radial), angle/focal point, every
  color stop with hex + opacity, for EVERY colored region — not just the
  obviously-shaded ones
- **Icon inventory**: what each icon depicts (e.g. "person with tie +
  checkmark badge", not "a person icon"), and whether the built-in set
  (`svgkit.icons.available()`) covers it or a new path needs adding
- **Text inventory**: content, position, straight/rotated/curved, font
  size per line (multi-part labels like "Knowledge" + smaller "of SMEs"
  keep their size hierarchy — don't collapse to one size)

Only after this is complete does config-writing begin. Skipping straight
to a config JSON (or straight to inline SVG) is how geometry gets
eyeballed.

### 3 · BUILD

Fill in `configs/<name>.json` per the matching `recipes/<type>.md` schema,
then:

```python
from recipes.registry import get_builder
build = get_builder(cfg["type"])
svg_path = build(f"configs/{name}.json", f"configs/{name}.svg")
```

The builder calls `svgkit` for all math — a recipe's `.py` file should
contain layout/dispatch logic and essentially no raw trigonometry itself.

### 4 · VERIFY — render, diff, adjust the CONFIG not the code

**With a reference screenshot:**

```python
from svgkit import render
history = render.verify_loop(
    build, config_path, original_png=reference_screenshot_path,
    out_dir="configs/_verify", width=W, height=H,
)
```

Read `history[-1]`: `mae` (0 = identical), `worst_quadrant`, and the
written `heatmap_path` PNG. **Look at the heatmap** — it tells you *where*
the mismatch is, so the next config edit is targeted (a radius, an angle,
a color stop) instead of a guess across the whole image. Stops
automatically at `mae < 8` or after 2 rounds with no meaningful gain;
default cap is 6 rounds. If it stops without converging, that's a signal
the CLASSIFY step picked the wrong recipe or the MEASURE step missed a
structural element — reconsider, don't keep nudging numbers past round 6.

**Without a reference (freeform diagram):** there's no pixel target to
diff against, so `mae` isn't available — the gate is the Design Principles
checklist above instead. Render the SVG and check it against every bullet
there explicitly (depth, hue variety, label legibility, one focal point,
deliberate whitespace, restraint, contrast) before moving to REPORT. This
is not optional just because there's no reference — it's the only check a
freeform diagram gets, so treat it with the same rigor as a `mae` number.

**Never edit the recipe's `.py` file to fix one reconstruction's mismatch**
— that breaks every other config using that recipe. Fix the config; if the
recipe genuinely can't express what's needed, that's a recipe change
(rare, and it should improve the recipe for all future uses, not
special-case this one image).

### 5 · REPORT

State the final `mae`, and explicitly list any known remaining deviations
("icon simplified — no exact Lucide match for X", "gradient angle
approximated at N° — original may use a radial gradient instead"). Flag
ambiguity; do not silently ship a guess as if it were measured.

### 6 · Hand off to deck-designer

The recipe's `build()` returns a path to a standalone `<svg>` document.
To embed it in a slide's content area (per
`deck-designer/SKILL.md`'s "Bespoke SVG visuals" host-template pattern):

1. Open the built SVG file and take everything between `<defs>...</defs>`
   and the closing `</svg>` (or call `svgkit.canvas.fragment()` from the
   start instead of `svgkit.canvas.svg()` if building custom — it returns
   `(defs, body)` unwrapped for exactly this purpose).
2. Merge the `<defs>` content into the host template's own `<svg viewBox=
   "..." style="width:100%;flex:1">` — watch for `id` collisions with the
   template's own `grad-box`/`grad-tint`/`arrow`/`box-shadow` ids from
   a `<defs>` block in one of the active pack's snippets, if it provides one; rename if needed.
3. Rescale: the recipe's config `width`/`height` almost never matches the
   host template's content-area viewBox. Either regenerate the config at
   the target viewBox dimensions (preferred — keeps stroke widths and font
   sizes correct at the final size) or wrap the fragment in a `<g
   transform="scale(...)">` (acceptable but stroke widths won't scale
   proportionally in older renderers — verify visually).
4. Run the slide through the normal pipeline: `deck-designer`'s Step 4
   self-check, then `brand-audit`, then `design-crit` — this
   skill's output is not exempt from those gates just because the
   geometry is provably correct. A correct donut can still use an
   off-brand gradient stop or an undersized label.

---

## Recipe Index

| Type | When the reference looks like… |
|---|---|
| `donut` | A ring of N labeled wedge segments around a central hub word |
| `pie` | A full disc split into proportional slices |
| `gauge` | A single value as a filled arc against a track, big number in the center |
| `cycle` | Steps arranged in a circle with curved arrows flowing between them (a loop) |
| `hub_spoke` | One central node with straight lines radiating to surrounding nodes (no flow arrows) |
| `funnel` | Descending stacked trapezoids (conversion funnel) |
| `pyramid` | Ascending stacked trapezoids, narrow apex to wide base (maturity/hierarchy) |
| `process` | Left-to-right interlocking chevron/arrow steps |
| `flowchart` | Boxes/diamonds connected by arrows (decision flow) |
| `org_chart` | Top-down hierarchy boxes with orthogonal connectors |
| `timeline` | Events plotted along a horizontal spine, alternating above/below |
| `roadmap` | Swimlane grid: lanes (rows) x time columns, item bars spanning columns |
| `matrix` | 2x2 quadrant grid with plotted points (BCG-style) |
| `venn` | 2-3 overlapping translucent circles |
| `kpi_cards` | Grid of metric cards: big number, label, icon, delta |
| `bar` / `line` / `pie` / `area` / `radar` / `stacked_bar` | Standard chart shapes — **only** for exact-match image reconstruction; for live-data charts in a deck, prefer `design-system/charts/` (ECharts) instead |

Full schema + build steps + failure checks for each: `recipes/<type>.md`.
Runnable example: `configs/example_<type>.json`.

---

## Design Principles

Geometric accuracy is necessary but not sufficient — a diagram can have
every angle computed correctly and still look flat, cluttered, or
illegible. These rules apply whether or not there's a reference screenshot
to match, and are what the render-diff loop (which only measures pixel
distance to a reference) cannot catch on its own — check for these by
looking at the rendered SVG, not just the `mae` number.

- **Depth over flat.** A "gradient" whose two stops are the same color is a
  flat fill wearing a gradient's clothes — it fails the "assume gradients
  until proven flat" hard rule even though the code path looks like it's
  using one. Every filled shape should read as having genuine light/dark
  variation unless a reference screenshot specifically proves it's flat.
  `presets.sequential_stops(i, n)` and `gradients.auto(id, base_color)`
  exist so a builder never has to fall back to a bare flat color by
  default — use them instead of `presets.PRIMARY` alone.
- **Hue variety on repeating shapes.** A donut/pie/cycle with 4+ segments
  in one repeated hue reads as one undifferentiated blob, not N distinct
  categories — `presets.sequential_stops` cycles the pack's viz sequence so
  adjacent segments are visibly different hues from the same family. Never
  invent hues outside the pack's palette to get variety.
- **Legibility beats literal instructions.** A config (or an agent
  defaulting to `curve:true` with no reference to check against) asking for
  curved text on an arc too short for it produces warped, overlapping
  letters — worse than the straight label it replaced. `text.smart_label` /
  `text.curve_legible` exist to catch this; don't force a curve a label
  doesn't fit. This is not a style preference, it's the specific failure
  this skill's own origin story hit by hand (see
  `references/embedding-example.md`).
- **One visual hierarchy, one focal point.** In a hub-and-ring diagram the
  hub should be the clear visual anchor (larger, higher-contrast, often
  with a subtle shadow lifting it above the ring) — not a same-weight puck
  competing with the segments. In any diagram, decide what the eye should
  land on first and make everything else visibly secondary (size, weight,
  or color, not all three maxed out everywhere).
- **Whitespace is a structural element, not leftover space.** Gaps between
  segments/nodes/boxes should be deliberate and consistent (a stated gap
  angle or px value, not "whatever's left"), and labels/icons need breathing
  room from the shape edges they sit inside — a label touching its
  segment's boundary reads as a bug even when technically inside it.
- **Restraint on color and type.** Stay inside the pack's role palette —
  don't reach for more hues than `presets.VIZ_SEQUENCE`/`WEDGE_SEQUENCE`
  offer, and don't mix more than the pack's one font stack. A diagram with
  a color or weight for every element competing for attention has no
  hierarchy left.
- **Contrast is load-bearing, not decorative.** Text on a fill needs enough
  luminance difference to read at the diagram's actual output size — white
  text on a light-tint fill, or `MUTED` text under `MIN_LABEL_PX`, fails
  even if it "matches the reference's vibe"; check actual contrast, not
  impression.

---

## Boot sequence

Read in this order before reconstructing anything:

1. This file (workflow + hard rules)
2. `recipes/<type>.md` for the classified type (schema + failure checks)
3. `configs/example_<type>.json` (a working reference config)
4. `svgkit/presets.py` (token defaults resolved from the active pack — colors, font, min sizes)
5. `{PACK}/SKILL.md` if the output is about to be embedded
   in a slide — the brand rules that govern the *slide*, not just the
   diagram, still apply (logo, footer chrome, eyebrow format, etc. are
   untouched by this skill; only the diagram content area is in scope
   here)
