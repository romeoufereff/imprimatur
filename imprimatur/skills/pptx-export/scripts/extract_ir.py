#!/usr/bin/env python3
"""
pptx-export — stage 1: HTML slide → intermediate representation (IR).

Loads a slide in headless Chromium at the native 1920x1080 viewport (the scaler resolves
to scale(1) there, so getBoundingClientRect() values ARE slide pixels) and walks the
#slide DOM into a flat, z-ordered list of primitives:

  box    — element with a visible solid background and/or border → PPTX (rounded) rectangle;
           a fully-opaque element whose background-image is exactly one simple
           linear-gradient (a brand-ramp badge, dot, divider bar, chart bar) is ALSO a box,
           carrying a `gradient` field the builder renders as a native gradFill instead of
           a flat colour — editable shape, not a picture.
  text   — "text leaf" (block element whose element descendants are all inline) → PPTX
           textbox with styled runs (size, weight, color, uppercase applied, alignment)
  raster — anything computed styles can't faithfully describe: <svg>, <canvas> (ECharts),
           <img>, a translucent (opacity < 1) decorative wash, or any other
           background-image (photos, layered/radial gradients, repeating patterns) →
           element screenshot PNG placed as a picture. Descendants are baked in and NOT
           walked further. An <img> whose src is an SVG file or data: URI (a co-brand
           logo) also carries that SVG, with its CSS resolved, so it converts to native
           shapes like an inline <svg> instead of shipping as a 1x screenshot.

Gradient text (background-clip:text) keeps its glyphs editable: the run is emitted with
color=the design system's primary and flagged "accent" — a documented approximation, since PPTX has
no per-run gradient fill worth the fidelity trade.

The IR is inspectable JSON (one per slide) + an assets/ folder of raster PNGs — debug the
JSON, not the pptx.

Usage (single file; html2pptx.py drives the whole deck):
    python3 extract_ir.py slide.html --out ir/01.json --assets ir/assets
"""

import argparse
import base64
import json
import os
import sys
from urllib.parse import unquote, urlparse
from urllib.request import url2pathname

from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gradients import css_gradient_window  # noqa: E402

# Depth-independent: anchor on the plugin marker rather than counting `..` hops.
_here = os.path.dirname(os.path.abspath(__file__))
_probe = _here
while not os.path.isdir(os.path.join(_probe, ".claude-plugin")):
    _parent = os.path.dirname(_probe)
    if _parent == _probe:
        raise RuntimeError(f"No .claude-plugin/ found above {_here}")
    _probe = _parent
sys.path.insert(0, os.path.join(_probe, "scripts"))
from ds_config import load as _load_ds  # noqa: E402

_DS = _load_ds()
# Gradient-clipped text has no readable computed colour — the browser reports the
# transparent fill. PPTX cannot reproduce a per-character gradient either, so the run is
# flagged `accent` and painted in the pack's primary. These two values used to be hardcoded
# hexes from whichever pack happened to be the default, so a deck built on any other
# pack exported its accent runs in the wrong brand.
_ACCENT = _DS.color('primary') or '#000000'
_INK = _DS.color('ink') or '#000000'

WALK_JS = r"""
() => {
  const slide = document.getElementById('slide');
  if (!slide) return { error: 'no #slide element' };
  const out = [];
  let rasterSeq = 0;

  const parse = (c) => {
    const m = (c || '').match(/rgba?\(([\d.]+),\s*([\d.]+),\s*([\d.]+)(?:,\s*([\d.]+))?\)/);
    return m ? [+m[1], +m[2], +m[3], m[4] === undefined ? 1 : +m[4]] : null;
  };
  const hex = (rgb) => '#' + rgb.slice(0, 3).map(v => Math.round(v).toString(16).padStart(2, '0')).join('').toUpperCase();
  // Single linear-gradient -> {angle, stops:[{color,pos,alpha}]}, or null for anything
  // else (radial, repeating, several layers, length stop positions, corner directions)
  // — the shape this engine can turn into a native PPTX gradient fill, nothing fancier.
  // Direction: `Ndeg`, `to top|right|bottom|left`, or none (180deg). Stops without a
  // position are spread the way CSS spreads them (first 0 %, last 100 %, the rest evenly
  // between their positioned neighbours): Tailwind's `bg-gradient-to-r from-… to-…`
  // computes to `linear-gradient(to right, rgb(…), rgb(…))` and used to fall through to
  // a screenshot that took the pill's text with it (2026-10-23).
  const parseGrad = (bgi) => {
    if (!bgi || bgi === 'none') return null;
    const single = bgi.match(/^linear-gradient\((.+)\)$/);
    const gradCount = (bgi.match(/gradient\(/g) || []).length;
    if (!single || gradCount !== 1) return null;
    const parts = [];
    let depth = 0, cur = '';
    for (const ch of single[1]) {
      if (ch === '(') depth++;
      if (ch === ')') depth--;
      if (ch === ',' && depth === 0) { parts.push(cur.trim()); cur = ''; } else cur += ch;
    }
    parts.push(cur.trim());
    const SIDES = { 'to top': 0, 'to right': 90, 'to bottom': 180, 'to left': 270 };
    let angle = 180;
    if (/^-?[\d.]+deg$/.test(parts[0])) angle = parseFloat(parts.shift());
    else if (parts[0] in SIDES) angle = SIDES[parts.shift()];
    else if (/^to\s/.test(parts[0])) return null;          // corners depend on the box's aspect
    const stops = [];
    for (const part of parts) {
      const m = part.match(/^(rgba?\([\d.,\s]+\))(?:\s+([\d.]+)%)?$/);
      const col = m && parse(m[1]);
      // alpha is kept per stop: a fade to transparent (cover image-slot overlays,
      // `#FFF 0% → rgba(255,255,255,0) 100%`) used to lose it and export as a solid
      // white block with a hard edge (2026-10-07, client covers).
      if (!col) return null;                                 // px positions, hints, double stops
      stops.push({ color: hex(col), pos: m[2] === undefined ? null : parseFloat(m[2]), alpha: col[3] });
    }
    if (stops.length < 2) return null;
    if (stops[0].pos === null) stops[0].pos = 0;
    if (stops[stops.length - 1].pos === null) stops[stops.length - 1].pos = 100;
    for (let i = 1; i < stops.length; i++) {
      if (stops[i].pos !== null) continue;
      let j = i;
      while (stops[j].pos === null) j++;
      const a = stops[i - 1].pos, step = (stops[j].pos - a) / (j - i + 1);
      for (let k = i; k < j; k++) stops[k].pos = Math.round((a + step * (k - i + 1)) * 1000) / 1000;
    }
    return { angle, stops };
  };
  const rectOf = (el) => {
    const r = el.getBoundingClientRect(), s = slide.getBoundingClientRect();
    return { x: r.left - s.left, y: r.top - s.top, w: r.width, h: r.height };
  };
  const visible = (el, cs) =>
    cs.display !== 'none' && cs.visibility !== 'hidden' && parseFloat(cs.opacity) > 0.05;

  // Slide background. A single linear-gradient is parsed into stops so the builder
  // can emit a NATIVE gradient fill (cover/divider slides stay editable); anything
  // else image-like falls back to the full-slide raster.
  const scs = getComputedStyle(slide);
  const sbg = parse(scs.backgroundColor);
  const slideNode = {
    kind: 'slide',
    bg: (sbg && sbg[3] > 0) ? hex(sbg) : '#FFFFFF',
    bgImage: scs.backgroundImage !== 'none',
  };
  if (slideNode.bgImage) {
    const bgi = scs.backgroundImage;
    const grad = parseGrad(bgi);
    if (grad) {
      slideNode.bgGradient = grad;
      slideNode.bgGradientCss = bgi;
      slideNode.bgImage = false;           // native gradient — do NOT full-raster
    }
  }

  const isTextLeaf = (el) => {
    if (!(el.textContent || '').trim()) return false;
    for (const d of el.querySelectorAll('*')) {
      const t = d.tagName.toLowerCase();
      if (['svg', 'img', 'canvas', 'video'].includes(t)) return false;
      const dcs = getComputedStyle(d);
      if (!dcs.display.startsWith('inline') && dcs.display !== 'none') return false;
    }
    return true;
  };

  // Extract styled runs from a text-leaf element — LINE-AWARE: each word's rendered
  // line is measured via Range rects, and soft wraps become explicit '\n' runs. The
  // builder then disables wrapping entirely, so PowerPoint (or any renderer with
  // different font metrics) reproduces the browser's exact line breaks instead of
  // reflowing titles into neighboring elements.
  const runsOf = (el) => {
    const styleOf = (node) => {
      const cs = getComputedStyle(node);
      const col = parse(cs.color);
      const accent = (cs.webkitBackgroundClip || cs.backgroundClip) === 'text';
      const ls = cs.letterSpacing === 'normal' ? 0 : parseFloat(cs.letterSpacing) || 0;
      let size = parseFloat(cs.fontSize);
      // per-RUN line-height: a leaf may mix sizes (28px title + 20px desc in one card);
      // one container-level value would squeeze the larger line (real bug, slide 11)
      const lh = parseFloat(cs.lineHeight);
      // <sup>/<sub> (vertical-align super|sub) is a baseline-offset RUN, not a new line:
      // a:rPr baseline (+30 % / -25 %). PowerPoint draws an offset run smaller on its
      // own, so the run carries its parent's size — the browser's own smaller sup size
      // would be shrunk twice. ("migVisor™" put the ™ in a paragraph of its own, 2026-10-23.)
      const baseline = cs.verticalAlign === 'super' ? 30 : cs.verticalAlign === 'sub' ? -25 : 0;
      if (baseline && node.parentElement) size = parseFloat(getComputedStyle(node.parentElement).fontSize) || size;
      return {
        size,
        baseline: baseline || undefined,
        weight: parseInt(cs.fontWeight, 10) || 400,
        // the computed stack, so a two-family pack (display titles + text body) keeps
        // each run's own face; build_pptx resolves it against the pack's families
        family: cs.fontFamily,
        color: accent ? '__DS_ACCENT__' : (col ? hex(col) : '__DS_INK__'),
        accent,
        // the deck's OWN computed gradient (respects any !important override style
        // block), not the pack's generic default — a deck that overrides the brand
        // ramp (e.g. dropping violet) must export that ramp, not the pack's raw one.
        accentGradient: accent ? cs.backgroundImage : undefined,
        upper: cs.textTransform === 'uppercase',
        italic: cs.fontStyle === 'italic',
        spacing: ls,
        lineHeight: isFinite(lh) ? lh : Math.round(size * 1.2),
      };
    };
    // `sp`: is there whitespace between this word and the one before it? A styled run
    // inside a word (mig<span class="accent">V</span>isor) splits it across text nodes
    // with nothing between them; joining every pair of words with ' ' exported it as
    // "mig V isor" (2026-10-23). Trailing whitespace carries over to the next text node.
    const measureWords = (textNode, st, words) => {
      const s = textNode.textContent;
      const re = /\S+/g;
      let m, end = -1;
      while ((m = re.exec(s)) !== null) {
        const range = document.createRange();
        range.setStart(textNode, m.index);
        range.setEnd(textNode, m.index + m[0].length);
        const rects = range.getClientRects();
        const rr = rects.length ? rects[0] : null;
        const sp = end >= 0 || m.index > 0 || !!words.ws;
        words.push({ w: m[0], st, sp, top: rr ? Math.round(rr.top) : 0,
                     box: rr ? { l: rr.left, t: rr.top, r: rr.right, b: rr.bottom } : null });
        end = m.index + m[0].length;
      }
      words.ws = end >= 0 ? end < s.length : (!!words.ws || s.length > 0);
    };
    const wordsToRuns = (words) => {
      const runs = [];
      const emit = (text, st) => {
        if (!text) return;
        if (st.upper) text = text.toUpperCase();
        const last = runs[runs.length - 1];
        if (last && last.text !== '\n' && JSON.stringify(last.st) === JSON.stringify(st)) last.text += text;
        else runs.push({ text, st });
      };
      // A word starts a new line when its glyph box does not overlap the current line's
      // band by half its height. (A >3 px move of the glyph TOP used to break the line,
      // so a raised <sup> or a larger inline span became a paragraph of its own.)
      const overlap = (b, band) => Math.min(b.b, band.b) - Math.max(b.t, band.t);
      let band = null, started = false, prev = null;
      for (const wd of words) {
        if (wd.br) { runs.push({ text: '\n', st: wd.st || null }); started = false; band = null; prev = null; continue; }
        const b = wd.box;
        const newLine = started && b && band && overlap(b, band) < 0.5 * Math.min(b.b - b.t, band.b - band.t);
        if (newLine) runs.push({ text: '\n', st: wd.st });
        // no whitespace but a visible gap (an inline-block's margin) still reads as a space
        else if (started && (wd.sp || (b && prev && prev.box && b.l - prev.box.r > 0.2 * (wd.st.size || 16)))) emit(' ', wd.st);
        emit(wd.w, wd.st);
        if (b) band = (band && !newLine) ? { t: Math.min(band.t, b.t), b: Math.max(band.b, b.b) } : { t: b.t, b: b.b };
        started = true;
        prev = wd;
      }
      return runs.filter(r => r.text.length);
    };

    const words = [];
    const collect = (node, st) => {
      for (const c of node.childNodes) {
        if (c.nodeType === 3) measureWords(c, st, words);
        else if (c.nodeType === 1) {
          if (c.tagName.toLowerCase() === 'br') { words.push({ br: true }); continue; }
          const ccs = getComputedStyle(c);
          if (ccs.display === 'none') continue;
          collect(c, styleOf(c));
        }
      }
    };
    collect(el, styleOf(el));
    return { runs: wordsToRuns(words), words };
  };

  // Where the text actually sits inside its box. Padding, borders, table-cell
  // vertical-align, flex centring — every CSS route to "text not at the top-left" is
  // read off the MEASURED word boxes instead of re-implementing CSS layout: compare the
  // text's line-box extent with the content box. Result: PPTX insets (px) + a vertical
  // anchor that keeps the behaviour when the user later edits the text in PowerPoint
  // (a centred cell stays centred). Before this the text frame had zero insets and a
  // top anchor, so table cells and padded labels rendered flush top-left (slide 9/12
  // of a 2026-10-01 client deck).
  const layoutOf = (cs, r, words, align) => {
    const px = (v) => parseFloat(v) || 0;
    const pad = {
      l: px(cs.paddingLeft) + px(cs.borderLeftWidth),
      t: px(cs.paddingTop) + px(cs.borderTopWidth),
      r: px(cs.paddingRight) + px(cs.borderRightWidth),
      b: px(cs.paddingBottom) + px(cs.borderBottomWidth),
    };
    const ws = words.filter(w => w.box);
    if (!ws.length) return { insets: pad, anchor: 'top' };
    const sb = slide.getBoundingClientRect();
    let top = Infinity, bot = -Infinity, left = Infinity, right = -Infinity;
    for (const w of ws) {
      // glyph box ± half-leading = the line box CSS actually stacks
      const hl = ((w.st.lineHeight || 0) - (w.box.b - w.box.t)) / 2;
      top = Math.min(top, w.box.t - hl - sb.top);
      bot = Math.max(bot, w.box.b + hl - sb.top);
      left = Math.min(left, w.box.l - sb.left);
      right = Math.max(right, w.box.r - sb.left);
    }
    const TOL = 3;
    const ins = { ...pad };
    const cT = r.y + pad.t, cB = r.y + r.h - pad.b, cL = r.x + pad.l, cR = r.x + r.w - pad.r;
    const gT = top - cT, gB = cB - bot;
    // When the text fills the content box exactly, every anchor fits the pixels; the
    // CSS intent then decides, so an edited cell keeps centring the way the HTML would.
    const fd = cs.flexDirection || 'row';
    const flex = (cs.display || '').includes('flex');
    const cssV = (cs.display === 'table-cell')
      ? ({ middle: 'middle', bottom: 'bottom' })[cs.verticalAlign]
      : flex ? ({ center: 'middle', 'flex-end': 'bottom', end: 'bottom' })[
                 fd.startsWith('column') ? cs.justifyContent : cs.alignItems]
      : undefined;
    let anchor = 'top';
    if (Math.abs(gT) <= TOL && Math.abs(gB) <= TOL && cssV) anchor = cssV;
    else if (Math.abs(gT) <= TOL) anchor = 'top';
    else if (Math.abs(gT - gB) <= TOL) anchor = 'middle';
    else if (Math.abs(gB) <= TOL) anchor = 'bottom';
    else ins.t = Math.max(0, top - r.y);          // unexplained offset: pin where it is
    if (align === 'center') {
      if (Math.abs((left + right) / 2 - (cL + cR) / 2) > TOL) {
        ins.l = Math.max(0, left - r.x); ins.r = Math.max(0, r.x + r.w - right);
      }
    } else if (align === 'right') {
      if (Math.abs(cR - right) > TOL) ins.r = Math.max(0, r.x + r.w - right);
    } else if (Math.abs(left - cL) > TOL) {
      ins.l = Math.max(0, left - r.x);            // e.g. flex justify-content on bare text
    }
    for (const k of Object.keys(ins)) ins[k] = Math.round(ins[k] * 100) / 100;
    return { insets: ins, anchor };
  };

  // Direct text nodes of a NON-leaf container (e.g. a flex cell holding both text and a
  // pill: flex blockifies element children, so the container fails the leaf test and a
  // naive child walk drops the bare text — the "right table column vanished" bug).
  // Returns a text node covering ONLY the container's own text nodes, rect from the
  // measured word boxes.
  const directTextNode = (el, cs) => {
    const styleOf2 = (node) => {
      const c = getComputedStyle(node);
      const col = parse(c.color);
      const accent = (c.webkitBackgroundClip || c.backgroundClip) === 'text';
      const ls = c.letterSpacing === 'normal' ? 0 : parseFloat(c.letterSpacing) || 0;
      const size = parseFloat(c.fontSize);
      const lh = parseFloat(c.lineHeight);
      return { size, weight: parseInt(c.fontWeight, 10) || 400, family: c.fontFamily,
               color: accent ? '__DS_ACCENT__' : (col ? hex(col) : '__DS_INK__'),
               accent, accentGradient: accent ? c.backgroundImage : undefined,
               upper: c.textTransform === 'uppercase',
               italic: c.fontStyle === 'italic', spacing: ls,
               lineHeight: isFinite(lh) ? lh : Math.round(size * 1.2) };
    };
    const st = styleOf2(el);
    const words = [];
    const measure = (tn) => {
      const re = /\S+/g;
      let m;
      while ((m = re.exec(tn.textContent)) !== null) {
        const range = document.createRange();
        range.setStart(tn, m.index);
        range.setEnd(tn, m.index + m[0].length);
        const rects = range.getClientRects();
        const rr = rects.length ? rects[0] : null;
        words.push({ w: m[0], st, top: rr ? Math.round(rr.top) : 0,
                     box: rr ? { l: rr.left, t: rr.top, r: rr.right, b: rr.bottom } : null });
      }
    };
    for (const c of el.childNodes) {
      if (c.nodeType === 3 && c.textContent.trim()) measure(c);
    }
    if (!words.length) return null;
    const boxes = words.map(w => w.box).filter(Boolean);
    if (!boxes.length) return null;
    const sb = slide.getBoundingClientRect();
    const l = Math.min(...boxes.map(b => b.l)), t = Math.min(...boxes.map(b => b.t));
    const rgt = Math.max(...boxes.map(b => b.r)), btm = Math.max(...boxes.map(b => b.b));
    const runs = [];
    let lastTop = null;
    for (const wd of words) {
      if (lastTop !== null && Math.abs(wd.top - lastTop) > 3) runs.push({ text: '\n', st });
      const last = runs[runs.length - 1];
      let text = st.upper ? wd.w.toUpperCase() : wd.w;
      if (last && last.text !== '\n') last.text += ' ' + text;
      else runs.push({ text, st });
      lastTop = wd.top;
    }
    return { kind: 'text', rect: { x: l - sb.left, y: t - sb.top, w: rgt - l, h: btm - t },
             runs, align: cs.textAlign === 'start' ? 'left' : cs.textAlign,
             lineHeight: st.lineHeight };
  };

  const walk = (el) => {
    const tag = el.tagName.toLowerCase();
    if (['script', 'style', 'defs', 'template'].includes(tag)) return;
    const cs = getComputedStyle(el);
    if (!visible(el, cs)) return;
    const r = rectOf(el);
    if (r.w < 1 || r.h < 1) return;

    // Gradient text (background-clip:text) is TEXT, not a picture — this check must
    // run BEFORE the raster branch or accent words ship as mid-title PNGs (v1 bug).
    const clipText = (cs.webkitBackgroundClip || cs.backgroundClip) === 'text';

    // A background-image that's exactly one simple linear-gradient (a brand-ramp badge,
    // dot, divider bar, chart bar — not a photo, not layered) is a shape with a gradient
    // fill, not a picture: parse it BEFORE the raster branch so it can flow into the box
    // path below instead of being screenshotted. Guarded to fully-opaque elements only —
    // a box fill can't reproduce a translucent (opacity < 1) decorative wash the way a
    // screenshot does, so those keep going through raster unchanged.
    const elGrad = (!clipText && tag !== 'canvas' && tag !== 'img' && tag !== 'svg' &&
                    parseFloat(cs.opacity) > 0.99)
      ? parseGrad(cs.backgroundImage) : null;

    // Raster cases — screenshot, don't descend. SVGs additionally get serialized so the
    // builder can embed them as native vector (svgBlip) with the PNG as fallback.
    const isBgImageRaster = !clipText && !elGrad && cs.backgroundImage && cs.backgroundImage !== 'none';
    // A background-image the parser cannot make native (a grid-line pattern, a layered
    // gradient border, a radial wash, a photo) on an element that HOLDS content: the
    // background alone becomes the picture (extract() hides the content for the shot)
    // and the walk descends, so the text and cards on it stay editable shapes on top.
    // Until 1.6.5 the whole element was screenshotted — text, pills and cards baked into
    // one PNG with a warning (a client roadmap's gantt track, a card's gradient border,
    // 2026-10-23), and designers split the layer by hand.
    const bgOnly = isBgImageRaster && !['canvas', 'img', 'svg'].includes(tag) &&
                   (el.children.length > 0 || (el.textContent || '').trim().length > 0);
    if (bgOnly) {
      el.setAttribute('data-ir-raster', String(rasterSeq));
      out.push({ kind: 'raster', id: rasterSeq++, rect: r, isSvg: false, bgOnly: true,
                 tag, cls: (el.getAttribute('class') || '').slice(0, 60) });
    } else if (tag === 'canvas' || tag === 'img' || isBgImageRaster || tag === 'svg') {
      el.setAttribute('data-ir-raster', String(rasterSeq));
      // <img src="logo.svg">: extract() reads the file and inlines it for svg2shapes
      const src = tag === 'img' ? (el.currentSrc || el.src || '') : '';
      const imgSvg = /^data:image\/svg\+xml|\.svg([?#]|$)/i.test(src) ? src : undefined;
      out.push({ kind: 'raster', id: rasterSeq++, rect: r, isSvg: tag === 'svg', imgSvg,
                 tag, cls: (el.getAttribute('class') || '').slice(0, 60) });
      return;
    }

    // Box: visible solid fill and/or borders — PER SIDE. Divider rules are drawn with a
    // single border-bottom/top and no fill; the old top-only check dropped them.
    const bgc = parse(cs.backgroundColor);
    const hasFill = (bgc && bgc[3] > 0.05) || !!elGrad;
    const sides = {};
    for (const side of ['Top', 'Right', 'Bottom', 'Left']) {
      const w = parseFloat(cs[`border${side}Width`]) || 0;
      const c = parse(cs[`border${side}Color`]);
      if (w > 0 && c && c[3] > 0.05 && cs[`border${side}Style`] !== 'none') {
        sides[side] = { color: hex(c), width: w };
      }
    }
    const nSides = Object.keys(sides).length;
    // a bg-only picture already carries this element's fill, borders and pseudo layers
    if (!bgOnly && (hasFill || nSides === 4)) {
      out.push({
        kind: 'box', rect: r,
        fill: bgc && bgc[3] > 0.05 ? hex(bgc) : null,
        fillAlpha: bgc && bgc[3] > 0.05 ? bgc[3] : 0,
        gradient: elGrad || undefined,
        gradientCss: elGrad ? cs.backgroundImage : undefined,
        // background-size/-position/-repeat: a gradient sized to run across several
        // elements (continuous header bars) must be cut per element — see gradients.py
        gradientLayout: elGrad ? {
          size: cs.backgroundSize, position: cs.backgroundPosition, repeat: cs.backgroundRepeat,
          w: r.w - (parseFloat(cs.borderLeftWidth) || 0) - (parseFloat(cs.borderRightWidth) || 0),
          h: r.h - (parseFloat(cs.borderTopWidth) || 0) - (parseFloat(cs.borderBottomWidth) || 0),
        } : undefined,
        border: nSides === 4 ? sides.Top : (sides.Left || sides.Top || null),
        radius: parseFloat(cs.borderTopLeftRadius) || 0,
      });
    }
    if (!bgOnly && nSides > 0 && nSides < 4) {
      // partial borders (divider rules, left-accent bars) → thin filled rects
      const mk = (rr, col) => out.push({ kind: 'box', rect: rr, fill: col, fillAlpha: 1,
                                         border: null, radius: 0 });
      if (sides.Top)    mk({ x: r.x, y: r.y, w: r.w, h: sides.Top.width }, sides.Top.color);
      if (sides.Bottom) mk({ x: r.x, y: r.y + r.h - sides.Bottom.width, w: r.w, h: sides.Bottom.width }, sides.Bottom.color);
      if (sides.Left)   mk({ x: r.x, y: r.y, w: sides.Left.width, h: r.h }, sides.Left.color);
      if (sides.Right)  mk({ x: r.x + r.w - sides.Right.width, y: r.y, w: sides.Right.width, h: r.h }, sides.Right.color);
    }

    // Pseudo-element decorations (bullet dots, accent bars): best-effort synthesis of
    // solid-background ::before/::after as box nodes. Only measurable cases (px sizes;
    // absolute px offsets relative to this element) — text-content pseudos are skipped.
    for (const which of (bgOnly ? [] : ['::before', '::after'])) {
      const ps = getComputedStyle(el, which);
      if (!ps || ps.content === 'none' || ps.display === 'none') continue;
      const pb = parse(ps.backgroundColor);
      const pw = parseFloat(ps.width), ph = parseFloat(ps.height);
      if (!(pb && pb[3] > 0.05) || !isFinite(pw) || !isFinite(ph) || pw < 1 || ph < 1) continue;
      let px0 = r.x, py0 = r.y;
      if (ps.position === 'absolute') {
        const pl = parseFloat(ps.left), pt = parseFloat(ps.top);
        if (isFinite(pl)) px0 = r.x + pl;
        if (isFinite(pt)) py0 = r.y + pt;
      }
      out.push({ kind: 'box', pseudo: true, rect: { x: px0, y: py0, w: pw, h: ph },
                 fill: hex(pb), fillAlpha: pb[3], border: null,
                 radius: parseFloat(ps.borderTopLeftRadius) || 0 });
    }

    // Text leaf → emit text node, stop descending (runs cover inline children).
    if (isTextLeaf(el)) {
      const { runs, words } = runsOf(el);
      if (runs.length) {
        const align = ({ start: 'left', end: 'right', '-webkit-center': 'center' })[cs.textAlign] || cs.textAlign;
        const lay = layoutOf(cs, r, words, align);
        out.push({
          kind: 'text', rect: r, runs, align,
          anchor: lay.anchor, insets: lay.insets,
          lineHeight: parseFloat(cs.lineHeight) || null,
        });
      }
      return;
    }

    // NON-leaf container: its own direct text nodes would be silently dropped by the
    // child walk (flex blockifies children — the "table column vanished" bug). Emit
    // them as their own measured text node, then walk element children as usual.
    const direct = directTextNode(el, cs);
    if (direct) out.push(direct);

    for (const c of el.children) walk(c);
  };

  for (const c of slide.children) walk(c);
  return { slide: slideNode, nodes: out };
}
"""


ISOLATE_JS = """
(id) => {
  const target = document.querySelector(`[data-ir-raster="${id}"]`);
  if (!target) return 0;
  const tr = target.getBoundingClientRect();
  let n = 0;
  for (const el of document.getElementById('slide').querySelectorAll('*')) {
    if (el === target || target.contains(el) || el.contains(target)) continue;
    const r = el.getBoundingClientRect();
    if (r.width && r.height &&
        !(r.left >= tr.right || r.right <= tr.left || r.top >= tr.bottom || r.bottom <= tr.top)) {
      if (getComputedStyle(el).visibility !== 'hidden') {
        el.setAttribute('data-ir-hidden', '');
        el.style.visibility = 'hidden';
        n++;
      }
    }
  }
  return n;
}
"""

# A bg-only raster (a background-image element that holds content) is shot with its
# content invisible: every child at opacity 0 (opacity cannot be undone by a descendant,
# unlike visibility) and the element's own text transparent, so the PNG is the
# background alone and the walk's native text/shapes sit on it without a ghost copy.
HIDE_CONTENT_JS = """
(id) => {
  const t = document.querySelector(`[data-ir-raster="${id}"]`);
  if (!t) return;
  const keep = (el, props) => el.setAttribute('data-ir-content',
    JSON.stringify(props.map(p => [p, el.style.getPropertyValue(p), el.style.getPropertyPriority(p)])));
  keep(t, ['color', '-webkit-text-fill-color', 'text-shadow']);
  t.style.setProperty('color', 'transparent', 'important');
  t.style.setProperty('-webkit-text-fill-color', 'transparent', 'important');
  t.style.setProperty('text-shadow', 'none', 'important');
  for (const c of t.children) {
    keep(c, ['opacity']);
    c.style.setProperty('opacity', '0', 'important');
  }
}
"""

RESTORE_JS = """
() => {
  for (const el of document.querySelectorAll('[data-ir-hidden]')) {
    el.style.visibility = '';
    el.removeAttribute('data-ir-hidden');
  }
  for (const el of document.querySelectorAll('[data-ir-content]')) {
    for (const [p, v, pri] of JSON.parse(el.getAttribute('data-ir-content'))) {
      if (v) el.style.setProperty(p, v, pri); else el.style.removeProperty(p);
    }
    el.removeAttribute('data-ir-content');
  }
  for (const n of document.querySelectorAll('[data-ir-bg]')) {
    const [bc, bi] = JSON.parse(n.getAttribute('data-ir-bg'));
    n.style.backgroundColor = bc;
    n.style.backgroundImage = bi;
    n.removeAttribute('data-ir-bg');
  }
}
"""

# Clear every ANCESTOR background before a raster shot: the element screenshot captures
# whatever pixels sit behind the element's transparent parts — without this, decor blobs
# and SVG fallbacks bake a chunk of the slide gradient into the PNG, which then shows as
# a rectangular seam over the pptx's native background. Combined with
# omit_background=True the PNG keeps real alpha.
CLEAR_ANCESTOR_BG_JS = """
(id) => {
  const t = document.querySelector(`[data-ir-raster="${id}"]`);
  if (!t) return;
  let node = t.parentElement;
  while (node && node.nodeType === 1) {
    node.setAttribute('data-ir-bg',
      JSON.stringify([node.style.backgroundColor || '', node.style.backgroundImage || '']));
    node.style.backgroundColor = 'transparent';
    node.style.backgroundImage = 'none';
    node = node.parentElement;
  }
}
"""

SERIALIZE_SVG_JS = """
(id) => {
  const el = document.querySelector(`[data-ir-raster="${id}"]`);
  if (!el) return null;
  const clone = el.cloneNode(true);
  const cs = getComputedStyle(el);
  clone.setAttribute('xmlns', 'http://www.w3.org/2000/svg');
  clone.setAttribute('xmlns:xlink', 'http://www.w3.org/1999/xlink');
  if (!clone.getAttribute('font-family')) clone.setAttribute('font-family', cs.fontFamily);
  // SVG text styled by a CSS class (font-traf-display) has no font-family attribute for
  // svg2shapes to read: write each text/tspan's computed family onto the clone
  const srcT = el.querySelectorAll('text, tspan'), dstT = clone.querySelectorAll('text, tspan');
  srcT.forEach((t, i) => {
    if (dstT[i] && !dstT[i].getAttribute('font-family'))
      dstT[i].setAttribute('font-family', getComputedStyle(t).fontFamily);
  });
  // chart or diagram (svg2shapes.picture_reason): a chart library's SVG keeps its
  // provenance, and an author's data-pptx on the svg or any ancestor travels with it
  if (el.closest('[_echarts_instance_]')) clone.setAttribute('data-pptx-chart', 'echarts');
  const want = el.closest('[data-pptx]');
  if (want) clone.setAttribute('data-pptx', want.getAttribute('data-pptx'));
  const r = el.getBoundingClientRect();
  clone.setAttribute('width', String(Math.round(r.width)));
  clone.setAttribute('height', String(Math.round(r.height)));
  return clone.outerHTML;
}
"""

# <img src="*.svg"> → the same svg2shapes path as an inline <svg>. The file is parsed and
# probed inside a shadow root sized to the <img>, so its own <style> (Illustrator's
# `.st0{fill:…}`; svg2shapes reads attributes and style="" only) resolves there and
# nowhere else on the slide, and each element's computed paint is written onto it as
# attributes. The <img>'s CSS filter is honoured where it is a flat recolour —
# brightness(0) paints the mark black, `brightness(0) invert(1)` white (the co-brand
# lockup on dark covers); any other filter returns null and the picture stays.
# Until 1.6.6 such an <img> was a 1x element screenshot: the EPAM mark in a client
# co-brand lockup shipped as an 86x31 px PNG (2026-10-23).
INLINE_IMG_SVG_JS = """
([id, text]) => {
  const img = document.querySelector(`[data-ir-raster="${id}"]`);
  if (!img) return null;
  const f = (getComputedStyle(img).filter || 'none').replace(/\\s+/g, ' ').trim();
  const mono = f === 'none' ? null : f === 'brightness(0)' ? 'rgb(0, 0, 0)'
             : f === 'brightness(0) invert(1)' ? 'rgb(255, 255, 255)' : undefined;
  if (mono === undefined) return null;
  const doc = new DOMParser().parseFromString(text, 'image/svg+xml');
  const src = doc.documentElement;
  if (!src || src.localName !== 'svg' || doc.getElementsByTagName('parsererror').length) return null;
  const r = img.getBoundingClientRect();
  const host = document.createElement('div');
  host.style.cssText = `position:fixed;left:0;top:0;width:${r.width}px;height:${r.height}px;` +
                       'visibility:hidden;pointer-events:none';
  document.body.appendChild(host);
  try {
    const svg = document.importNode(src, true);
    if (!svg.getAttribute('viewBox')) {
      const w = parseFloat(svg.getAttribute('width')), h = parseFloat(svg.getAttribute('height'));
      if (!(w > 0 && h > 0)) return null;
      svg.setAttribute('viewBox', `0 0 ${w} ${h}`);
    }
    svg.setAttribute('width', String(r.width));
    svg.setAttribute('height', String(r.height));
    host.attachShadow({ mode: 'open' }).appendChild(svg);
    const frag = (v) => v.replace(/url\\(["']?[^#"')]*(#[^"')]+)["']?\\)/, 'url($1)');
    const paint = 'path, rect, circle, ellipse, line, polyline, polygon, text, tspan';
    svg.querySelectorAll('*').forEach((el) => {
      const cs = getComputedStyle(el);
      if (cs.display === 'none' && el.matches(paint + ', g') && !el.closest('defs, symbol')) {
        el.remove();
        return;
      }
      if (cs.opacity !== '1') el.setAttribute('opacity', cs.opacity);
      if (!el.matches(paint) || el.closest('defs, clipPath, mask, marker, pattern')) return;
      for (const k of ['fill', 'stroke']) {
        const v = frag(cs.getPropertyValue(k));
        el.setAttribute(k, mono && v !== 'none' ? mono : v);
        el.style.removeProperty(k);
      }
      el.setAttribute('stroke-width', String(parseFloat(cs.strokeWidth) || 0));
      for (const k of ['fill-opacity', 'stroke-opacity']) el.setAttribute(k, cs.getPropertyValue(k));
      if (el.matches('text, tspan') && !el.getAttribute('font-family'))
        el.setAttribute('font-family', cs.fontFamily);
    });
    svg.querySelectorAll('style').forEach((st) => st.remove());
    svg.removeAttribute('style');
    const want = img.closest('[data-pptx]');
    if (want) svg.setAttribute('data-pptx', want.getAttribute('data-pptx'));
    return new XMLSerializer().serializeToString(svg);
  } finally {
    host.remove();
  }
}
"""


def img_svg_text(src):
    """The markup behind an <img> SVG src: a file:// path or a data: URI. Remote URLs stay
    pictures — the exporter never fetches."""
    try:
        if src.startswith('file:'):
            with open(url2pathname(urlparse(src).path), encoding='utf-8') as f:
                return f.read()
        if src.startswith('data:'):
            head, _, body = src.partition(',')
            return (base64.b64decode(body).decode('utf-8') if ';base64' in head
                    else unquote(body))
    except (OSError, ValueError, UnicodeDecodeError):
        pass
    return None


# Speaker notes → ppt/notesSlides. Explicit opt-in only: ordinary HTML comments are
# authoring scaffolding ("<!-- Footer chrome -->") and must never leak into the presenter
# view. Two spellings are recognised, anywhere in the document:
#   <aside class="notes">…</aside>   (reveal.js convention; also .speaker-notes or
#                                     [data-speaker-notes]) — keep it display:none
#   <!-- notes: … -->                (or "speaker notes:" / "speaker-notes:")
# <p>/<li> children become separate paragraphs; otherwise blank lines split them.
NOTES_JS = r"""
() => {
  const paras = [];
  const clean = (t) => t.split(/\n\s*\n/).map(x => x.replace(/\s+/g, ' ').trim()).filter(Boolean);
  for (const el of document.querySelectorAll('aside.notes, aside.speaker-notes, .speaker-notes, [data-speaker-notes]')) {
    const attr = el.getAttribute('data-speaker-notes');
    if (attr && attr.trim()) { paras.push(...clean(attr)); continue; }
    const blocks = el.querySelectorAll('p, li');
    if (blocks.length) blocks.forEach(b => { const t = b.textContent.replace(/\s+/g, ' ').trim(); if (t) paras.push(t); });
    else paras.push(...clean(el.textContent || ''));
  }
  const tw = document.createTreeWalker(document, NodeFilter.SHOW_COMMENT);
  let c;
  while ((c = tw.nextNode())) {
    const m = c.nodeValue.match(/^\s*(?:speaker[\s-]?)?notes\s*:\s*([\s\S]*)$/i);
    if (m) paras.push(...clean(m[1]));
  }
  return paras;
}
"""

CHARTS_JS = """
() => {
  if (typeof echarts === 'undefined') return [];
  const slide = document.getElementById('slide');
  const sb = slide.getBoundingClientRect();
  const res = [];
  for (const el of slide.querySelectorAll('div')) {
    const inst = echarts.getInstanceByDom ? echarts.getInstanceByDom(el) : null;
    if (!inst) continue;
    const opt = inst.getOption();
    const r = el.getBoundingClientRect();
    const series = (opt.series || []).map(s => ({
      name: s.name || '', type: s.type,
      data: (s.data || []).map(d => (typeof d === 'object' && d !== null) ? (d.value ?? null) : d),
    }));
    const cats = (opt.xAxis && opt.xAxis[0] && opt.xAxis[0].data) ? opt.xAxis[0].data : [];
    res.push({ rect: { x: r.left - sb.left, y: r.top - sb.top, w: r.width, h: r.height },
               categories: cats, series });
  }
  return res;
}
"""


def extract(page, html_path, assets_dir, name, native_charts=False):
    page.goto('file://' + os.path.abspath(html_path), wait_until='networkidle')
    page.evaluate("document.fonts.ready || Promise.resolve()")
    page.wait_for_timeout(600)  # Tailwind CDN + ECharts render
    ir = page.evaluate(WALK_JS.replace('__DS_ACCENT__', _ACCENT).replace('__DS_INK__', _INK))
    if 'error' in ir:
        raise RuntimeError(f"{html_path}: {ir['error']}")

    for node in ir['nodes']:
        if node.get('bgOnly'):
            print(f"  note: <{node['tag']}> class=\"{node['cls']}\" — its background-image is "
                  f"exported as a picture BEHIND its content; the text and shapes on it stay "
                  f"editable (pptx-export SKILL.md, \"Background images under content\")")

    # A box gradient painted with a custom background-size/-position shows only its
    # slice of a larger gradient image (one ramp running across three header bars).
    # PowerPoint restarts the gradient in every shape, so cut each box's own slice.
    for node in ir['nodes']:
        lay = node.get('gradientLayout')
        if node['kind'] != 'box' or not node.get('gradient') or not lay:
            continue
        g = node['gradient']
        stops = [(s_['pos'] / 100.0, s_['color'], float(s_.get('alpha', 1.0) if s_.get('alpha') is not None else 1.0))
                 for s_ in g['stops']]
        win = css_gradient_window(g['angle'], stops, lay['w'], lay['h'],
                                  lay['size'], lay['position'], lay['repeat'])
        if win is None:
            print(f"  warn: gradient box at {node['rect']} uses background-size "
                  f"{lay['size']!r} / position {lay['position']!r} this exporter cannot "
                  f"slice — exported with the full gradient per shape")
            continue
        if [(round(p, 4), c) for p, c, _ in win] != [(round(p, 4), c) for p, c, _ in stops]:
            node['gradient'] = {'angle': g['angle'],
                                'stops': [{'color': c, 'pos': round(p * 100, 3), 'alpha': a} for p, c, a in win],
                                'windowOf': g['stops']}

    # Opt-in native charts: scrape live ECharts instances; a raster node whose rect sits
    # inside a chart container becomes a 'chart' node (real editable PPTX chart). On any
    # scrape miss the raster/svgBlip path silently remains.
    if native_charts:
        charts = page.evaluate(CHARTS_JS)
        for node in ir['nodes']:
            if node['kind'] != 'raster':
                continue
            nr = node['rect']
            for ch in charts:
                cr = ch['rect']
                inside = (nr['x'] >= cr['x'] - 2 and nr['y'] >= cr['y'] - 2 and
                          nr['x'] + nr['w'] <= cr['x'] + cr['w'] + 2 and
                          nr['y'] + nr['h'] <= cr['y'] + cr['h'] + 2)
                # None values are legitimate gaps (e.g. a forecast series that starts
                # where actuals end) — require only that some numeric data exists
                has_data = any(v is not None for s in ch['series'] for v in s['data'])
                if inside and ch['series'] and has_data:
                    node['kind'] = 'chart'
                    node['chart'] = {'categories': ch['categories'], 'series': ch['series'],
                                     'type': ch['series'][0]['type']}
                    break

    os.makedirs(assets_dir, exist_ok=True)
    # Screenshot each raster node (isolated: overlapping non-relatives hidden during the
    # shot so neighbor pixels never get baked in). SVGs additionally serialize to a .svg
    # asset for native-vector (svgBlip) embedding.
    for node in ir['nodes']:
        if node['kind'] != 'raster':
            continue
        png = os.path.join(assets_dir, f"{name}-r{node['id']}.png")
        el = page.locator(f"[data-ir-raster=\"{node['id']}\"]").first
        try:
            page.evaluate(ISOLATE_JS, node['id'])
            page.evaluate(CLEAR_ANCESTOR_BG_JS, node['id'])
            if node.get('bgOnly'):
                page.evaluate(HIDE_CONTENT_JS, node['id'])
            el.screenshot(path=png, omit_background=True)
            node['asset'] = os.path.abspath(png)
        except Exception as e:  # zero-size after clip etc. — drop the node
            node['asset'] = None
            node['error'] = str(e)
        finally:
            page.evaluate(RESTORE_JS)
        if node.get('isSvg') and node.get('asset'):
            svg_markup = page.evaluate(SERIALIZE_SVG_JS, node['id'])
            if svg_markup:
                svg_path = os.path.join(assets_dir, f"{name}-r{node['id']}.svg")
                with open(svg_path, 'w', encoding='utf-8') as f:
                    f.write(svg_markup)
                node['asset_svg'] = os.path.abspath(svg_path)
        elif node.get('imgSvg') and node.get('asset'):
            text = img_svg_text(node['imgSvg'])
            svg_markup = text and page.evaluate(INLINE_IMG_SVG_JS, [node['id'], text])
            if svg_markup:
                svg_path = os.path.join(assets_dir, f"{name}-r{node['id']}.svg")
                with open(svg_path, 'w', encoding='utf-8') as f:
                    f.write(svg_markup)
                node['asset_svg'] = os.path.abspath(svg_path)
            else:
                print(f"  note: <img src=\"{os.path.basename(urlparse(node['imgSvg']).path)}\"> "
                      f"stays a picture (unreadable SVG or a CSS filter other than a "
                      f"brightness(0)[ invert(1)] recolour)", file=sys.stderr)

    # Slide background gradient (covers, dividers): full-slide screenshot as base layer.
    if ir['slide'].get('bgImage'):
        png = os.path.join(assets_dir, f"{name}-bg.png")
        page.locator('#slide').screenshot(path=png)
        ir['slide']['bgAsset'] = os.path.abspath(png)

    notes = page.evaluate(NOTES_JS)
    if notes:
        ir['notes'] = notes
    ir['source'] = os.path.abspath(html_path)
    return ir


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('html')
    ap.add_argument('--out', required=True)
    ap.add_argument('--assets', required=True)
    args = ap.parse_args()
    name = os.path.splitext(os.path.basename(args.html))[0]
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={'width': 1920, 'height': 1080})
        ir = extract(page, args.html, args.assets, name)
        browser.close()
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, 'w', encoding='utf-8') as f:
        json.dump(ir, f, indent=2)
    kinds = {}
    for n in ir['nodes']:
        kinds[n['kind']] = kinds.get(n['kind'], 0) + 1
    print(f"{name}: {kinds} -> {args.out}")


if __name__ == '__main__':
    main()
