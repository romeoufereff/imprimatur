---
name: pptx-export
description: |
  Exports a folder of HTML slides to an EDITABLE PowerPoint (.pptx): text stays text, cards stay shapes, SVG diagrams become native grouped shapes. The sibling of pdf-export. Use whenever the user says "export to pptx", "make it a PowerPoint", "the client wants an editable version", or asks for PPTX at export.
compatibility: "Bash, Read; python: playwright, python-pptx, Pillow, numpy; playwright install chromium"
license: MIT for the pipeline logic; the design-system pack it drives carries its own terms — see LICENSE.md
metadata:
  author: Roman Iuferev
---

# PPTX Export

Turns an assembled, review-clean deck into an **editable** 16:9 PowerPoint. This is the
"client wants to edit it" export; `pdf-export` remains the canonical presentation-grade
output (run both when in doubt — the PDF is the fidelity reference).

```
NN-*.html ──▶ extract_ir.py (Playwright DOM walk @1920×1080)
                 │  per-slide JSON IR + assets/*.png     ← inspect THIS when debugging
                 ▼
              build_pptx.py (python-pptx)  ──▶ Deck.pptx (13.333in × 7.5in, 6350 EMU/px)
```

## Quick start

```bash
python3 "{PLUGIN}/skills/pptx-export/scripts/html2pptx.py" \
  --deck-dir "/path/to/deck" \
  --output   "/path/to/deck/DeckTitle-YYYY-MM-DD.pptx"
```

- Same glob discipline as pdf-export: default `[0-9]*.html`; `index.html` and
  `slide-review.html` are skipped defensively either way.
- Per-slide IR JSON + raster assets are kept in `<deck>/.pptx-ir/` — **debug the IR, not
  the pptx**. If an element is wrong in PowerPoint, find its node in the JSON first: a bad
  rect/color there is an extraction issue; a good IR rendered wrong is a builder issue.
- `--ir-dir <path>` keeps the IR somewhere else (a scratch re-export that must not touch
  the deck's own `.pptx-ir/`); pass the same `--ir-dir` to `ir_preview.py`.
- `--raster-fallback` — every slide becomes one full-slide screenshot picture:
  pixel-perfect, zero editability. The escape hatch when IR fidelity isn't good enough
  for a particular deck and there's no time to fix it.

## Fidelity contract (v2 — what's editable vs baked)

| HTML element | PPTX result |
|---|---|
| Text (any block whose children are all inline) | **Editable textbox** = the element's border box, exact; **insets = CSS padding + border, vertical anchor measured** (table-cell `vertical-align`, flex centring, padding — read off the rendered word boxes, so a centred cell stays centred when edited); styled runs: size px→pt (**×0.5**, `PT_PER_PX`: the 1920-px canvas maps onto the 13.333-in = 960-pt slide, so 1 px = 0.5 pt; the CSS ×0.75 assumes 96 dpi and renders all text 1.5× too large), **per-weight font names** (the pack family plus its weight, e.g. "Source Sans 3 300/400/700" — a bare family name plus a bold flag resolves unpredictably across families), **per-run family** (each run's computed `font-family` is in the IR; the first family in the stack that the pack declares in `typography.familyRequiredPattern` wins, so a two-family pack keeps its display face on titles — a client pack's Century Gothic over Arial; a family `pptx.fontFamilyByWeight` covers keeps its per-weight name, and bold is set only where the name cannot carry the weight), color, uppercase, **letter-spacing** (oxml `spc`), **per-paragraph line-height** (mixed-size cards keep their rhythm). The browser's ACTUAL line breaks are measured word-by-word (Range rects) and written as explicit paragraphs with **wrapping off** — renderer metric differences can never reflow a title into the element below it |
| Card / callout (solid bg or border) | **Editable rounded rectangle** — fill, border, corner radius; shadows off |
| `::before/::after` decorations (bullet dots, bars) | **Shape** (best-effort: solid-background, px-measurable pseudos) |
| Slide background (solid) | Slide background fill |
| Slide background (single linear-gradient — covers, dividers) | **Native gradient fill** (oxml `gradFill`, CSS→DrawingML angle mapped); text/logo stay editable on top |
| Slide background (layered/radial image) | Whole slide as one picture (fallback) |
| One gradient spanning several elements (`background-size`/`-position` sized across header bars) | Each shape gets **its own slice** of the shared ramp (`gradients.py`), so the colour continues across shapes instead of restarting per shape. Unsliceable layouts (a tile seam inside the element) print a warning and keep the full ramp |
| SVG `<text>` with inline `<tspan>` runs (a coloured word inside a line, e.g. `<tspan fill=blue>trading</tspan>-subdomain-1`) | **One textbox, one run per segment**, each with its own colour; the text after a tspan (its XML tail) is kept. Until 1.5.9 the tail was dropped and the tspan fill ignored, so a two-tone repo name exported as just its first word (a client repository map, 2026-10-07). Positioned tspans (own x/y/dx/dy) still start a new line |
| `<svg>` (diagrams, logo, icons) | **Native GROUPED SHAPES** (svg2shapes.py): rects/ovals/freeform beziers (`a:custGeom`)/textboxes with linear **and radial** gradient fills, **gradient strokes** (line `gradFill`), `userSpaceOnUse` ramps cut per shape, gradients that inherit stops/attributes through `xlink:href` (Illustrator exports; until 1.6.2 these fell back to a picture), arrowhead markers instantiated at path ends, dashes, drop shadows — movable, scalable as one, ungroup to edit any piece. Verified by re-rendering the parsed model and content-MAE-ing it against the source SVG (logo 0.0, cycle diagram 40.9, live-views hub with radial 18.6). Unconvertible SVGs (textPath curved labels, masks, radials with `gradientTransform`) fall back to **svgBlip** with a printed reason; `--svg-blip` forces blip mode for everything. **Chart or diagram is decided by provenance, not size**: an SVG a chart library drew (ECharts — `extract_ir.py` stamps `data-pptx-chart`) stays a picture; a hand-drawn SVG converts at any density up to a 500-element safety ceiling. Until 1.6.4 a 150-element cap doubled as the chart test, so a dense diagram (the 1&1 roadmap's knowledge-graph row, 180 elements) became a picture while a 42-element ECharts chart exploded into shapes. Authors override either way with `data-pptx="shapes"` or `data-pptx="picture"` on the `<svg>` or any ancestor (mark a hand-drawn SVG chart `picture`) |
| ECharts with `--native-charts` (opt-in) | **Real data-editable PPTX chart** (bar/line/pie) scraped from `chart.getOption()`, the pack's `viz` series colors; `null` gaps (forecast series) preserved; scrape miss → svgBlip fallback |
| `<img>` of an SVG (`src` a `.svg` file or `data:image/svg+xml` — the co-brand partner logo) | **Native grouped shapes**, same path as an inline `<svg>`: the file is parsed in a shadow root sized to the `<img>`, so its own `<style>` classes resolve (Illustrator logos) and nothing from the slide leaks in, and each element's computed paint is written onto it. A `brightness(0)` filter paints it black, `brightness(0) invert(1)` white (lockups on dark covers); any other filter, an unreadable file or a remote URL keeps the picture, with a note. Until 1.6.6 it was a 1x screenshot (an 86×31 px EPAM mark, soft when projected) |
| `<canvas>`, raster `<img>`, gradient-background elements (chips, blobs) | Picture at exact position (isolated screenshot — overlapping neighbors are hidden during capture) |
| Background-image element holding text/shapes (gridline track, layered gradient border, photo panel) | **Picture of the background alone**, its content exported as editable shapes on top (see "Background images under content") |
| `<sup>` / `<sub>` | Same-line run with a baseline offset (`a:rPr baseline` +30 % / −25 %) |
| Gradient text (`background-clip:text`) | Editable text with a **real per-run brand-gradient fill** (the pack's `svg.brandGradientStops`); the gradient spans each run's own box rather than the whole element — close for accent phrases. Checked BEFORE the raster branch; never a picture |
| Semi-transparent solid fills | Pre-composited over white (approximation) |
| Translucent gradient stops (`#FFF 0% → rgba(255,255,255,0) 100%` — the cover image-slot fade, a wash that fades to the canvas) | **Native gradient with per-stop alpha** (`<a:alpha>` on the stop). Until 1.5.8 the alpha was dropped at parse time and a fade exported as a solid block with a hard edge (client covers, 2026-10-07) |
| Speaker notes — `<aside class="notes">` / `.speaker-notes` / `data-speaker-notes="…"`, or a `<!-- notes: … -->` comment | **Notes page** (`ppt/notesSlides`), one paragraph per `<p>`/`<li>` or blank-line block. Ordinary HTML comments are authoring scaffolding and are never exported |

## Background images under content

`extract_ir.py` makes a background-image native when it can: one `linear-gradient` with
a `deg` or `to top|right|bottom|left` direction (or none) and colour stops with `%`
positions or none at all (spread the CSS way) becomes a gradient fill on the box, and the
box's text stays editable on top. Tailwind's `bg-gradient-to-r from-… to-…` computes to
that form.

Every other background-image — a grid-line pattern sized with `background-size`, a
layered gradient border (`linear-gradient(white,white) padding-box, … border-box`), a
radial wash, a photo — is a picture. On an element that **holds content** (text, a pill,
a card), only the background is the picture: the element is shot with its content
hidden, and the walk descends, so the text and shapes on it export as editable shapes in
front of that picture. The run prints `note: <tag> class="…" — its background-image is
exported as a picture BEHIND its content` for each. An element with no content is one
picture, as before.

Until 1.6.5 the whole element was screenshotted with its content baked in (a warning,
nothing more): a client deck's gradient pill badges inside a grid-line-pattern lane
(`07-parallel-lanes.html`), and on 2026-10-23 an exec briefing's gantt track (bars and
labels inside a gridline background) and accelerator cards (heading inside a layered
gradient border), which the designers then split into sibling layers by hand. That split
is no longer needed for export; a sibling overlay (`position:absolute; inset:0;
pointer-events:none`) is still fine, and the contrast checks read text over one correctly
(`check_contrast` resolves the background from the paint stack under the text, not only
from its ancestors, so a label over a sibling gradient layer is pixel-sampled by
`check_gradient` instead of failing as white-on-white).

Inline text: runs are joined with a space only where the HTML has whitespace (or a visible
gap) between them, so `mig<span class="accent">V</span>isor` stays one word; `<sup>` /
`<sub>` (`vertical-align: super|sub`) are baseline-offset runs (`a:rPr baseline` ±30/25 %,
at the parent's size — PowerPoint shrinks offset runs itself) on the same line, and a
word starts a new line only when its glyph box leaves the current line's band, so a raised
or larger inline run no longer becomes a paragraph of its own. Regression:
`run_evals.py export` (fixtures in `tests/fixtures/inline-runs.html`, `bg-layers.html`).

## Speaker notes convention

Notes are explicit opt-in, so `<!-- Footer chrome -->`-style scaffolding never reaches the
presenter view. Put them anywhere in the slide file:

```html
<aside class="notes" style="display:none">
  <p>Open with the cost of context loss — 30 s.</p>
  <p>Hand over to Boris for the demo.</p>
</aside>
<!-- notes: Short form also works. Blank lines split paragraphs. -->
```

Keep the aside `display:none` (the extractor skips invisible elements, and PDF export
never shows it). `html2pptx.py` prints `+ N note paragraph(s)` per slide that has them.

**Radial gradients in PowerPoint**: a radial becomes a `path="circle"` gradient whose
centre is the SVG focal point and whose outer stop reaches the bounding box's farthest
corner; svg2shapes rescales the stops so the colour at radius `r` matches. The
svg2shapes `--verify` render models exactly that geometry; Quick Look flattens shape
gradients, so judge radials in PowerPoint.

## Limitations (tell the user these up front)

1. **Machines without the pack's font family substitute fonts** — the pptx names per-weight
   fonts but cannot embed them (python-pptx limitation; macOS PowerPoint ignores embeds
   anyway). Whether the family is installed is a property of the viewer's machine, not
   something this pipeline can guarantee — say so rather than assuming. Because line breaks
   are explicit and wrapping is off, substitution shifts glyph widths but never reflows
   lines into neighboring elements.
2. Charts are vector pictures unless `--native-charts` is passed. A chart is recognised by its library (ECharts); a chart hand-drawn in plain SVG looks like a diagram and converts to shapes unless it carries `data-pptx="picture"`.
3. **Quick Look is NOT a reference renderer**: it ignores `wrap="none"` (spurious text
   wraps), substitutes fonts, flattens shape gradients, and **silently drops custGeom
   freeforms inside groups** (verified: the same freeform renders ungrouped). Use it only
   for pictures/solid shapes/background sanity; judge everything else in PowerPoint.

## Pipeline position & gate

Same gate as pdf-export: **only after §9 is review-clean** (zero open annotations +
explicit user acceptance). Run it alongside pdf-export when the user wants both. The
orchestrator records the extra artifact in `deck-metadata.json` (`"pptx": "<file>"`).

## Verification checklist (after every export)

1. **MAE loop** (the primary check — measure, don't eyeball):
   ```bash
   python3 "{PLUGIN}/skills/pptx-export/scripts/ir_preview.py" --deck-dir "<deck>"
   ```
   (add `--ir-dir <path>` when the export used one.)
   Renders each slide's IR back to a PNG (mirroring exactly what the builder writes —
   text insets/anchor and per-shape gradient slices included) and
   pixel-diffs it against the real slide render. **Gate: content-MAE < 60 per slide**
   (MAE over ink-carrying pixels, both images lightly blurred so 1px stroke offsets
   don't drown real defects — the whole-canvas MAE is reported too but is so diluted a
   full font-fallback preview once passed it). Heatmaps in `.pptx-ir/preview/` show
   WHERE any drift is. Caveat: it approximates PowerPoint's text engine with the
   browser's — property fidelity and geometry, not PPT-specific rendering.
2. **Slide count**: `python3 -c "from pptx import Presentation; print(len(Presentation('<file>').slides))"`
   equals `slide_count` in deck-metadata.json.
3. **Geometry cross-check**: for one content slide, compare each text shape's
   `left/top/width/height ÷ 6350` against the IR node rects — deltas must be sub-pixel.
   The builder writes the rect exactly (up to 1.4.2 it padded textboxes by 1/2 px left/top
   and 4/6 px in size — wrap-on-era slack that shifted centred/right-aligned lines; removed
   in 1.4.3). Padding lives in the text frame insets (`lIns/tIns/rIns/bIns`), not in the
   shape geometry.
4. **Thumbnail** (`qlmanage -t`): pictures/gradients sanity ONLY — Quick Look ignores
   `wrap="none"` and substitutes fonts, so its text layout is wrong by design.
5. **Human open**: ask the user to open the file in PowerPoint and spot-check 2–3 dense
   slides + one SVG (zoom in: vector-crisp; right-click offers Convert to Shape).
   Scripted PowerPoint automation (AppleScript / the PowerPoint MCP `export_pdf`) is
   **unreliable** — it has reported success without writing, then hung on a
   modal dialog. Don't burn a round on it; the user opening the file is the final check.

## Scripts

| Script | Role |
|---|---|
| `scripts/html2pptx.py` | Deck CLI — drives extract + build; `--raster-fallback`, `--native-charts` |
| `scripts/extract_ir.py` | Stage 1: DOM → IR JSON + raster/SVG assets (importable + single-file CLI) |
| `scripts/build_pptx.py` | Stage 2: IR JSON → .pptx incl. svgBlip / gradFill / native charts |
| `scripts/ir_preview.py` | Verify loop: IR → PNG → pixel-diff vs slide render (content-MAE + heatmap) |
| `scripts/svg2shapes.py` | SVG → native-shape model; `--verify` re-renders the model and content-MAEs it vs the source SVG; `--dump` prints the model JSON |
| `scripts/gradients.py` | Shared gradient geometry: per-shape slices of a CSS gradient sized across several elements, and of SVG `userSpaceOnUse` ramps |
