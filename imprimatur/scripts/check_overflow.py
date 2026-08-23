#!/usr/bin/env python3
"""
Render-level layout checker — design-system agnostic.

Loads each slide in headless Chromium at the active design system's native canvas size
and runs two checks that validate.py (pure grep) structurally cannot:

  1. OVERFLOW — any element whose rect sticks out past the #slide canvas: text that grew
     past its container, cards that spill off-canvas, SVG labels clipped at the edge.
  2. COLLISIONS (rules.banElementCollisions) — content sitting ON TOP of other content:
     text over text, or an opaque panel covering text. A slide can pass every other gate
     while a paragraph is completely hidden behind a card, because nothing has left the
     canvas and every colour and font is legal.

Both are the "measure, don't eyeball" half of QA.

Usage:
    python3 scripts/check_overflow.py            # check every template in templates/
    python3 scripts/check_overflow.py FILE...    # check specific HTML files (e.g. generated slides)

Exit code 0 = clean; 1 = at least one overflow or collision.

A design system may sanction templates that intentionally bleed ONE decorative element
past the canvas edge (clipped by #slide's overflow:hidden) — those files tolerate
decorative overflow but still fail on overflowing TEXT elements. Deliberate overlaps are
sanctioned per-element with data-overlap="ok" (and decorative glyphs already marked
data-decor-text / data-decor-bleed are never collision participants).
"""

import glob
import os
import sys

from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _targets  # noqa: E402
from ds_config import load  # noqa: E402

# The pack's legacy filename allowlist (exemptions.decorBleedAllowlist) names templates
# that deliberately hang a decorative element off the canvas edge.
#
# NOTE: the allowlist is legacy. The PREFERRED mechanism is the `data-decor-bleed="ok"`
# attribute on the bleeding element itself (or a wrapper): it survives copying a template
# into a deck slide under a new filename, which the allowlist does not (a 35-closing
# derivative saved as 03-ask.html false-positived for an entire deck review before this
# was added). Sanctioning only ever exempts NON-TEXT elements — overflowing text still
# fails either way.

# Tolerance in px: sub-pixel rounding and shadow boxes are not defects.
EPS = 2.0

MEASURE_JS = """
() => {
  const slide = document.getElementById('slide');
  if (!slide) return { error: 'no #slide element' };
  const sb = slide.getBoundingClientRect();
  const out = [];
  for (const el of slide.querySelectorAll('*')) {
    const cs = getComputedStyle(el);
    if (cs.display === 'none' || cs.visibility === 'hidden') continue;
    const r = el.getBoundingClientRect();
    if (r.width === 0 && r.height === 0) continue;
    const over = {
      left:   sb.left - r.left,
      right:  r.right - sb.right,
      top:    sb.top - r.top,
      bottom: r.bottom - sb.bottom,
    };
    const max = Math.max(over.left, over.right, over.top, over.bottom);
    if (max > %EPS%) {
      const text = (el.textContent || '').trim().slice(0, 60);
      // "hasText" = the element itself carries text (direct text nodes), not just a
      // container inheriting textContent from descendants. Containers around a
      // sanctioned decorative bleed would otherwise false-positive.
      const directText = Array.from(el.childNodes)
        .some(n => n.nodeType === 3 && n.textContent.trim().length > 0);
      out.push({
        tag: el.tagName.toLowerCase(),
        cls: (el.getAttribute('class') || '').slice(0, 80),
        text,
        hasText: directText && !['style','script','defs'].includes(el.tagName.toLowerCase()),
        // Element (or an ancestor wrapper) explicitly marked as a sanctioned
        // decorative bleed — filename-independent alternative to the pack allowlist.
        sanctioned: el.closest('[data-decor-bleed="ok"]') !== null,
        over: Math.round(max),
      });
    }
  }
  return { violations: out };
}
"""


def check_files(paths, ds):
    decor_bleed_ok = set(ds.get('exemptions.decorBleedAllowlist', []) or [])
    cw, ch = ds.canvas
    failures = 0
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": cw, "height": ch})
        for path in paths:
            name = os.path.basename(path)
            page.goto('file://' + os.path.abspath(path), wait_until='networkidle')
            page.evaluate("document.fonts.ready || Promise.resolve()")
            page.wait_for_timeout(400)  # let the Tailwind CDN inject styles
            res = page.evaluate(MEASURE_JS.replace('%EPS%', str(EPS)))
            if 'error' in res:
                print(f'{name}\n  FAIL  {res["error"]}')
                failures += 1
                continue
            viol = res['violations']
            # Attribute-level sanctioning (preferred): non-text elements marked
            # data-decor-bleed="ok" may bleed; text must stay on-canvas regardless.
            viol = [v for v in viol if v['hasText'] or not v.get('sanctioned')]
            if name in decor_bleed_ok:
                viol = [v for v in viol if v['hasText']]  # legacy filename allowlist
            if viol:
                print(name)
                for v in viol[:8]:
                    label = v['text'] or v['cls'] or v['tag']
                    print(f'  FAIL  <{v["tag"]}> overflows canvas by {v["over"]}px — {label!r}')
                if len(viol) > 8:
                    print(f'  … and {len(viol) - 8} more')
                failures += len(viol)
        browser.close()
    return failures


# ── Collision checking ────────────────────────────────────────────────────
# Canvas-bounds checking answers "does anything stick out?" but not "does anything
# sit on top of anything else?" — and a slide can pass every mechanical gate while
# text is occluded by a panel. That happened for real: raising a template's type to
# the design system's own floors pushed a column 79px into the panel below it,
# hiding an item's body copy. validate.py, check_contrast.py and the canvas check
# all passed the slide; only a human reviewer saw it.
#
# What counts as a collision:
#   • text-over-text     — two elements that each paint their own text, overlapping
#   • panel-over-text    — an element with an opaque background painted AFTER a text
#                          element in document order (so it covers it)
# Ancestor/descendant pairs are never collisions (a heading inside its card, a
# gradient <span> inside its <h1>) — that is ordinary nesting.
#
# Escape hatch: mark either element `data-overlap="ok"` for deliberate composition
# (a badge sitting on a card corner, a number behind a title). Mirrors the
# data-decor-bleed / data-decor-text convention.

COLLIDE_JS = """
(tol) => {
  const slide = document.getElementById('slide');
  if (!slide) return { error: 'no #slide element' };
  const els = [...slide.querySelectorAll('*')];
  const info = [];
  els.forEach((el, i) => {
    const cs = getComputedStyle(el);
    if (cs.display === 'none' || cs.visibility === 'hidden' || parseFloat(cs.opacity) === 0) return;
    if (el.closest('svg')) return;                       // SVG internals have their own layout
    if (el.closest('[data-overlap="ok"]')) return;       // sanctioned composition
    // Decorative glyphs (ghost numerals, oversized quote marks) are DESIGNED to sit
    // behind content — the same category check_contrast.py already exempts. They are
    // composition, not collision.
    if (el.closest('[data-decor-text="ok"]')) return;
    if (el.closest('[data-decor-bleed="ok"]')) return;
    let r = el.getBoundingClientRect();
    if (r.width < 1 || r.height < 1) return;
    const hasText = [...el.childNodes].some(n => n.nodeType === 3 && n.textContent.trim());
    // A block element's rect spans its whole container, not its glyphs — an <h1> in a
    // 1760px column reports a 1760px-wide box even when the words occupy 700px of it.
    // Comparing those boxes reports overlaps that are not visible. For text we measure
    // the glyphs themselves via Range rects and use their union.
    if (hasText) {
      const range = document.createRange();
      range.selectNodeContents(el);
      const rects = [...range.getClientRects()].filter(q => q.width > 0 && q.height > 0);
      if (rects.length) {
        const left = Math.min(...rects.map(q => q.left));
        const right = Math.max(...rects.map(q => q.right));
        const top = Math.min(...rects.map(q => q.top));
        const bottom = Math.max(...rects.map(q => q.bottom));
        r = { left, right, top, bottom, width: right - left, height: bottom - top };
      }
    }
    const bg = cs.backgroundColor || '';
    const m = bg.match(/rgba?\\(([\\d.]+),\\s*([\\d.]+),\\s*([\\d.]+)(?:,\\s*([\\d.]+))?\\)/);
    // "Opaque" = a background solid enough to hide text under it. Translucent washes
    // and decorative gradients are not treated as occluders.
    const opaque = (m && (m[4] === undefined ? 1 : +m[4]) >= 0.85);
    if (!hasText && !opaque) return;
    info.push({ i, el, r, hasText, opaque,
                tag: el.tagName.toLowerCase(),
                cls: (el.getAttribute('class') || '').slice(0, 60),
                txt: (el.innerText || '').trim().slice(0, 44).replace(/\\s+/g, ' ') });
  });
  const out = [];
  for (let a = 0; a < info.length; a++) {
    for (let b = a + 1; b < info.length; b++) {
      const A = info[a], B = info[b];
      if (A.el.contains(B.el) || B.el.contains(A.el)) continue;   // nesting, not collision
      const ox = Math.min(A.r.right, B.r.right) - Math.max(A.r.left, B.r.left);
      const oy = Math.min(A.r.bottom, B.r.bottom) - Math.max(A.r.top, B.r.top);
      if (ox <= tol || oy <= tol) continue;
      // Which pairs are defects: text vs text always; background vs text only when the
      // background paints later (document order approximates paint order without z-index).
      let kind = null;
      if (A.hasText && B.hasText) kind = 'text over text';
      else if (B.opaque && A.hasText) kind = 'panel over text';
      else if (A.opaque && B.hasText && A.i > B.i) kind = 'panel over text';
      if (!kind) continue;
      out.push({ kind, ox: Math.round(ox), oy: Math.round(oy),
                 a: { tag: A.tag, cls: A.cls, txt: A.txt },
                 b: { tag: B.tag, cls: B.cls, txt: B.txt } });
    }
  }
  return { collisions: out };
}
"""


def check_collisions(paths, ds):
    tol = float(ds.get('collisionTolerancePx', 4))
    cw, ch = ds.canvas
    failures = 0
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": cw, "height": ch})
        for path in paths:
            name = os.path.basename(path)
            page.goto('file://' + os.path.abspath(path), wait_until='networkidle')
            page.evaluate("document.fonts.ready || Promise.resolve()")
            page.wait_for_timeout(400)
            res = page.evaluate(COLLIDE_JS, tol)
            if 'error' in res:
                print(f'{name}\n  FAIL  {res["error"]}')
                failures += 1
                continue
            cols = res['collisions']
            if cols:
                print(name)
                for c in cols[:6]:
                    la = c['a']['txt'] or c['a']['cls'] or c['a']['tag']
                    lb = c['b']['txt'] or c['b']['cls'] or c['b']['tag']
                    print(f'  FAIL  {c["kind"]} — {c["ox"]}x{c["oy"]}px\n'
                          f'          {la!r}\n'
                          f'          {lb!r}')
                if len(cols) > 6:
                    print(f'  … and {len(cols) - 6} more')
                failures += len(cols)
        browser.close()
    return failures


def main():
    ds = load()
    _, targets = _targets.parse(__doc__.strip().split('\n')[0], ds.templates_dir)
    n = len(targets)
    cw, ch = ds.canvas

    failures = check_files(targets, ds)
    if failures:
        print(f'\n{failures} overflow violation(s) across {n} file(s).')
    else:
        print(f'All {n} file(s) fit the {cw}x{ch} canvas.')

    collisions = 0
    if ds.rule('banElementCollisions'):
        collisions = check_collisions(targets, ds)
        if collisions:
            note = ds.note('banElementCollisions')
            print(f'\n{collisions} collision(s) across {n} file(s).'
                  + (f' {note}' if note else ''))
        else:
            print(f'All {n} file(s) free of element collisions.')

    if failures or collisions:
        sys.exit(1)


if __name__ == '__main__':
    main()
