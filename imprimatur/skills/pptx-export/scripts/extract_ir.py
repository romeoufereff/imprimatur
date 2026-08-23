#!/usr/bin/env python3
"""
pptx-export — stage 1: HTML slide → intermediate representation (IR).

Loads a slide in headless Chromium at the native 1920x1080 viewport (the scaler resolves
to scale(1) there, so getBoundingClientRect() values ARE slide pixels) and walks the
#slide DOM into a flat, z-ordered list of primitives:

  box    — element with a visible solid background and/or border → PPTX (rounded) rectangle
  text   — "text leaf" (block element whose element descendants are all inline) → PPTX
           textbox with styled runs (size, weight, color, uppercase applied, alignment)
  raster — anything computed styles can't faithfully describe: <svg>, <canvas> (ECharts),
           <img>, and any element with a background-image (brand gradients, decorative
           blobs) → element screenshot PNG placed as a picture. Descendants are baked in
           and NOT walked further.

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

from playwright.sync_api import sync_playwright

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
    const single = bgi.match(/^linear-gradient\((.+)\)$/);
    const gradCount = (bgi.match(/gradient\(/g) || []).length;
    if (single && gradCount === 1) {                       // exactly one gradient, nothing layered
      const inner = single[1];
      const angM = inner.match(/^\s*([\d.]+)deg\s*,/);
      const stops = [];
      const re = /rgba?\([\d.,\s]+\)\s*([\d.]+)%/g;
      let m;
      while ((m = re.exec(inner)) !== null) {
        const col = parse(m[0]);
        if (col) stops.push({ color: hex(col), pos: parseFloat(m[1]) });
      }
      if (angM && stops.length >= 2) {
        slideNode.bgGradient = { angle: parseFloat(angM[1]), stops };
        slideNode.bgGradientCss = bgi;
        slideNode.bgImage = false;           // native gradient — do NOT full-raster
      }
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
      const size = parseFloat(cs.fontSize);
      // per-RUN line-height: a leaf may mix sizes (28px title + 20px desc in one card);
      // one container-level value would squeeze the larger line (real bug, slide 11)
      const lh = parseFloat(cs.lineHeight);
      return {
        size,
        weight: parseInt(cs.fontWeight, 10) || 400,
        color: accent ? '__DS_ACCENT__' : (col ? hex(col) : '__DS_INK__'),
        accent,
        upper: cs.textTransform === 'uppercase',
        italic: cs.fontStyle === 'italic',
        spacing: ls,
        lineHeight: isFinite(lh) ? lh : Math.round(size * 1.2),
      };
    };
    const measureWords = (textNode, st, words) => {
      const re = /\S+/g;
      let m;
      while ((m = re.exec(textNode.textContent)) !== null) {
        const range = document.createRange();
        range.setStart(textNode, m.index);
        range.setEnd(textNode, m.index + m[0].length);
        const rects = range.getClientRects();
        const rr = rects.length ? rects[0] : null;
        words.push({ w: m[0], st, top: rr ? Math.round(rr.top) : 0,
                     box: rr ? { l: rr.left, t: rr.top, r: rr.right, b: rr.bottom } : null });
      }
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
      let lastTop = null;
      for (const wd of words) {
        if (wd.br) { runs.push({ text: '\n', st: wd.st || null }); lastTop = null; continue; }
        if (lastTop !== null && Math.abs(wd.top - lastTop) > 3) runs.push({ text: '\n', st: wd.st });
        else if (lastTop !== null) emit(' ', wd.st);
        emit(wd.w, wd.st);
        lastTop = wd.top;
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
    return wordsToRuns(words);
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
      return { size, weight: parseInt(c.fontWeight, 10) || 400,
               color: accent ? '__DS_ACCENT__' : (col ? hex(col) : '__DS_INK__'),
               accent, upper: c.textTransform === 'uppercase',
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

    // Raster cases — screenshot, don't descend. SVGs additionally get serialized so the
    // builder can embed them as native vector (svgBlip) with the PNG as fallback.
    if (tag === 'canvas' || tag === 'img' ||
        (!clipText && cs.backgroundImage && cs.backgroundImage !== 'none') ||
        (tag === 'svg')) {
      el.setAttribute('data-ir-raster', String(rasterSeq));
      out.push({ kind: 'raster', id: rasterSeq++, rect: r, isSvg: tag === 'svg',
                 tag, cls: (el.getAttribute('class') || '').slice(0, 60) });
      return;
    }

    // Box: visible solid fill and/or borders — PER SIDE. Divider rules are drawn with a
    // single border-bottom/top and no fill; the old top-only check dropped them.
    const bgc = parse(cs.backgroundColor);
    const hasFill = bgc && bgc[3] > 0.05;
    const sides = {};
    for (const side of ['Top', 'Right', 'Bottom', 'Left']) {
      const w = parseFloat(cs[`border${side}Width`]) || 0;
      const c = parse(cs[`border${side}Color`]);
      if (w > 0 && c && c[3] > 0.05 && cs[`border${side}Style`] !== 'none') {
        sides[side] = { color: hex(c), width: w };
      }
    }
    const nSides = Object.keys(sides).length;
    if (hasFill || nSides === 4) {
      out.push({
        kind: 'box', rect: r,
        fill: hasFill ? hex(bgc) : null,
        fillAlpha: hasFill ? bgc[3] : 0,
        border: nSides === 4 ? sides.Top : (sides.Left || sides.Top || null),
        radius: parseFloat(cs.borderTopLeftRadius) || 0,
      });
    }
    if (nSides > 0 && nSides < 4) {
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
    for (const which of ['::before', '::after']) {
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
      const runs = runsOf(el);
      if (runs.length) {
        out.push({
          kind: 'text', rect: r, runs,
          align: cs.textAlign === 'start' ? 'left' : cs.textAlign,
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

RESTORE_JS = """
() => {
  for (const el of document.querySelectorAll('[data-ir-hidden]')) {
    el.style.visibility = '';
    el.removeAttribute('data-ir-hidden');
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
  const r = el.getBoundingClientRect();
  clone.setAttribute('width', String(Math.round(r.width)));
  clone.setAttribute('height', String(Math.round(r.height)));
  return clone.outerHTML;
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

    # Slide background gradient (covers, dividers): full-slide screenshot as base layer.
    if ir['slide'].get('bgImage'):
        png = os.path.join(assets_dir, f"{name}-bg.png")
        page.locator('#slide').screenshot(path=png)
        ir['slide']['bgAsset'] = os.path.abspath(png)

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
