#!/usr/bin/env python3
"""
WCAG AA contrast checker (render-level) — design-system agnostic.

Loads each slide in headless Chromium at the active design system's native canvas
size, walks every
element that carries direct text, resolves its effective text color and background
(nearest opaque ancestor background, composited over white), and computes the WCAG
contrast ratio. This automates brand-audit Check 1 — previously the only mechanical
check without a script.

Thresholds (WCAG AA):
  - normal text:  >= 4.5:1
  - large text:   >= 3.0:1   (>= 24px, or >= 18.66px at weight >= 700)

Skipped (reported as "verify manually", never FAIL):
  - text over background-image / gradient backgrounds (ratio is position-dependent)
  - text with NO computed background anywhere up the chain whose white-assumption fails
    (the background is being painted by a pseudo-element or absolute sibling layer —
    e.g. the strategy-ladder gradient pills — which computed styles cannot see)
  - transparent / background-clip:text elements (gradient-text — no computed color)
  - SVG text (fill-based; judged by the design system's own SVG rules instead)

Sanctioned decorative text — ghost numerals, oversized quote marks — is exempted via a
`data-decor-text="ok"` attribute on the element (or a wrapper), mirroring the
`data-decor-bleed="ok"` convention in check_overflow.py. Content text is never exempt.

Usage:
    python3 scripts/check_contrast.py FILE...
    python3 scripts/check_contrast.py            # check every template in templates/

Exit code 0 = no failures; 1 = at least one text/background pair below its threshold.
"""

import glob
import os
import sys

from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _targets  # noqa: E402
from ds_config import load  # noqa: E402

COLLECT_JS = """
() => {
  const slide = document.getElementById('slide');
  if (!slide) return { error: 'no #slide element' };
  const parse = (c) => {
    const m = (c || '').match(/rgba?\\(([\\d.]+),\\s*([\\d.]+),\\s*([\\d.]+)(?:,\\s*([\\d.]+))?\\)/);
    return m ? [+m[1], +m[2], +m[3], m[4] === undefined ? 1 : +m[4]] : null;
  };
  const out = [];
  for (const el of slide.querySelectorAll('*')) {
    if (el.closest('svg')) continue;
    const direct = Array.from(el.childNodes)
      .some(n => n.nodeType === 3 && n.textContent.trim().length > 0);
    if (!direct) continue;
    const cs = getComputedStyle(el);
    if (cs.display === 'none' || cs.visibility === 'hidden') continue;
    const r = el.getBoundingClientRect();
    if (!r.width || !r.height) continue;
    const col = parse(cs.color);
    if (!col || col[3] === 0) continue;                       // transparent text
    if ((cs.webkitBackgroundClip || cs.backgroundClip) === 'text') continue;  // gradient-text
    if (el.closest('[data-decor-text="ok"]')) continue;       // sanctioned decorative glyphs
    // Walk up collecting the background stack. Translucent layers (bg-opacity-*)
    // don't terminate the walk — what's UNDER them decides the final color. A
    // gradient/image anywhere in the stack (element or its ::before/::after — e.g.
    // the strategy-ladder pills) makes the ratio position-dependent → manual check.
    let layers = [], bg = null, bgImage = false, node = el;
    while (node && node.nodeType === 1) {
      const ncs = node === el ? cs : getComputedStyle(node);
      if (ncs.backgroundImage && ncs.backgroundImage !== 'none') { bgImage = true; break; }
      const pb = getComputedStyle(node, '::before').backgroundImage;
      const pa = getComputedStyle(node, '::after').backgroundImage;
      if ((pb && pb !== 'none') || (pa && pa !== 'none')) { bgImage = true; break; }
      const b = parse(ncs.backgroundColor);
      if (b && b[3] >= 1) { bg = b; break; }
      if (b && b[3] > 0) layers.push(b);
      if (node === slide) break;
      node = node.parentElement;
    }
    out.push({
      tag: el.tagName.toLowerCase(),
      cls: (el.getAttribute('class') || '').slice(0, 70),
      text: (el.textContent || '').trim().slice(0, 50),
      color: col, bg, layers, bgImage,
      fontSize: parseFloat(cs.fontSize),
      fontWeight: parseInt(cs.fontWeight, 10) || 400,
    });
  }
  return { items: out };
}
"""


def _composite(rgba, base=(255.0, 255.0, 255.0)):
    r, g, b, a = rgba
    return tuple(c * a + bc * (1 - a) for c, bc in zip((r, g, b), base))


def _luminance(rgb):
    def chan(c):
        c /= 255.0
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (chan(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(fg, bg):
    l1, l2 = sorted((_luminance(fg), _luminance(bg)), reverse=True)
    return (l1 + 0.05) / (l2 + 0.05)


def check_files(paths, ds):
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
            res = page.evaluate(COLLECT_JS)
            if 'error' in res:
                print(f'{name}\n  FAIL  {res["error"]}')
                failures += 1
                continue
            fails, manual = [], 0
            for it in res['items']:
                if it['bgImage']:
                    manual += 1
                    continue
                base = _composite(tuple(it['bg'])) if it['bg'] else (255.0, 255.0, 255.0)
                # apply translucent layers bottom-up (walk collected them top-down)
                for layer in reversed(it.get('layers') or []):
                    base = _composite(tuple(layer), base)
                fg = _composite(tuple(it['color']), base)
                ratio = contrast_ratio(fg, base)
                large = it['fontSize'] >= 24 or (it['fontSize'] >= 18.66 and it['fontWeight'] >= 700)
                need = 3.0 if large else 4.5
                if ratio < need - 0.005:
                    if it['bg'] is None:
                        # No computed background found up the chain and the white
                        # assumption fails — the bg is likely painted by a pseudo-element
                        # or absolute layer the walker can't see. Human check, not FAIL.
                        manual += 1
                        continue
                    fails.append((it, ratio, need))
            if fails or manual:
                print(name)
                for it, ratio, need in fails[:10]:
                    label = it['text'] or it['cls'] or it['tag']
                    print(f'  FAIL  <{it["tag"]}> {ratio:.2f}:1 < {need}:1 '
                          f'({it["fontSize"]:.0f}px w{it["fontWeight"]}) — {label!r}')
                if len(fails) > 10:
                    print(f'  … and {len(fails) - 10} more')
                if manual:
                    print(f'  note  {manual} element(s) over gradient/image backgrounds — verify manually')
            failures += len(fails)
        browser.close()
    return failures


def main():
    ds = load()
    _, targets = _targets.parse(__doc__.strip().split('\n')[0], ds.templates_dir)
    failures = check_files(targets, ds)
    n = len(targets)
    if failures:
        print(f'\n{failures} contrast failure(s) across {n} file(s).')
        sys.exit(1)
    print(f'All {n} file(s) pass WCAG AA contrast.')


if __name__ == '__main__':
    main()
