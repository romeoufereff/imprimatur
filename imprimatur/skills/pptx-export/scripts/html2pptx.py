#!/usr/bin/env python3
"""
pptx-export — deck CLI: HTML slides → editable .pptx.

Two modes:

  IR mode (default) — extract_ir.py walks each slide's DOM into JSON IR (text stays
  editable text, cards stay shapes; SVGs/charts/gradient areas become pictures), then
  build_pptx.py renders the IR. The per-slide IR JSON is kept next to the output for
  inspection (--ir-dir).

  --raster-fallback — every slide is one full-slide screenshot placed as a picture.
  Pixel-perfect, zero editability. Use when IR fidelity isn't good enough for a slide
  and there's no time to fix it.

Usage:
    python3 html2pptx.py --deck-dir "/path/to/deck" --output "/path/to/Deck.pptx" \
        [--glob "[0-9]*.html"] [--ir-dir /tmp/deck-ir] [--raster-fallback]
"""

import argparse
import glob as globmod
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from extract_ir import extract  # noqa: E402
from build_pptx import build, SLIDE_W, SLIDE_H  # noqa: E402

from playwright.sync_api import sync_playwright  # noqa: E402

SKIP = {'index.html', 'slide-review.html'}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--deck-dir', required=True)
    ap.add_argument('--output', required=True)
    ap.add_argument('--glob', default='[0-9]*.html')
    ap.add_argument('--ir-dir', default=None, help='where to keep IR JSON + assets (default: <deck>/.pptx-ir)')
    ap.add_argument('--raster-fallback', action='store_true')
    ap.add_argument('--native-charts', action='store_true',
                    help='opt-in: rebuild ECharts as real data-editable PPTX charts (default: vector svgBlip)')
    ap.add_argument('--svg-blip', action='store_true',
                    help='embed SVGs as vector pictures instead of native shape groups')
    args = ap.parse_args()

    deck = os.path.abspath(args.deck_dir)
    slides = sorted(f for f in globmod.glob(os.path.join(deck, args.glob))
                    if os.path.basename(f) not in SKIP)
    if not slides:
        sys.exit(f"no slides matching {args.glob} in {deck}")

    ir_dir = os.path.abspath(args.ir_dir or os.path.join(deck, '.pptx-ir'))
    assets = os.path.join(ir_dir, 'assets')
    os.makedirs(assets, exist_ok=True)

    ir_paths = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={'width': 1920, 'height': 1080})
        for path in slides:
            name = os.path.splitext(os.path.basename(path))[0]
            if args.raster_fallback:
                page.goto('file://' + path, wait_until='networkidle')
                page.wait_for_timeout(600)
                png = os.path.join(assets, f"{name}-full.png")
                page.locator('#slide').screenshot(path=png)
                ir = {'source': path, 'slide': {'bg': '#FFFFFF', 'bgImage': True,
                                                'bgAsset': os.path.abspath(png)}, 'nodes': []}
            else:
                ir = extract(page, path, assets, name, native_charts=args.native_charts)
            out = os.path.join(ir_dir, f"{name}.json")
            import json
            with open(out, 'w', encoding='utf-8') as f:
                json.dump(ir, f, indent=2)
            ir_paths.append(out)
            kinds = {}
            for n in ir['nodes']:
                kinds[n['kind']] = kinds.get(n['kind'], 0) + 1
            print(f"extracted {name}: {kinds or 'raster-fallback'}")
        browser.close()

    n = build(ir_paths, args.output, svg_mode='blip' if args.svg_blip else 'shapes')
    print(f"\n{n} slide(s) -> {args.output}")
    print(f"IR kept at {ir_dir} (inspect the JSON, not the pptx)")


if __name__ == '__main__':
    main()
