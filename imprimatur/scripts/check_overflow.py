#!/usr/bin/env python3
"""
Render-level layout checker — design-system agnostic.

Loads each slide in headless Chromium at the active design system's native canvas size
and runs three checks that validate.py (pure grep) structurally cannot:

  1. OVERFLOW — any element whose rect sticks out past the #slide canvas: text that grew
     past its container, cards that spill off-canvas, SVG labels clipped at the edge.
  2. COLLISIONS (rules.banElementCollisions) — content sitting ON TOP of other content:
     text over text, or an opaque panel covering text. A slide can pass every other gate
     while a paragraph is completely hidden behind a card, because nothing has left the
     canvas and every colour and font is legal. Text over a logo or labelled mark counts.
  3. SVG SIZING — an <svg> laid out smaller than written (flex-squashed below its height
     attribute or its unshrunk size), or SVG text whose RENDERED size is below the pack's
     typography.minFontSizePx. validate.py reads SVG sizes as written and cannot see either.

All three are the "measure, don't eyeball" half of QA.

Usage:
    python3 scripts/check_overflow.py            # check every template in templates/
    python3 scripts/check_overflow.py FILE...    # check specific HTML files (e.g. generated slides)

Exit code 0 = clean; 1 = at least one overflow, collision or SVG sizing violation.

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
    if (el.closest('[class*="sr-only"]:not(.not-sr-only), [class*="visually-hidden"]')) continue;   // screen-reader-only text is not on the slide
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


def analyze_overflow_page(page, ds, name):
    """Run the overflow measurer on an ALREADY-LOADED page. Returns a violation list
    (already filtered for sanctioned decor-bleed / legacy allowlist), or None on error
    (in which case the second return value is the error string).

    Pulled out of check_files() so render_checks.py (WP1) can share one Chromium launch
    across overflow + collisions + contrast + paint instead of each script opening its
    own browser.
    """
    decor_bleed_ok = set(ds.get('exemptions.decorBleedAllowlist', []) or [])
    res = page.evaluate(MEASURE_JS.replace('%EPS%', str(EPS)))
    if 'error' in res:
        return None, res['error']
    viol = res['violations']
    # Attribute-level sanctioning (preferred): non-text elements marked
    # data-decor-bleed="ok" may bleed; text must stay on-canvas regardless.
    viol = [v for v in viol if v['hasText'] or not v.get('sanctioned')]
    if name in decor_bleed_ok:
        viol = [v for v in viol if v['hasText']]  # legacy filename allowlist
    return viol, None


def format_overflow_report(name, viol):
    lines = []
    if viol:
        lines.append(name)
        for v in viol[:8]:
            label = v['text'] or v['cls'] or v['tag']
            lines.append(f'  FAIL  <{v["tag"]}> overflows canvas by {v["over"]}px — {label!r}')
        if len(viol) > 8:
            lines.append(f'  … and {len(viol) - 8} more')
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
            viol, err = analyze_overflow_page(page, ds, name)
            if viol is None:
                print(f'{name}\n  FAIL  {err}')
                failures += 1
                continue
            for line in format_overflow_report(name, viol):
                print(line)
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
#   • text-over-logo /   — text overlapping a logo (the pack's logo.selector, [data-logo],
#     text-over-mark       [data-client-logo], a co-brand client mark [data-cobrand="client"])
#                          or a labelled svg/img no larger than 240px,
#                          in either paint order. Big diagrams are not marks: templates
#                          lay HTML labels over a background curve on purpose.
# Ancestor/descendant pairs are never collisions (a heading inside its card, a
# gradient <span> inside its <h1>) — that is ordinary nesting.
#
# Escape hatch: mark either element `data-overlap="ok"` for deliberate composition
# (a badge sitting on a card corner, a number behind a title). Mirrors the
# data-decor-bleed / data-decor-text convention.

COLLIDE_JS = """
([tol, logoSel]) => {
  const MARK_PX = 240;   // a labelled svg/img this small is a mark (logo, icon), not a diagram
  const slide = document.getElementById('slide');
  if (!slide) return { error: 'no #slide element' };
  const els = [...slide.querySelectorAll('*')];
  const info = [];
  els.forEach((el, i) => {
    const cs = getComputedStyle(el);
    if (cs.display === 'none' || cs.visibility === 'hidden' || parseFloat(cs.opacity) === 0) return;
    // SVG internals have their own layout — but a MARK (a logo, a labelled icon) is a
    // painted box text must not sit on. Skipping every <svg> whole (until 1.6.1) meant the
    // footer logo was never compared: a caption sat on it and passed (a client deck,
    // slide 03). Large unlabelled-or-labelled diagrams are NOT occluders: templates lay
    // HTML labels over a background curve or staircase on purpose.
    const tg = el.tagName.toLowerCase();
    const rootSvg = tg === 'svg' && !(el.parentElement && el.parentElement.closest('svg'));
    if (el.closest('svg') && !rootSvg) return;
    if (el.closest('[data-overlap="ok"]')) return;       // sanctioned composition
    if (el.closest('[class*="sr-only"]:not(.not-sr-only), [class*="visually-hidden"]')) return;   // screen-reader-only text
    // Decorative glyphs (ghost numerals, oversized quote marks) are DESIGNED to sit
    // behind content — the same category check_contrast.py already exempts. They are
    // composition, not collision.
    if (el.closest('[data-decor-text="ok"]')) return;
    if (el.closest('[data-decor-bleed="ok"]')) return;
    let r = el.getBoundingClientRect();
    if (r.width < 1 || r.height < 1) return;
    if (rootSvg || tg === 'img') {
      const logo = !!(logoSel && el.matches(logoSel)) || el.matches('[data-logo], [data-client-logo], [data-cobrand="client"]');
      const labelled = el.hasAttribute('aria-label') || el.getAttribute('role') === 'img' || !!el.getAttribute('alt');
      const mark = labelled && r.width <= MARK_PX && r.height <= MARK_PX;
      if (!logo && !mark) { if (rootSvg) return; }
      else {
        // A mark is a non-text occluder: text over it is a collision whichever paints first.
        info.push({ i, el, r, hasText: false, opaque: false, graphic: true, logo,
                    tag: tg, cls: (el.getAttribute('class') || '').slice(0, 60),
                    txt: (el.getAttribute('aria-label') || el.getAttribute('alt') || '').slice(0, 44) });
        return;
      }
    }
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
      if (A.graphic || B.graphic) {
        const G = A.graphic ? A : B, T = A.graphic ? B : A;
        if (!T.hasText) continue;                                 // graphic vs panel/graphic
        kind = G.logo ? 'text over logo' : 'text over mark';
        out.push({ kind, ox: Math.round(ox), oy: Math.round(oy),
                   a: { tag: T.tag, cls: T.cls, txt: T.txt },
                   b: { tag: G.tag, cls: G.cls, txt: G.txt || (G.logo ? 'logo' : G.tag) } });
        continue;
      }
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


def analyze_collisions_page(page, tol, logo_selector=""):
    """Run the collision detector on an ALREADY-LOADED page. Returns (collisions, error).
    `logo_selector` (the pack's logo.selector) only names a graphic as a logo in the
    report; every root <svg> takes part in the comparison either way."""
    res = page.evaluate(COLLIDE_JS, [tol, logo_selector or ""])
    if 'error' in res:
        return None, res['error']
    return res['collisions'], None


def format_collisions_report(name, cols):
    lines = []
    if cols:
        lines.append(name)
        for c in cols[:6]:
            la = c['a']['txt'] or c['a']['cls'] or c['a']['tag']
            lb = c['b']['txt'] or c['b']['cls'] or c['b']['tag']
            lines.append(f'  FAIL  {c["kind"]} — {c["ox"]}x{c["oy"]}px\n'
                        f'          {la!r}\n'
                        f'          {lb!r}')
        if len(cols) > 6:
            lines.append(f'  … and {len(cols) - 6} more')
    return lines


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
            cols, err = analyze_collisions_page(page, tol, ds.get('logo.selector', ''))
            if cols is None:
                print(f'{name}\n  FAIL  {err}')
                failures += 1
                continue
            for line in format_collisions_report(name, cols):
                print(line)
            failures += len(cols)
        browser.close()
    return failures


# ── SVG sizing ────────────────────────────────────────────────────────────
# A root <svg> can be laid out SMALLER than it was written, and every label in it shrinks
# with it. Nothing caught that: validate.py reads SVG font sizes as written, overflow sees
# nothing leave the canvas, and the only witness was the gradient sampler's fontSize
# column, which does not gate. Real case (a client deck, slide 04, 2026-10-20): an
# <svg height="56"> rail in a flex column was flex-shrunk to ~22px when a sibling grew,
# so its 22-unit labels rendered at 8.8px.
#
# Two findings, both measured on the rendered page:
#   • svg squashed   — rendered height < SQUASH_RATIO x its height attribute (a length),
#                      or the SVG is a flex item and re-measuring it with flex-shrink:0
#                      grows either side by more than 1/SQUASH_RATIO: flex took the space.
#                      An SVG sized by CSS (h-full, h-[480px]) is the author's choice and
#                      is not judged against its viewBox — calibration on the EPAM pack
#                      showed a viewBox-aspect rule flags deliberately fitted diagrams.
#   • svg text small — SVG text whose RENDERED size (font-size x the screen CTM scale) is
#                      below the pack's typography.minFontSizePx, when the pack enforces
#                      the floor. Same floor validate.py applies to the written size.
#
# Escape hatch: data-svg-scale="ok" on the <svg> for a deliberate thumbnail. Decorative
# glyphs (data-decor-text / data-decor-bleed) and client logos are exempt as elsewhere.

SQUASH_RATIO = 0.9
FLOOR_EPS = 0.25  # px: sub-pixel CTM rounding is not a defect

SVG_SIZE_JS = """
([ratio, floor, eps]) => {
  const slide = document.getElementById('slide');
  if (!slide) return { error: 'no #slide element' };
  // the measurement is in canvas px even if a viewer scales #slide
  const k0 = slide.offsetWidth ? slide.getBoundingClientRect().width / slide.offsetWidth : 1;
  const exempt = '[data-svg-scale="ok"], [data-decor-text="ok"], [data-decor-bleed="ok"], [data-client-logo="ok"]';
  const label = (svg) => (svg.getAttribute('aria-label') || svg.getAttribute('class') || '').slice(0, 60)
    || ((svg.querySelector('text') || {}).textContent || '').trim().slice(0, 40) || 'svg';
  // the opening tag, trimmed to the attributes that find it in the source
  const tag = (svg) => '<svg' + ['id', 'class', 'aria-label', 'viewBox', 'width', 'height']
    .filter(a => svg.hasAttribute(a)).map(a => ` ${a}="${svg.getAttribute(a).slice(0, 40)}"`).join('') + '>';
  const out = [];
  for (const svg of slide.querySelectorAll('svg')) {
    if (svg.parentElement && svg.parentElement.closest('svg')) continue;   // root svgs only
    if (svg.closest(exempt)) continue;
    const cs = getComputedStyle(svg);
    if (cs.display === 'none' || cs.visibility === 'hidden') continue;
    const r = svg.getBoundingClientRect();
    if (r.width < 1 || r.height < 1) continue;
    const w = r.width / k0, h = r.height / k0;
    let want = null, basis = null, got = h;
    const ha = (svg.getAttribute('height') || '').trim();
    const mh = ha.match(/^([\\d.]+)(px)?$/);
    if (mh && h < ratio * parseFloat(mh[1])) { want = parseFloat(mh[1]); basis = 'height="' + ha + '"'; }
    const pd = svg.parentElement ? getComputedStyle(svg.parentElement).display : '';
    if (!want && /flex/.test(pd) && parseFloat(cs.flexShrink) > 0) {
      const prev = svg.style.flexShrink;
      svg.style.flexShrink = '0';
      const n = svg.getBoundingClientRect();
      svg.style.flexShrink = prev;
      const nw = n.width / k0, nh = n.height / k0;
      if (h < ratio * nh) { want = nh; basis = 'flex-shrink:0 height'; }
      else if (w < ratio * nw) { want = nw; got = w; basis = 'flex-shrink:0 width'; }
    }
    if (want) {
      out.push({ kind: 'svg squashed', label: label(svg), element: tag(svg), rendered: Math.round(got * 10) / 10,
                 expected: Math.round(want * 10) / 10, basis,
                 pct: Math.round(100 * got / want) });
    }
    if (floor > 0) {
      for (const t of svg.querySelectorAll('text')) {
        if (t.closest(exempt)) continue;
        const txt = (t.textContent || '').trim();
        if (!txt) continue;
        const tcs = getComputedStyle(t);
        if (tcs.display === 'none' || tcs.visibility === 'hidden') continue;
        const ctm = t.getScreenCTM();
        const k = (ctm ? Math.sqrt(Math.abs(ctm.a * ctm.d - ctm.b * ctm.c)) : 1) / k0;
        const written = parseFloat(tcs.fontSize);
        const px = written * k;
        if (px < floor - eps) {
          out.push({ kind: 'svg text below floor', label: label(svg), element: tag(svg), text: txt.slice(0, 44),
                     rendered: Math.round(px * 10) / 10, written: Math.round(written * 10) / 10,
                     scale: Math.round(k * 100) / 100, floor });
        }
      }
    }
  }
  return { findings: out };
}
"""


def analyze_svg_sizing_page(page, ds):
    """Run the SVG sizing check on an ALREADY-LOADED page. Returns (findings, error)."""
    floor = float(ds.get('typography.minFontSizePx', 0) or 0) if ds.rule('enforceFontSizeFloor') else 0.0
    res = page.evaluate(SVG_SIZE_JS, [SQUASH_RATIO, floor, FLOOR_EPS])
    if 'error' in res:
        return None, res['error']
    return res['findings'], None


def format_svg_sizing_report(name, findings):
    lines = []
    if findings:
        lines.append(name)
        for f in findings[:8]:
            if f['kind'] == 'svg squashed':
                lines.append(f'  FAIL  svg squashed to {f["rendered"]}px, {f["pct"]}% of '
                             f'{f["expected"]}px ({f["basis"]}) — {f["element"]}')
            else:
                lines.append(f'  FAIL  svg text renders at {f["rendered"]}px < {f["floor"]:g}px floor '
                             f'(written {f["written"]:g}, svg scaled x{f["scale"]}) — {f["text"]!r} in {f["element"]}')
        if len(findings) > 8:
            lines.append(f'  … and {len(findings) - 8} more')
    return lines


def check_svg_sizing(paths, ds):
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
            found, err = analyze_svg_sizing_page(page, ds)
            if found is None:
                print(f'{name}\n  FAIL  {err}')
                failures += 1
                continue
            for line in format_svg_sizing_report(name, found):
                print(line)
            failures += len(found)
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

    sizing = check_svg_sizing(targets, ds)
    if sizing:
        print(f'\n{sizing} SVG sizing violation(s) across {n} file(s).')
    else:
        print(f'All {n} file(s) render their SVGs at the written size.')

    if failures or collisions or sizing:
        sys.exit(1)


if __name__ == '__main__':
    main()
