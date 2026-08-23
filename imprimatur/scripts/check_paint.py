#!/usr/bin/env python3
"""
Render-level "does this paint reference actually resolve" checker — design-system
agnostic.

validate.py checks tokens/brand rules, check_contrast.py checks WCAG ratios,
check_overflow.py checks canvas bounds and occlusion. None of them ask the most
basic visual question about a bespoke SVG: does an element's stroke/fill paint
reference actually resolve to something visible?

This gap shipped a real bug: a bespoke SVG line used a `url(#gradient)` stroke
with the SVG default `gradientUnits="objectBoundingBox"`. The path was a
perfectly horizontal line, so its geometric bounding box had zero HEIGHT. An
objectBoundingBox gradient scales its coordinate system by the element's own
bbox — with a zero-height bbox that transform is non-invertible, so Chromium
silently drops the paint. No console error, no warning, nothing in validate.py
or check_contrast.py catches it (the element isn't a text node, so contrast
doesn't apply; the geometry is on-canvas, so overflow doesn't apply). The line
was simply invisible, and it survived two rounds of manual screenshot review
before a live DOM inspection (computed style + getBBox()) found the mechanism.

An earlier version of this script tried to catch this by screenshotting each
shape's bounding box and checking for a single flat color. That approach is
unreliable for connective diagrams: a line's bounding box often overlaps
neighboring visible strokes (e.g. converging lines near a hub node), so the
crop reads as "has color variation" even when the target element itself is
painting nothing. This version instead inspects the DOM/geometry directly —
deterministic, and immune to neighboring-element contamination:

  1. For every shape element (path/rect/circle/ellipse/polygon/polyline/line)
     with a stroke or fill that references a paint server (`url(#id)`):
     - FAIL if the referenced id doesn't exist in the document (broken ref).
     - FAIL if the paint server is a linearGradient/radialGradient using the
       default (or explicit) `objectBoundingBox` units AND the element's own
       geometric bounding box (getBBox()) has zero width or zero height —
       the exact degenerate-transform case above. A perfectly horizontal or
       vertical shape is the classic trigger; any shape whose bbox collapses
       to a line is at risk.

Usage:
    python3 scripts/check_paint.py            # check every template in templates/
    python3 scripts/check_paint.py FILE...    # check specific slide files

Exit code 0 = every paint-server reference resolves and is geometrically safe;
1 = at least one broken reference or degenerate objectBoundingBox gradient.

Escape hatch: mark the shape (or an ancestor) `data-flat-ok="ok"` to skip it —
for a deliberate case where the pattern is known-safe despite the geometry
(e.g. a radialGradient, which doesn't degenerate the same way).
"""

import glob
import os
import sys

from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _targets  # noqa: E402
from ds_config import load  # noqa: E402

SHAPE_TAGS = {"path", "rect", "circle", "ellipse", "polygon", "polyline", "line"}

CHECK_JS = """
() => {
  const slide = document.getElementById('slide');
  if (!slide) return { error: 'no #slide element' };
  const shapeTags = new Set(['path','rect','circle','ellipse','polygon','polyline','line']);
  const urlRe = /url\\(["']?#([^"')]+)["']?\\)/;
  const out = [];

  slide.querySelectorAll('*').forEach((el) => {
    const tag = el.tagName.toLowerCase();
    if (!shapeTags.has(tag)) return;
    if (el.closest('[data-flat-ok="ok"]')) return;
    const cs = getComputedStyle(el);
    if (cs.display === 'none' || cs.visibility === 'hidden' || parseFloat(cs.opacity) === 0) return;

    for (const prop of ['stroke', 'fill']) {
      const raw = el.getAttribute(prop) || cs[prop];
      if (!raw) continue;
      const m = urlRe.exec(raw);
      if (!m) continue;
      const id = m[1];
      const ref = document.getElementById(id);
      const label = (el.getAttribute('class') || tag).slice(0, 60);
      if (!ref) {
        out.push({ tag, label, prop, id, issue: 'broken-ref' });
        continue;
      }
      const refTag = ref.tagName.toLowerCase();
      if (refTag === 'lineargradient' || refTag === 'radialgradient') {
        const units = ref.getAttribute('gradientUnits') || 'objectBoundingBox';
        if (units === 'objectBoundingBox' && typeof el.getBBox === 'function') {
          let bbox;
          try { bbox = el.getBBox(); } catch (e) { bbox = null; }
          if (bbox && (bbox.width === 0 || bbox.height === 0)) {
            out.push({
              tag, label, prop, id, issue: 'degenerate-bbox-gradient',
              bbox: { w: bbox.width, h: bbox.height },
            });
          }
        }
      }
    }
  });
  return { violations: out };
}
"""


def check_files(paths, ds):
    failures = 0
    cw, ch = ds.canvas
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": cw, "height": ch})
        for path in paths:
            name = os.path.basename(path)
            page.goto('file://' + os.path.abspath(path), wait_until='networkidle')
            page.evaluate("document.fonts.ready || Promise.resolve()")
            page.wait_for_timeout(400)  # let the Tailwind CDN inject styles
            res = page.evaluate(CHECK_JS)
            if 'error' in res:
                print(f'{name}\n  FAIL  {res["error"]}')
                failures += 1
                continue

            viol = res['violations']
            if viol:
                print(name)
                for v in viol[:10]:
                    if v['issue'] == 'broken-ref':
                        print(f'  FAIL  <{v["tag"]}> {v["label"]!r} {v["prop"]}=url(#{v["id"]}) '
                              f'— no element with id="{v["id"]}" exists')
                    else:
                        bb = v['bbox']
                        print(f'  FAIL  <{v["tag"]}> {v["label"]!r} {v["prop"]}=url(#{v["id"]}) '
                              f'uses a default/objectBoundingBox gradient on a shape whose '
                              f'own bbox is {bb["w"]}x{bb["h"]} — a zero dimension makes the '
                              f'gradient transform degenerate and Chromium drops the paint '
                              f'silently. Fix: add gradientUnits="userSpaceOnUse" with explicit '
                              f'x1/y1/x2/y2 coordinates on #{v["id"]}.')
                if len(viol) > 10:
                    print(f'  … and {len(viol) - 10} more')
                failures += len(viol)
        browser.close()
    return failures


def main():
    ds = load()
    _, targets = _targets.parse(__doc__.strip().split('\n')[0], ds.templates_dir)
    n = len(targets)

    failures = check_files(targets, ds)
    if failures:
        print(f'\n{failures} silent-paint violation(s) across {n} file(s).')
        sys.exit(1)
    print(f'All {n} file(s): every url(#...) paint reference resolves and is geometrically safe.')


if __name__ == '__main__':
    main()
