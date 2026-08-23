---
name: pdf-export
description: |
  Converts a directory of HTML slide files into a merged PDF using Playwright element screenshots. Use this skill whenever the user wants to export, render, or convert HTML slides (especially Tailwind-based deck slides) to PDF. Handles custom @font-face paths, Tailwind CDN, and gradient text correctly — invoke it any time the user mentions "export to PDF", "render slides as PDF", "convert HTML deck to PDF", or similar. The key insight is that it uses element screenshots (not page.pdf) to bypass Chromium's print-media relayout, which is what breaks gradient text, custom fonts, and text wrapping in standard approaches.
compatibility: "Bash, Read, Write; python: playwright, Pillow, pypdf (or PyPDF2); playwright install chromium"
license: MIT for the pipeline logic; the design-system pack it drives carries its own terms — see LICENSE.md
metadata:
  author: Roman Iuferev
---

# PDF Export Skill

Converts HTML slide files → individual PDFs → merged single PDF.

## When to use

- User has a directory of HTML slide files and wants a PDF deck
- Slides use Tailwind CSS (CDN or local), custom @font-face, or gradient text
- Standard Playwright `page.pdf()` produced clipped text or gradient bleed artifacts

## Quick start

```bash
# Convert a deck directory to a single merged PDF
python scripts/batch_convert.py \
  --deck-dir "/path/to/deck/" \
  --output "/path/to/output.pdf" \
  --slide-selector "#slide" \
  --glob "[0-9]*.html"
```

This finds the matching `.html` files in `--deck-dir` (sorted), renders each to a temporary
per-slide PDF, then merges them and cleans up the temps.

**Glob discipline:** orchestrator decks name slides `NN-slug.html`, so pass
`--glob "[0-9]*.html"`. The default `*.html` would also sweep up `index.html` (the deck
viewer) and `slide-review.html` (the review harness) as extra PDF pages. The script
skips those two filenames defensively either way, but be explicit.

**Render at the native 1920×1080 viewport only.** The slide's own scaler fits the canvas
via `transform: scale()`, and the element screenshot captures the fixed 1920×1080 box —
a different viewport buys you nothing and historically (with the old resize-based scaler)
caused real text re-wrapping that made the PDF diverge from the HTML.

## Scripts

| Script | Purpose |
|--------|---------|
| `scripts/batch_convert.py` | Main entry point — batch render + merge |
| `scripts/pdf_renderer.py` | Single-file renderer (Playwright element screenshot) |
| `scripts/server.py` | Local HTTP server (fixes @font-face absolute paths + CDN) |

## How it works (why it doesn't break)

Three root-cause fixes are baked into this pipeline:

1. **Fonts load correctly** — HTTP server serves from filesystem root (`/`), so
   absolute-path `@font-face` URLs like `/Users/name/fonts/Font.ttf` resolve as
   `http://127.0.0.1:PORT/Users/name/fonts/Font.ttf`. Without this, Playwright
   404s on fonts and falls back to system fonts with different metrics, causing
   text to overflow and get clipped.

2. **Screen media before load** — `page.emulate_media("screen")` is called before
   `page.goto()`. Tailwind generates utility classes based on the active media type
   at render time, so calling it after the fact doesn't fix layout.

3. **Element screenshot, not page.pdf()** — `page.pdf()` internally switches
   Chromium to print media regardless of `emulate_media()` settings. This triggers
   a re-layout that breaks text wrapping on long gradient-text headings. Instead,
   we screenshot the slide DOM element directly (in screen mode), then convert
   the PNG to a PDF page via Pillow.

## Slide selector

The selector identifies the single slide container element. Common values:

| HTML pattern | Selector |
|---|---|
| `<div id="slide">` | `#slide` (default) |
| `<div class="slide">` | `.slide` |
| `<section>` | `section` |

If the selector isn't found, the renderer falls back to a full-viewport screenshot.

## Viewport & DPI

Default viewport is `1920×1080` (16:9). `device_scale_factor=2` produces a
3840×2160 screenshot saved at 192 DPI → 20in × 11.25in in the PDF (correct
physical size for a 16:9 presentation at 96 DPI screen resolution).

Override for non-standard slides:

```bash
python scripts/batch_convert.py \
  --deck-dir "/path/to/deck/" \
  --output "out.pdf" \
  --viewport-width 2560 \
  --viewport-height 1440 \
  --scale 1
```

## Troubleshooting

**Blue rectangle artifact at end of gradient text**
→ Font failed to load, system font is wider, text overflows and the gradient
  background bleeds. Check that `--deck-dir` is accessible from filesystem root.

**Blank / white slides**
→ Check the slide selector. Run with `--debug` to save individual slide PNGs
  alongside the PDFs for inspection.

**Wrong page count (e.g., 22 pages for 11 slides)**
→ You're using `page.pdf()` somewhere — this skill uses element screenshots only.

**Tailwind classes not applying**
→ The Tailwind CDN must respond before screenshot. The built-in wait checks for
  `--tw-` CSS variables in injected `<style>` tags (10s timeout).

**"The PDF looks smaller / different than the HTML" (in Preview.app or any viewer)**
→ Almost certainly the viewer, not the render. macOS Preview auto-fits every page to the
  window, so declared page size / DPI changes are **invisible** — do not burn time tuning
  DPI. Settle the dispute with measurements: load the HTML at two different viewports in
  Playwright and compare an element's width ÷ slide width ratio (must be identical), and
  compare the same ratio in the rendered PNG. If ratios match, parity is proven; if they
  don't, the slide's scaler is re-laying-out the DOM — see next item.

**Text wraps differently in the PDF than in the browser**
→ Symptom of the retired resize-based scaler (`s.style.width = computed px`), which
  re-layouts the slide at every viewport. The canonical scaler keeps `#slide` at a fixed
  1920×1080 and applies `transform: scale(r)`. `validate.py` fails slides carrying the
  legacy pattern.

## Post-export checklist

1. Page count equals the deck's slide count (`deck-metadata.json` → `slide_count`).
2. Page size sanity: `points = pixels / DPI × 72` (3840×2160 @ 192 DPI → 1440×810 pt).
3. Visual spot-check first + last page: `qlmanage -t -s 1400 -o <dir> <pdf>` and read the
   generated PNG. Quick Look is the reliable thumbnailer for this — browser preview
   screenshot tooling has produced wrong-scale captures.
