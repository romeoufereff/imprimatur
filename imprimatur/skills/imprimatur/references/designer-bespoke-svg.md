# Designer — bespoke SVG visuals

Read this only when a slide's `Visual:` is `bespoke`, `chart`, or `pipeline` with no pack
snippet. Read `design-craft.md` § SVG visuals and `{PLUGIN}/skills/svg-reconstruct/SKILL.md`
alongside it. Template-only slides never need any of the three.

## Why bespoke exists

Templates cover recurring layouts; the pipeline snippet covers architecture flows; ECharts
covers data. Some messages are inherently **spatial** — concentric scopes, layered stacks,
journeys, ecosystems, before/after transformations, custom flows. Flattening those into
cards and bullet columns is a failure mode even if every card passes audit. In those cases
you are expected to author a new inline `<svg>`; the brief's `Visual:` line is the mandate.

| Brief says | You do |
|---|---|
| `Visual: none` | Template content edits only — no SVG work |
| `Visual: chart (…)` | The pack's chart example if the inventory lists one (copy its script, replace only data arrays + axis labels); otherwise build from `charts.library` + the `viz` role colours; expect `validate.py` to look for `charts.requiredMarker` |
| `Visual: pipeline` | The pack's flow/pipeline snippet if it has one (copy its `<svg>`, adapt labels/colours/connectors, keep `<defs>` — gradients and markers are referenced by id); otherwise bespoke |
| `Visual: bespoke (…)` | Author a new SVG per the rules below |
| No `Visual:` line but the message is spatial | Flag to the orchestrator; do not silently default to cards |

## The rule: every bespoke SVG goes through svg-reconstruct

That is the default, not the exception — for crafting a diagram from a brief as much as for
reconstructing one from a screenshot. Hand-authoring path data and judging it by eye is the
failure the skill exists to remove: geometry comes from trigonometry, colour and type from
the pack's presets, and the result is checked in a render loop. A donut once shipped with
clipped labels and needed three manual fix passes because it was eyeballed
(`svg-reconstruct/references/embedding-example.md`).

- **The shape is one of its 20 recipe types** (donut/pie/gauge/cycle/hub-and-spoke/org-chart/
  funnel/pyramid/chevron-process/quadrant-matrix/venn/swimlane-roadmap/timeline/flowchart/…),
  or a screenshot must be matched → recipe + config. Never hand-write these path strings.
- **The shape is a one-off** (custom flow, ecosystem, a metaphor no recipe covers) → you author
  it, under that skill's rules: positions from `svgkit.geometry`, colours from
  `svgkit.presets` (`sequential_stops` / `gradients.auto`, never a bare flat fill), icons via
  `svgkit.icons.place`, and its Design Principles read first — depth over flat, hue variety on
  repeating shapes, legibility over literal instructions, one focal point, deliberate
  whitespace, restraint on colour and type, contrast as load-bearing.

Either way it returns an SVG fragment sized to your viewBox; merge its `<defs>` + body into
the host template's content area per its handoff section.

## How to build one

1. **Host template** — the locked plan names it: one with a title block and a large open
   area. Create it with `new_slide.py` exactly like a template slide; keep its chrome, title
   block and footer.
2. **Replace only the main visual area** with your `<svg>`. This is the one sanctioned case
   for a full `Write` of the file (say so in the `--deviation` line when you log the slide);
   everything outside the visual area stays byte-identical to the template.
3. **`<defs>`** — if the pack ships a snippet with a starter `<defs>`, start from it and keep
   the ids. If not, define your own from the pack's role colours. Never drop `<defs>` when
   pasting: an unpainted gradient fill is invisible, and only the batch `qa.py` paint check
   catches it.
4. **Type inside the SVG** — primary labels at the pack's `body`/`subhead` step in bold,
   sub-labels at its `label` step in the `muted-soft` role; viewBox sized to content;
   `style="width:100%;flex:1"` (full rules: `design-craft.md` § SVG visuals).
5. **It is the focal point** — no competing cards beside it. Each labelled node counts as one
   atomic item toward the DENSITY budget.
6. **Never ship round 1.** After the chunk's batch `qa.py`, render this slide
   (`qa.py --files <slide> --render /tmp/NN.png`, 960×540 by default) and look at it: flat
   fills, a hub that does not read as the focal point, labels touching shape edges are things
   only a look catches. This is the one place a PNG read is part of the designer loop.
7. **Log it** — `log_slide.py … --visual bespoke --focal "<metaphor in ≤ 12 words>"`; auditors
   judge the SVG against the pack's SVG rules, not against template mapping.

## Never nest convertible content inside a decorative-background div

If the deck also gets exported to PPTX (`pptx-export`), any HTML element that needs a
`background-image` (a pattern, a photo, a layered/radial gradient — the kind of decoration
a bespoke lanes/pipeline/flow layout tends to reach for as a grid-line or texture backdrop)
gets rasterized whole and **its children are baked into that screenshot instead of being
extracted as their own shapes**. A gradient pill badge, a text label, a card — anything with
real content — placed *inside* such a div silently becomes part of the picture, even though
it would otherwise export as an editable shape or textbox.

This shipped a real bug: a Sklum deck's parallel-lanes slide put gradient "pill" badges
(their own text included) inside a div whose background-image was a grid-line pattern; the
pills vanished into that raster and only turned up as a flattened picture in PowerPoint,
nothing looked wrong in the browser or the review harness.

**Rule: a decorative background pattern is always a sibling overlay
(`position:absolute; inset:0; pointer-events:none;`), never the parent of text, badges, or
cards.** Put the pattern in its own div stacked behind (or above, with `pointer-events:none`)
the real content — never wrap the content in it. `extract_ir.py` prints a `warn:` line for
any element it catches with a background-image AND non-trivial descendant text — treat that
like a svg2shapes fallback warning and restructure before calling the slide done.

## Raster images (screenshots, photos)

Embed as `data:image/png;base64,…` URIs — never file-path references. The review harness
renders slides in srcdoc iframes and the standalone harness runs from `file://`; relative
`assets/` paths 404 in both. Encode with
`python3 -c "import base64;print(base64.b64encode(open('img.png','rb').read()).decode())"`.
