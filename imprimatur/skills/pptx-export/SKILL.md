---
name: pptx-export
description: |
  Converts a directory of HTML slide files into an EDITABLE PowerPoint (.pptx) via a Playwright→JSON-IR→python-pptx pipeline. Use this skill whenever the user wants the deck as PPTX / PowerPoint / "an editable deck" / "slides the client can modify" — the sibling of pdf-export, which produces the pixel-perfect but non-editable PDF. Text stays editable text at exact positions, cards stay shapes; SVGs, charts, and gradient areas are placed as high-res pictures. Invoke on: "export to pptx", "make it a PowerPoint", "client wants the editable version", or when the orchestrator reaches §10 and the user asked for PPTX in addition to (or instead of) PDF.
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
- `--raster-fallback` — every slide becomes one full-slide screenshot picture:
  pixel-perfect, zero editability. The escape hatch when IR fidelity isn't good enough
  for a particular deck and there's no time to fix it.

## Fidelity contract (v2 — what's editable vs baked)

| HTML element | PPTX result |
|---|---|
| Text (any block whose children are all inline) | **Editable textbox**, exact position; styled runs: size px→pt (×0.75), **per-weight font names** (the pack family plus its weight, e.g. "Source Sans 3 300/400/700" — a bare family name plus a bold flag resolves unpredictably across families), color, uppercase, **letter-spacing** (oxml `spc`), **per-paragraph line-height** (mixed-size cards keep their rhythm). The browser's ACTUAL line breaks are measured word-by-word (Range rects) and written as explicit paragraphs with **wrapping off** — renderer metric differences can never reflow a title into the element below it |
| Card / callout (solid bg or border) | **Editable rounded rectangle** — fill, border, corner radius; shadows off |
| `::before/::after` decorations (bullet dots, bars) | **Shape** (best-effort: solid-background, px-measurable pseudos) |
| Slide background (solid) | Slide background fill |
| Slide background (single linear-gradient — covers, dividers) | **Native gradient fill** (oxml `gradFill`, CSS→DrawingML angle mapped); text/logo stay editable on top |
| Slide background (layered/radial image) | Whole slide as one picture (fallback) |
| `<svg>` (diagrams, logo, icons) | **Native GROUPED SHAPES** (svg2shapes.py): rects/ovals/freeform beziers (`a:custGeom`)/textboxes with gradient fills, arrowhead markers instantiated at path ends, dashes, drop shadows — movable, scalable as one, ungroup to edit any piece. Verified by re-rendering the parsed model and content-MAE-ing it against the source SVG (logo 0.0, cycle diagram 40.9). Unconvertible SVGs (textPath curved labels, masks, >150 elements) fall back to **svgBlip** with a printed reason; `--svg-blip` forces blip mode for everything |
| ECharts with `--native-charts` (opt-in) | **Real data-editable PPTX chart** (bar/line/pie) scraped from `chart.getOption()`, the pack's `viz` series colors; `null` gaps (forecast series) preserved; scrape miss → svgBlip fallback |
| `<canvas>`, `<img>`, gradient-background elements (chips, blobs) | Picture at exact position (isolated screenshot — overlapping neighbors are hidden during capture) |
| Gradient text (`background-clip:text`) | Editable text with a **real per-run brand-gradient fill** (the pack's `svg.brandGradientStops`); the gradient spans each run's own box rather than the whole element — close for accent phrases. Checked BEFORE the raster branch; never a picture |
| Semi-transparent solid fills | Pre-composited over white (approximation) |

## Authoring trap: rasterized parents swallow children

`extract_ir.py`'s DOM walk screenshots any element that needs a background-image (a
pattern, photo, canvas, layered/radial gradient) and **does not descend into its
children** — they get baked into that one raster PNG instead of being extracted as their
own shapes. If a deck-designer-authored slide puts otherwise-convertible content (a text
node, a gradient pill/badge, a card) **inside** a div whose own background-image is a
decorative pattern, that content silently disappears into the picture. It still looks
fine in the browser and in the review harness — the only way to notice is opening the
PPTX and finding a flattened picture where an editable badge should be.

Real incident: a Sklum deck (`07-parallel-lanes.html`) nested gradient "pill" badges
(with their own text) inside a div whose background-image was a grid-line pattern; the
pills silently became part of that raster screenshot even though they were themselves
perfectly convertible. Fixed by moving the grid-line pattern into a separate **sibling**
overlay div instead of being the pills' parent.

**Rule for anyone authoring slide HTML (deck-designer included): a decorative background
that needs `background-image` must always be a sibling overlay
(`position:absolute; inset:0; pointer-events:none;` behind or above the content in
z-order, never a wrapper), never the parent of text, badges, or cards.** `extract_ir.py`
now detects this shape at extraction time — an element with a background-image AND
non-trivial descendant text — and prints `warn: <tag> ... has a background-image AND
descendant text ...` for each occurrence. Treat that warning like the svg2shapes fallback
warnings: read the IR JSON for the flagged node, restructure the HTML, and re-extract.

## Limitations (tell the user these up front)

1. **Machines without the pack's font family substitute fonts** — the pptx names per-weight
   fonts but cannot embed them (python-pptx limitation; macOS PowerPoint ignores embeds
   anyway). Whether the family is installed is a property of the viewer's machine, not
   something this pipeline can guarantee — say so rather than assuming. Because line breaks
   are explicit and wrapping is off, substitution shifts glyph widths but never reflows
   lines into neighboring elements.
2. Charts are vector pictures unless `--native-charts` is passed.
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
   Renders each slide's IR back to a PNG (mirroring exactly what the builder writes) and
   pixel-diffs it against the real slide render. **Gate: content-MAE < 60 per slide**
   (MAE over ink-carrying pixels, both images lightly blurred so 1px stroke offsets
   don't drown real defects — the whole-canvas MAE is reported too but is so diluted a
   full font-fallback preview once passed it). Heatmaps in `.pptx-ir/preview/` show
   WHERE any drift is. Caveat: it approximates PowerPoint's text engine with the
   browser's — property fidelity and geometry, not PPT-specific rendering.
2. **Slide count**: `python3 -c "from pptx import Presentation; print(len(Presentation('<file>').slides))"`
   equals `slide_count` in deck-metadata.json.
3. **Geometry cross-check**: for one content slide, compare each text shape's
   `left/top ÷ 6350` against the IR node rects — deltas must be sub-pixel.
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
