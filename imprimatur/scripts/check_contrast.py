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
  - text over background-image / gradient backgrounds (ratio is position-dependent;
    check_gradient.py pixel-samples them). The background is what PAINTS under the
    text — ancestors and any sibling layer beneath it (BG_STACK_JS) — so text over an
    absolutely positioned gradient layer is deferred, not read as white-on-white
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

# What paints under an element's text, shared with check_gradient.py. The background
# stack is read from the PAINT stack at the text's first word (document.elementsFromPoint,
# pointer-events forced on for the probe), not only from the element's ancestors: a
# background painted by an absolutely positioned SIBLING layer (`<div class="fill
# absolute inset-0 bg-gradient"></div><span class="relative">Label</span>`) is not an
# ancestor, so the ancestor walk skipped it, met the white page and read white text as
# 1.00:1 — a FAIL designers silenced by giving the parent a solid colour (2026-10-23).
# Falls back to the ancestor walk when the element is not hit at that point. Returns
# {bg, layers, bgImage} with the meaning COLLECT_JS has always used.
BG_STACK_JS = """
  const bgStackOf = (el, cs, slide, parse) => {
    const hasImage = (n, ncs) => {
      if (ncs.backgroundImage && ncs.backgroundImage !== 'none') return true;
      const pb = getComputedStyle(n, '::before').backgroundImage;
      const pa = getComputedStyle(n, '::after').backgroundImage;
      return (pb && pb !== 'none') || (pa && pa !== 'none');
    };
    const read = (nodes) => {
      const layers = [];
      for (const n of nodes) {
        const ncs = n === el ? cs : getComputedStyle(n);
        if (hasImage(n, ncs)) return { bg: null, layers, bgImage: true };
        const b = parse(ncs.backgroundColor);
        if (b && b[3] >= 1) return { bg: b, layers, bgImage: false };
        if (b && b[3] > 0) layers.push(b);
        if (n === slide) break;
      }
      return { bg: null, layers, bgImage: false };
    };
    const ancestors = [];
    for (let n = el; n && n.nodeType === 1; n = n.parentElement) { ancestors.push(n); if (n === slide) break; }
    let stack = null;
    const tn = Array.from(el.childNodes).find(n => n.nodeType === 3 && n.textContent.trim());
    const w = tn && /\\S+/.exec(tn.textContent);
    if (w) {
      const rg = document.createRange();
      rg.setStart(tn, w.index); rg.setEnd(tn, w.index + w[0].length);
      const rr = rg.getClientRects()[0];
      if (rr && rr.width && rr.height) {
        const hits = document.elementsFromPoint(rr.left + rr.width / 2, rr.top + rr.height / 2);
        const i = hits.indexOf(el), j = hits.indexOf(slide);
        if (i >= 0 && j >= i) {
          // painted below the text: ancestors, plus any other layer under that point —
          // never the element's own children, never an invisible (opacity 0) layer
          stack = hits.slice(i, j + 1).filter(n => n === el || n.contains(el) ||
            (!el.contains(n) && parseFloat(getComputedStyle(n).opacity) > 0.05));
        }
      }
    }
    return read(stack || ancestors);
  };
"""

# elementsFromPoint skips pointer-events:none, which is how decorative layers are usually
# written; the probe turns it back on for the duration of a collection pass.
PROBE_ON_JS = """
  const probeStyle = document.createElement('style');
  probeStyle.textContent = '* { pointer-events: auto !important; }';
  document.head.appendChild(probeStyle);
"""

COLLECT_JS = """
() => {
  const slide = document.getElementById('slide');
  if (!slide) return { error: 'no #slide element' };
  const parse = (c) => {
    const m = (c || '').match(/rgba?\\(([\\d.]+),\\s*([\\d.]+),\\s*([\\d.]+)(?:,\\s*([\\d.]+))?\\)/);
    return m ? [+m[1], +m[2], +m[3], m[4] === undefined ? 1 : +m[4]] : null;
  };
""" + BG_STACK_JS + PROBE_ON_JS + """
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
    if (el.closest('[class*="sr-only"]:not(.not-sr-only), [class*="visually-hidden"]')) continue;   // screen-reader-only text
    // The background stack under the text (bgStackOf: the paint stack, so a sibling
    // layer counts). Translucent layers (bg-opacity-*) don't terminate it — what's
    // UNDER them decides the final color. A gradient/image anywhere in the stack
    // (element or its ::before/::after — e.g. the strategy-ladder pills) makes the
    // ratio position-dependent → check_gradient's pixel sample, manual here.
    const { bg, layers, bgImage } = bgStackOf(el, cs, slide, parse);
    out.push({
      tag: el.tagName.toLowerCase(),
      cls: (el.getAttribute('class') || '').slice(0, 70),
      text: (el.textContent || '').trim().slice(0, 50),
      color: col, bg, layers, bgImage,
      fontSize: parseFloat(cs.fontSize),
      fontWeight: parseInt(cs.fontWeight, 10) || 400,
    });
  }
  probeStyle.remove();
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


def analyze_page(page):
    """Run the contrast collector on an ALREADY-LOADED page. Returns (fails, manual):
    `fails` is a list of (item, ratio, need) hard WCAG failures; `manual` is a count of
    elements needing a human look (gradient/image bg, or no resolvable bg at all).
    Returns (None, error_string) when the page has no #slide element.

    Pulled out of check_files() so render_checks.py (WP1) can share one Chromium launch
    across contrast + overflow + paint instead of each script opening its own browser.
    """
    res = page.evaluate(COLLECT_JS)
    if 'error' in res:
        return None, res['error']
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
    return fails, manual


def format_report(name, fails, manual, verbose=True):
    """Render the text check_files() has always printed, from analyze_page()'s output.
    `verbose=False` drops the "verify manually" note line (WP1: that note costs agent
    turns and belongs to brand-audit's judgment rows, not the designer-facing output).
    """
    lines = []
    if fails or manual:
        lines.append(name)
        for it, ratio, need in fails[:10]:
            label = it['text'] or it['cls'] or it['tag']
            lines.append(f'  FAIL  <{it["tag"]}> {ratio:.2f}:1 < {need}:1 '
                         f'({it["fontSize"]:.0f}px w{it["fontWeight"]}) — {label!r}')
        if len(fails) > 10:
            lines.append(f'  … and {len(fails) - 10} more')
        if manual and verbose:
            lines.append(f'  note  {manual} element(s) over gradient/image backgrounds — verify manually')
    return lines


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
            fails, manual = analyze_page(page)
            if fails is None:
                print(f'{name}\n  FAIL  {manual}')
                failures += 1
                continue
            for line in format_report(name, fails, manual, verbose=True):
                print(line)
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
