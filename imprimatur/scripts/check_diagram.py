#!/usr/bin/env python3
"""
Render-level diagram checks — design-system agnostic.

check_overflow.py asks "does anything leave the canvas?" and "does anything sit on top of
other content?". Four defects pass both, and each one hid a real fault in a 2026-10-26
restyle review until a script measured it:

  1. TEXT LEAVES ITS BOX — text that grows past the card, band or chip that holds it,
     without leaving the canvas or touching another element. A "box" is the nearest
     ancestor with a fill or with borders on 3 or more sides: a one-sided border (a rule
     line, a top edge) is not a box, and treating it as one reported phantom spills. The
     half-leading of a line box tighter than its glyphs (a numeral at line-height 1) is
     allowed for, so tight badges are not flagged.
  2. CONNECTOR THROUGH TEXT — an SVG line (or path, polyline) whose stroke is visible
     where it crosses a line of HTML or SVG text. Every point along the line is tested,
     endpoints included, against the full glyph band: a 2 px inset and skipping the first
     point missed a route that started inside a label's descender area. A line masked by
     an opaque box painted above it (a label with a white backing) is not visible there,
     so it passes; that is read from the real paint stack, not guessed.
  3. ARROW TIP — a line with an end marker whose tip is buried inside its target (more
     than 3 px past the edge) or floats more than 12 px short of anything. The tip is
     the line's end pushed out by the marker's own geometry (refX, markerWidth, viewBox,
     markerUnits). Targets are SVG shapes, boxed HTML elements and text; a box that also
     holds the line's start is a container, not a target.
  4. CONNECTOR CONTRAST — a connector's stroke (a line with a marker, or one marked
     data-connector) against what is painted behind its middle: at least 3:1, the WCAG
     1.4.11 bar for graphics needed to understand the content.
  5. ACCENT STRIPE (rules.banLeftAccentBars) — a heavier coloured edge on one side of an
     element holding text: the left-accent bar, and the stripe card (a 3 px coloured top
     edge over a 1 px border), which two critique rounds approved and the owner rejected as
     a generic, non-pack pattern. Measured after the cascade: validate.py reads the classes
     as written; a stylesheet rule or an inline style reaches the render without a class.
  6. UNEVEN ROW — cards that share a row top in a grid or flex row but end at different
     heights: the grid stretched each wrapper, not the card inside it.

It also measures the slide's diagram VOCABULARY, which brand-audit and design-crit read:
panel styles in use (filled or not + border geometry + rounding; which tint fills a box is
meaning, the legend's work mode, not style), tinted panels, connector colours (solid and
dashed apart), every element painted in the pack's decision colour or its tint, and text
closer than 8 stage px to a rounded card's edge. Reported always; it GATES only when the
pack opts in with rules.enforceDiagramVocabulary, against the pack's `diagram` block, all
values by ROLE so the engine never holds a brand value:

    "diagram": {
      "connectorRole": "primary",      # the one colour solid connectors use
      "exceptionRole": "muted",        # dashed exception paths
      "decisionRole":  "accent",       # the colour that means "a person decides"
      "decisionTintRole": "surface-accent",   # ... and the card fill that carries it
      "tintRole":      "tint",         # the focal-block fill (a role, or a list of roles)
      "maxPanelStyles": 3,             # rule band · bordered card · tinted card (focal or decision)
      "maxTintPanels":  1
    }

The pack's card vocabulary itself (which cards, fills, radius) is judged by design-crit
and brand-audit against the pack's card templates; a script cannot know it.

Exemptions, as elsewhere: data-overlap="ok" (deliberate composition), data-decor-text /
data-decor-bleed (decoration), data-accent-bar="ok" (a structural left line), and
screen-reader-only text (an .sr-only-style class or an ancestor clipped to 1–2 px) is never
measured. Charts (ECharts containers, data-pptx-chart) are not diagrams and are skipped.

The same lessons, for a deck that is not an imprimatur folder (one HTML file, its own slide
engine), live in skills/deck-review/scripts/qa_deck.js.

Usage:
    python3 scripts/check_diagram.py            # every template in the active pack
    python3 scripts/check_diagram.py FILE...

Exit code 0 = clean; 1 = at least one finding that gates.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _targets  # noqa: E402
from ds_config import load  # noqa: E402

# Distances scale with the canvas: calibrated on a 1440-wide stage (2 / 3 / 12 px there),
# so a 1920 canvas allows 2.7 / 4 / 16 px.
TOL = 2.0 / 1440       # text may sit this far past its box edge
BURIED = 3.0 / 1440    # an arrow tip this deep inside its target is buried
FLOAT = 12.0 / 1440    # an arrow tip this far from anything floats
PAD = 8.0 / 1440       # text this close to a rounded card's edge is cramped
STROKE_MIN = 3.0       # WCAG 1.4.11 non-text contrast

DIAGRAM_JS = r"""
([cfg]) => {
  const slide = document.getElementById('slide');
  if (!slide) return { error: 'no #slide element' };
  const k0 = slide.offsetWidth ? slide.getBoundingClientRect().width / slide.offsetWidth : 1;
  const C = v => Math.round(v / k0 * 10) / 10;
  const EXEMPT = '[data-overlap="ok"], [data-decor-text="ok"], [data-decor-bleed="ok"]';
  const CHART = '[_echarts_instance_], [data-pptx-chart], [data-chart]';
  const NONRENDER = 'marker, defs, symbol, clipPath, mask, pattern';
  const sb = slide.getBoundingClientRect();

  const parse = c => { const m = (c || '').match(/[\d.]+/g); if (!m || m.length < 3) return null; return [+m[0], +m[1], +m[2], m.length < 4 ? 1 : +m[3]]; };
  const alpha = c => { const p = parse(c); return p ? p[3] : 0; };
  const hex = c => { const p = parse(c); if (!p || p[3] < 0.05) return null; return '#' + p.slice(0, 3).map(v => Math.round(v).toString(16).padStart(2, '0')).join('').toUpperCase(); };
  const lum = p => { const [r, g, b] = p.slice(0, 3).map(v => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); }); return 0.2126 * r + 0.7152 * g + 0.0722 * b; };
  const ratio = (a, b) => { const x = lum(a), y = lum(b); return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05); };
  // screen-reader-only by class, or by the pattern itself: an ancestor clipped to a 1 px box (2 px leaves room for a scaled stage)
  const srOnly = el => { if (el.closest('[class*="sr-only"]:not(.not-sr-only), [class*="visually-hidden"]')) return true;
    for (let e = el; e && e !== slide; e = e.parentElement) { const r = e.getBoundingClientRect(), s = getComputedStyle(e);
      if (r.width <= 2 && r.height <= 2 && (s.overflow !== 'visible' || s.clip !== 'auto' || s.clipPath !== 'none')) return true; }
    return false; };
  const visible = el => { for (let e = el; e && e !== slide.parentElement; e = e.parentElement) { const s = getComputedStyle(e); if (s.display === 'none' || s.visibility === 'hidden' || +s.opacity < 0.05) return false; } return true; };
  const sides = s => ['Top', 'Right', 'Bottom', 'Left'].filter(k => parseFloat(s['border' + k + 'Width']) > 0
    && !/none|hidden/.test(s['border' + k + 'Style']) && alpha(s['border' + k + 'Color']) > 0.05);
  const painted = v => !!v && v !== 'none' && (/url\(/.test(v) || alpha(v) > 0.05);
  const filled = s => alpha(s.backgroundColor) > 0.05 || /gradient|url\(/.test(s.backgroundImage);
  const boxed = el => { const s = getComputedStyle(el); return filled(s) || sides(s).length >= 3; };
  const name = el => { const t = (el.innerText || el.textContent || '').trim().replace(/\s+/g, ' ').slice(0, 40);
    const c = (typeof el.className === 'string' ? el.className : (el.getAttribute('class') || '')).trim().split(/\s+/).slice(0, 3).join('.');
    return el.tagName.toLowerCase() + (c ? '.' + c : '') + (t ? ' "' + t + '"' : ''); };
  const toScreen = (svgEl, x, y) => { const m = svgEl.getScreenCTM(); const p = (svgEl.ownerSVGElement || svgEl).createSVGPoint(); p.x = x; p.y = y; return p.matrixTransform(m); };

  // paint-stack probes need hit-testing on everything, overlays included
  const probe = document.createElement('style');
  probe.textContent = '#slide, #slide *:not(#_qa0#_qa1#_qa2) { pointer-events: auto !important; }';
  document.head.appendChild(probe);

  const findings = [], cramped = [];

  // ── text lines: HTML glyph runs + SVG text ─────────────────────────────
  const lines = [];
  const tw = document.createTreeWalker(slide, NodeFilter.SHOW_TEXT, { acceptNode: n =>
    n.textContent.trim().length > 0 && !n.parentElement.closest('script, style, ' + NONRENDER) ? 1 : 2 });
  let n;
  while ((n = tw.nextNode())) {
    const el = n.parentElement;
    if (srOnly(el) || !visible(el)) continue;
    const rg = document.createRange(); rg.selectNodeContents(n);
    const rects = [...rg.getClientRects()].filter(r => r.width > 2 && r.height > 4);
    const txt = n.textContent.trim().replace(/\s+/g, ' ').slice(0, 44);
    const inSvg = !!el.closest('svg');
    rects.forEach(r => lines.push({ r, el, txt, inSvg, exempt: !!el.closest(EXEMPT) }));
    // 1 · text leaves its box (HTML text only; SVG text has its own geometry)
    if (inSvg || !rects.length || el.closest(EXEMPT)) continue;
    let box = el; while (box && box !== slide && !boxed(box)) box = box.parentElement;
    if (!box || box === slide) continue;
    const br = box.getBoundingClientRect(), cs = getComputedStyle(el);
    const lh = parseFloat(cs.lineHeight);
    let worst = 0, side = '';
    // a rounded card whose text runs closer than `pad` to its edge reads as cramped (cards that
    // became cards in a restyle kept their old zero padding). Reported in the vocabulary, not
    // gated: packs ship 8 px card padding on a 1920 canvas, under the 1440-stage 8 px.
    const bs = getComputedStyle(box);
    if (cfg.pad && parseFloat(bs.borderTopLeftRadius) > 0 && br.width / k0 >= 120 && br.height / k0 >= 48) {
      let tight = Infinity;
      rects.forEach(r => { tight = Math.min(tight, r.left - br.left, br.right - r.right, r.top - br.top, br.bottom - r.bottom); });
      if (tight >= 0 && tight / k0 < cfg.pad) cramped.push(C(tight) + 'px: "' + txt.slice(0, 30) + '" in ' + name(box).slice(0, 50));
    }
    rects.forEach(r => {
      const allowV = isNaN(lh) ? 0 : Math.max(0, (r.height - lh * k0) / 2);
      const o = { top: br.top - r.top - allowV, bottom: r.bottom - br.bottom - allowV, left: br.left - r.left, right: r.right - br.right };
      for (const k in o) if (o[k] > worst) { worst = o[k]; side = k; }
    });
    if (worst / k0 > cfg.tol) findings.push({ kind: 'text leaves its box', text: txt, box: name(box).slice(0, 90), side, px: C(worst) });
  }

  // ── strokes ────────────────────────────────────────────────────────────
  const strokes = [...slide.querySelectorAll('svg path, svg line, svg polyline')].filter(p =>
    !p.closest(NONRENDER) && !p.closest(CHART) && !p.closest(EXEMPT) && p.getTotalLength && visible(p));
  const markerOf = (p, which) => { const v = p.getAttribute('marker-' + which) || getComputedStyle(p)['marker' + (which === 'end' ? 'End' : 'Start')];
    const m = /url\(["']?#([^"')]+)["']?\)/.exec(v || ''); return m ? document.getElementById(m[1]) : null; };
  const conns = [];
  strokes.forEach(p => {
    const cs = getComputedStyle(p);
    if (cs.stroke === 'none' || alpha(cs.stroke) < 0.05 || parseFloat(cs.strokeWidth) <= 0) return;
    let L; try { L = p.getTotalLength(); } catch (e) { return; }
    if (!L) return;
    const pts = []; const step = Math.max(0.5, 2 / ((p.getScreenCTM() || { a: 1 }).a || 1) * k0);
    for (let t = 0; t < L; t += step) { const q = p.getPointAtLength(t); pts.push(toScreen(p, q.x, q.y)); }
    const e = p.getPointAtLength(L); pts.push(toScreen(p, e.x, e.y));
    const screenLen = Math.hypot(pts[pts.length - 1].x - pts[0].x, pts[pts.length - 1].y - pts[0].y);
    const open = p.tagName !== 'path' || !/z\s*$/i.test(p.getAttribute('d') || '') || cs.fill === 'none';
    const mEnd = markerOf(p, 'end'), mStart = markerOf(p, 'start');
    const isConn = !!(mEnd || mStart || p.closest('[data-connector]'));
    conns.push({ p, cs, L, pts, open, isConn, mEnd, mStart, dashed: cs.strokeDasharray && cs.strokeDasharray !== 'none', len: screenLen / k0 });
  });

  // 2 · connector through text
  const masks = e => {
    // does this element hide what is painted under it? opaque CSS fill or image, or a filled SVG shape
    const s = getComputedStyle(e);
    if (alpha(s.backgroundColor) >= 0.85 || /gradient|url\(/.test(s.backgroundImage)) return true;
    if (e instanceof SVGGeometryElement && e.tagName !== 'line' && e.tagName !== 'polyline' && s.fill !== 'none') {
      const op = (parseFloat(s.fillOpacity) || 1) * (parseFloat(s.opacity) || 1);
      return op >= 0.85 && (/url\(/.test(s.fill) || alpha(s.fill) >= 0.85);
    }
    return false;
  };
  const above = (x, y, target) => {
    // is an opaque box or shape painted above `target` at this point? (then the line is masked there)
    const stack = document.elementsFromPoint(x, y);
    const svg = target.ownerSVGElement || target;
    let i = stack.indexOf(target); if (i < 0) i = stack.indexOf(svg); if (i < 0) return false;
    for (let j = 0; j < i; j++) if (!stack[j].contains(target) && masks(stack[j])) return true;
    return false;
  };
  conns.forEach(c => {
    if (!c.open || c.len < 20) return;
    const hit = new Map();
    c.pts.forEach(z => lines.forEach(l => {
      if (l.exempt || hit.has(l.txt)) return;
      if (z.x > l.r.left + 0.5 && z.x < l.r.right - 0.5 && z.y > l.r.top + 0.5 && z.y < l.r.bottom - 0.5 && !above(z.x, z.y, c.p))
        hit.set(l.txt, { x: C(z.x - sb.left), y: C(z.y - sb.top) });
    }));
    hit.forEach((at, txt) => findings.push({ kind: 'connector through text', text: txt, at, line: name(c.p).slice(0, 60) }));
  });

  // targets for arrow tips: SVG shapes, boxed HTML elements, text
  const shapes = [...slide.querySelectorAll('svg rect, svg circle, svg ellipse, svg polygon, svg path')].filter(s =>
    !s.closest(NONRENDER) && !s.closest(CHART) && visible(s) && (() => { const cs = getComputedStyle(s);
      if (s.tagName === 'path' && !(/z\s*$/i.test(s.getAttribute('d') || '') && cs.fill !== 'none')) return false;
      return painted(cs.fill) || painted(cs.stroke); })());
  const boxes = [...slide.querySelectorAll('*')].filter(e => !(e instanceof SVGElement) && e !== slide && visible(e) && boxed(e)
    && (() => { const r = e.getBoundingClientRect(); return r.width >= 16 && r.height >= 12 && r.width * r.height < 0.5 * sb.width * sb.height; })());
  const rectDist = (z, r) => { const dx = Math.max(r.left - z.x, 0, z.x - r.right), dy = Math.max(r.top - z.y, 0, z.y - r.bottom);
    return (dx || dy) ? Math.hypot(dx, dy) : -Math.min(z.x - r.left, r.right - z.x, z.y - r.top, r.bottom - z.y); };
  const shapeDist = (s, z) => {
    // signed distance to the shape's outline: positive outside, negative inside
    let L; try { L = s.getTotalLength(); } catch (e) { return rectDist(z, s.getBoundingClientRect()); }
    let d = Infinity; const st = Math.max(L / 400, 0.5);
    for (let t = 0; t <= L; t += st) { const q = s.getPointAtLength(t), w = toScreen(s, q.x, q.y); d = Math.min(d, Math.hypot(w.x - z.x, w.y - z.y)); }
    const inv = s.getScreenCTM().inverse(), u = (s.ownerSVGElement).createSVGPoint(); u.x = z.x; u.y = z.y; const lp = u.matrixTransform(inv);
    let inside = false; try { inside = s.isPointInFill(lp); } catch (e) { const r = s.getBoundingClientRect(); inside = rectDist(z, r) < 0; }
    return inside ? -d : d;
  };
  const tipOf = (c, which) => {
    // the arrow's tip: the line end pushed out by the marker's geometry
    const m = which === 'end' ? c.mEnd : c.mStart;
    const at = which === 'end' ? c.L : 0, back = which === 'end' ? Math.max(0, c.L - 2) : Math.min(c.L, 2);
    const a = c.p.getPointAtLength(at), b = c.p.getPointAtLength(back);
    let dx = a.x - b.x, dy = a.y - b.y; const dl = Math.hypot(dx, dy) || 1; dx /= dl; dy /= dl;
    let off = 0;
    try {
      const vb = m.viewBox && m.viewBox.baseVal && m.viewBox.baseVal.width ? m.viewBox.baseVal : null;
      const mw = m.markerWidth.baseVal.value || 3, refX = m.refX.baseVal.value || 0;
      let maxX = vb ? vb.x + vb.width : mw;
      const kids = [...m.querySelectorAll('path, polygon, polyline, line, rect, circle')];
      if (kids.length) { maxX = -Infinity; kids.forEach(k => { const bb = k.getBBox(); maxX = Math.max(maxX, bb.x + bb.width); }); }
      const units = (m.getAttribute('markerUnits') || 'strokeWidth') === 'strokeWidth' ? parseFloat(c.cs.strokeWidth) || 1 : 1;
      off = Math.max(0, (maxX - refX) * (vb ? mw / vb.width : 1) * units);
    } catch (e) { off = 0; }
    const t = toScreen(c.p, a.x + dx * off, a.y + dy * off), u = toScreen(c.p, a.x + dx * (off + 1), a.y + dy * (off + 1));
    const ul = Math.hypot(u.x - t.x, u.y - t.y) || 1;
    return { x: t.x, y: t.y, dx: (u.x - t.x) / ul, dy: (u.y - t.y) / ul };
  };
  // 3 · arrow tips. Fine when an edge is within `buried` of the tip, or the first thing ahead
  // of it (along its heading) is within `float`. A gap up to 4x `float` to a node is a near miss;
  // no node ahead is an exit arrow (an axis, "goes out"), which is a design choice. Buried only
  // counts inside a LEAF target: a frame that holds other nodes is a region, not a landing.
  conns.forEach(c => {
    if (!c.mEnd || c.len < 12) return;
    const start = c.pts[0], tip = tipOf(c, 'end'), svgOf = c.p.ownerSVGElement;
    const T = [];
    shapes.forEach(s => { if (s !== c.p && shapeDist(s, start) >= 0) T.push({ d: z => shapeDist(s, z), r: s.getBoundingClientRect(), label: name(s), text: false }); });
    boxes.forEach(b => { if (b.contains(svgOf)) return; const r = b.getBoundingClientRect(); if (rectDist(start, r) < 0) return; T.push({ d: z => rectDist(z, r), r, label: name(b), text: false }); });
    lines.forEach(l => T.push({ d: z => rectDist(z, l.r), r: l.r, label: '"' + l.txt + '"', text: true }));
    if (!T.length) return;
    const dist = T.map(t => t.d(tip));
    if (dist.some(d => Math.abs(d) / k0 <= cfg.buried)) return;
    const tx = { x: C(tip.x - sb.left), y: C(tip.y - sb.top) }, line = name(c.p).slice(0, 60);
    let gap = null, ahead = '';
    for (let g = 1; g <= 4 * cfg.float * k0 && gap === null; g += 1) {
      const z = { x: tip.x + tip.dx * g, y: tip.y + tip.dy * g };
      // a label straight ahead is a landing when it is close; only a node makes a near miss
      T.forEach((t, i) => { if (gap === null && dist[i] >= 0 && (!t.text || g / k0 <= cfg.float) && t.d(z) <= 0) { gap = g; ahead = t.label; } });
    }
    if (gap !== null && gap / k0 <= cfg.float) return;
    const contains = (o, r) => r.left >= o.left - 1 && r.right <= o.right + 1 && r.top >= o.top - 1 && r.bottom <= o.bottom + 1;
    const leafIn = T.map((t, i) => ({ t, d: dist[i] })).filter(x => x.d < 0 && !x.t.text
      && !T.some(o => o !== x.t && !o.text && contains(x.t.r, o.r))).sort((a, b) => b.d - a.d)[0];
    if (leafIn) findings.push({ kind: 'arrow tip buried', px: C(-leafIn.d), target: leafIn.t.label.slice(0, 70), at: tx, line });
    else if (gap !== null) findings.push({ kind: 'arrow tip floats', px: C(gap), target: ahead.slice(0, 70), at: tx, line });
  });

  // 4 · connector stroke contrast
  conns.forEach(c => {
    if (!c.isConn) return;
    const mid = c.pts[Math.floor(c.pts.length / 2)];
    const svg = c.p.ownerSVGElement;
    const stack = document.elementsFromPoint(mid.x, mid.y).filter(e => !svg.contains(e) && e !== svg);
    let bg = null, unsampled = false;
    for (const e of stack) { const s = getComputedStyle(e); if (/gradient|url\(/.test(s.backgroundImage)) { unsampled = true; break; } const p = parse(s.backgroundColor); if (p && p[3] >= 0.85) { bg = p; break; } }
    if (unsampled) return;
    bg = bg || [255, 255, 255, 1];
    const st = parse(c.cs.stroke); if (!st) return;
    const r = ratio(st, bg);
    if (r < cfg.strokeMin) findings.push({ kind: 'connector contrast', ratio: Math.round(r * 100) / 100, stroke: hex(c.cs.stroke), on: hex('rgb(' + bg.slice(0, 3).join(',') + ')'), line: name(c.p).slice(0, 60) });
  });

  // 5 · accent stripes: a heavier coloured edge on ONE side (left or top) of an element that holds
  // text — the left-accent bar and the "stripe card" (a 3px coloured top edge over a 1px border).
  // Both read as generic, not as the pack's card vocabulary. A rule band (top and bottom alike)
  // and a uniform border are not stripes.
  if (cfg.banBars) slide.querySelectorAll('*').forEach(e => {
    if (e instanceof SVGElement || e.closest('[data-accent-bar="ok"]') || !visible(e)) return;
    const s = getComputedStyle(e), r = e.getBoundingClientRect();
    if (r.height / k0 <= 10 || r.width / k0 < 24 || !(e.innerText || '').trim()) return;
    const w = k => (!/none|hidden/.test(s['border' + k + 'Style']) && alpha(s['border' + k + 'Color']) > 0.05) ? parseFloat(s['border' + k + 'Width']) : 0;
    const W = { Top: w('Top'), Right: w('Right'), Bottom: w('Bottom'), Left: w('Left') };
    for (const [side, opp] of [['Left', 'Right'], ['Top', 'Bottom']]) {
      const others = Object.keys(W).filter(k => k !== side).map(k => W[k]);
      // a top-only rule is a divider; a top stripe needs a box under it (a fill or other borders)
      if (side === 'Top' && !filled(s) && Math.max(...others) === 0) continue;
      if (W[side] >= 2 && Math.max(...others) <= W[side] - 1)
        findings.push({ kind: 'accent stripe', side: side.toLowerCase(), width: W[side], colour: hex(s['border' + side + 'Color']), element: name(e).slice(0, 90) });
    }
  });

  // 6 · cards in one row that end at different heights (the "one short card": the grid
  // stretched the wrapper, not the card inside it)
  slide.querySelectorAll('*').forEach(c => {
    if (c instanceof SVGElement || !/grid|flex/.test(getComputedStyle(c).display) || c.children.length < 2 || !visible(c)) return;
    const cards = [...c.children].map(k => boxed(k) ? k : [...k.querySelectorAll('*')].find(x => !(x instanceof SVGElement) && boxed(x) && x.getBoundingClientRect().height / k0 > 40))
      .filter(k => { if (!k || !visible(k)) return false; const r = k.getBoundingClientRect(); return r.width / k0 > 80 && r.height / k0 > 60; });
    const rows = {};
    cards.forEach(k => { const t = Math.round(k.getBoundingClientRect().top / k0 / 4); (rows[t] = rows[t] || []).push(k); });
    Object.values(rows).filter(g => g.length > 1).forEach(g => {
      // a card under 60 % of its neighbour spans fewer rows (a featured card beside a stack), by design
      const hs = g.map(k => C(k.getBoundingClientRect().height)), mn = Math.min(...hs), mx = Math.max(...hs);
      if (mx - mn > cfg.tol * 2 && mn >= 0.6 * mx) findings.push({ kind: 'uneven row', heights: hs, short: name(g[hs.indexOf(mn)]).slice(0, 70) });
    });
  });

  // ── vocabulary (report; gates only when the pack opts in) ──────────────
  const panels = [...slide.querySelectorAll('*')].filter(e => !(e instanceof SVGElement) && e !== slide && visible(e) && !srOnly(e)
    && (() => { const r = e.getBoundingClientRect(); if (r.width / k0 < 120 || r.height / k0 < 48 || r.width * r.height > 0.6 * sb.width * sb.height) return false;
      const s = getComputedStyle(e); return filled(s) || sides(s).length > 0; })());
  const styles = {}; let tinted = 0;
  panels.forEach(e => {
    const s = getComputedStyle(e), sd = sides(s);
    const fill = /gradient|url\(/.test(s.backgroundImage) ? 'gradient' : (hex(s.backgroundColor) || 'none');
    // a style is the box's construction: filled or not, which borders at what width and colour,
    // rounded or square. WHICH tint fills it is meaning (the legend's work mode), not style.
    const tone = fill === 'none' ? 'no fill' : fill === '#FFFFFF' ? 'white' : fill === 'gradient' ? 'gradient' : 'tinted';
    const rest = sd.map(k => k[0] + Math.round(parseFloat(s['border' + k + 'Width'])) + hex(s['border' + k + 'Color'])).join(' ');
    const sig = tone + (rest ? ' · ' + rest : '') + (parseFloat(s.borderTopLeftRadius) > 0 ? ' · rounded' : '');
    (styles[sig] = styles[sig] || []).push(name(e).slice(0, 50));
    if (cfg.tint && cfg.tint.includes(fill)) tinted++;
  });
  const solid = {}, dashed = {};
  conns.forEach(c => { if (!c.isConn) return; const h = hex(c.cs.stroke); if (!h) return; const t = c.dashed ? dashed : solid; t[h] = (t[h] || 0) + 1; });
  const decision = [];
  if (cfg.decision) slide.querySelectorAll('*').forEach(e => {
    if (!visible(e) || e.closest(NONRENDER)) return;
    const s = getComputedStyle(e), hit = [];
    if (cfg.decision.includes(hex(s.color)) && [...e.childNodes].some(x => x.nodeType === 3 && x.textContent.trim())) hit.push('text');
    if (cfg.decision.includes(hex(s.backgroundColor))) hit.push('fill');
    if (sides(s).some(k => cfg.decision.includes(hex(s['border' + k + 'Color'])))) hit.push('border');
    if (e instanceof SVGElement) { if (cfg.decision.includes(hex(s.fill))) hit.push('svg fill'); if (cfg.decision.includes(hex(s.stroke))) hit.push('svg stroke'); }
    if (hit.length) decision.push(hit.join('+') + ': ' + name(e).slice(0, 60));
  });
  probe.remove();
  const vocabulary = { panel_styles: Object.keys(styles).length, panels: styles, tinted_panels: tinted,
    connectors_solid: solid, connectors_dashed: dashed, decision_colour: decision.slice(0, 12), decision_count: decision.length,
    cramped_text: cramped.slice(0, 8), cramped_count: cramped.length };
  return { findings, vocabulary };
}
"""


def config(ds):
    d = ds.get("diagram", {}) or {}
    cw = ds.canvas[0]
    tint_roles = d.get("tintRole", "tint")
    tint_roles = [tint_roles] if isinstance(tint_roles, str) else list(tint_roles)
    return {
        "tol": TOL * cw, "buried": BURIED * cw, "float": FLOAT * cw, "pad": PAD * cw, "strokeMin": STROKE_MIN,
        "banBars": ds.rule("banLeftAccentBars"),
        # the decision colour and its tint (a decision card is filled with the tint)
        "decision": [h.upper() for h in (ds.color(r) for r in (d.get("decisionRole", "accent"),
                     d.get("decisionTintRole", "surface-accent"))) if h] or None,
        "tint": [h.upper() for h in (ds.color(r) for r in tint_roles) if h] or None,
        "connector": (ds.color(d.get("connectorRole", "primary")) or "").upper() or None,
        "exception": (ds.color(d.get("exceptionRole", "muted")) or "").upper() or None,
        "maxPanelStyles": int(d.get("maxPanelStyles", 3)),
        "maxTintPanels": int(d.get("maxTintPanels", 1)),
    }


def vocabulary_findings(voc, cfg):
    """The vocabulary rows that gate under rules.enforceDiagramVocabulary."""
    out = []
    if voc["panel_styles"] > cfg["maxPanelStyles"]:
        out.append({"kind": "too many panel styles", "count": voc["panel_styles"],
                    "max": cfg["maxPanelStyles"], "styles": sorted(voc["panels"])})
    if voc["tinted_panels"] > cfg["maxTintPanels"]:
        out.append({"kind": "too many tinted panels", "count": voc["tinted_panels"],
                    "max": cfg["maxTintPanels"]})
    solid = voc["connectors_solid"]
    if len(solid) > 1 or (cfg["connector"] and solid and set(solid) != {cfg["connector"]}):
        out.append({"kind": "connector colours", "solid": solid, "want": cfg["connector"]})
    dashed = voc["connectors_dashed"]
    if cfg["exception"] and dashed and set(dashed) - {cfg["exception"], cfg["connector"]}:
        out.append({"kind": "exception path colour", "dashed": dashed, "want": cfg["exception"]})
    return out


def analyze_page(page, ds):
    """Run on an ALREADY-LOADED page. Returns (findings, vocabulary, error)."""
    cfg = config(ds)
    res = page.evaluate(DIAGRAM_JS, [cfg])
    if "error" in res:
        return None, None, res["error"]
    findings = res["findings"]
    if ds.rule("enforceDiagramVocabulary"):
        findings += vocabulary_findings(res["vocabulary"], cfg)
    return findings, res["vocabulary"], None


def describe(f):
    k = f["kind"]
    if k == "text leaves its box":
        return f'text leaves its box by {f["px"]}px ({f["side"]}) — {f["text"]!r} in {f["box"]}'
    if k == "connector through text":
        return f'connector runs through text {f["text"]!r} at {f["at"]["x"]},{f["at"]["y"]} — {f["line"]}'
    if k == "arrow tip buried":
        return f'arrow tip buried {f["px"]}px inside {f["target"]} at {f["at"]["x"]},{f["at"]["y"]} — {f["line"]}'
    if k == "arrow tip floats":
        return f'arrow tip floats {f["px"]}px short of {f["target"]} at {f["at"]["x"]},{f["at"]["y"]} — {f["line"]}'
    if k == "connector contrast":
        return f'connector stroke {f["stroke"]} on {f["on"]} = {f["ratio"]}:1 (< 3:1) — {f["line"]}'
    if k == "accent stripe":
        return f'accent stripe: {f["width"]:g}px {f["colour"]} on the {f["side"]} edge only — {f["element"]}'
    if k == "uneven row":
        return f'cards in one row end at different heights ({"/".join(str(h) for h in f["heights"])}px) — {f["short"]} is short'
    if k == "too many panel styles":
        return f'{f["count"]} panel styles (max {f["max"]}): ' + " | ".join(f["styles"])
    if k == "too many tinted panels":
        return f'{f["count"]} tinted panels (max {f["max"]} focal block)'
    if k == "connector colours":
        return f'solid connectors in {f["solid"]} — one colour, {f["want"]}'
    if k == "exception path colour":
        return f'dashed paths in {f["dashed"]} — exception paths use {f["want"]}'
    return str(f)


def format_report(name, findings):
    lines = []
    if findings:
        lines.append(name)
        for f in findings[:10]:
            lines.append("  FAIL  " + describe(f))
        if len(findings) > 10:
            lines.append(f"  … and {len(findings) - 10} more")
    return lines


def main():
    from playwright.sync_api import sync_playwright
    ds = load()
    args, targets = _targets.parse(__doc__.strip().split("\n")[0], ds.templates_dir,
                                   extra=lambda ap: ap.add_argument("--vocabulary", action="store_true",
                                                                    help="also print each file's vocabulary"))
    cw, ch = ds.canvas
    total = 0
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": cw, "height": ch})
        for path in targets:
            name = os.path.basename(path)
            page.goto("file://" + os.path.abspath(path), wait_until="networkidle")
            page.evaluate("document.fonts.ready || Promise.resolve()")
            page.wait_for_timeout(400)
            found, voc, err = analyze_page(page, ds)
            if found is None:
                print(f"{name}\n  FAIL  {err}")
                total += 1
                continue
            for line in format_report(name, found):
                print(line)
            if args.vocabulary:
                print(f"{name}  vocabulary: {voc['panel_styles']} panel styles, {voc['tinted_panels']} tinted, "
                      f"solid {voc['connectors_solid']}, dashed {voc['connectors_dashed']}, "
                      f"decision colour ×{voc['decision_count']}")
            total += len(found)
        browser.close()
    n = len(targets)
    print(f"\n{total} diagram finding(s) across {n} file(s)." if total
          else f"All {n} file(s) pass the diagram checks.")
    sys.exit(1 if total else 0)


if __name__ == "__main__":
    main()
