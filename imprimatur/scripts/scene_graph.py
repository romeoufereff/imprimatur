#!/usr/bin/env python3
"""
Scene graph of a slide — what a motion director reads instead of raw HTML.

Loads the slide once (static) and prints a compact inventory of what is on it and how the
parts relate: the text regions by role, every card/list with its heading, and — for bespoke
SVG diagrams — the NODES (shapes big enough to be a thing, with the label that sits on them),
the EDGES (stroked lines/paths, with the nodes they connect, from → to by arrow marker),
free-standing labels, and the reading-order / flow direction the geometry implies. The brief's
Message / Visual / Emphasis / Motion lines are printed alongside when the deck has an outline,
so the story and the structure sit next to each other in ≤ 2–3 KB.

Usage:
    scene_graph.py <slide.html> [--deck-dir D] [--json]
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

GRAPH_JS = r"""
() => {
  const root = document.getElementById('slide'); if (!root) return {error: 'no #slide'};
  const rb = root.getBoundingClientRect(); const sx = 1920 / (rb.width || 1920), sy = 1080 / (rb.height || 1080);
  const box = el => { const b = el.getBoundingClientRect(); return {x: Math.round((b.left - rb.left) * sx), y: Math.round((b.top - rb.top) * sy), w: Math.round(b.width * sx), h: Math.round(b.height * sy)}; };
  const txt = el => (el.textContent || '').replace(/\s+/g, ' ').trim();
  const path = el => { const parts = []; let e = el;
    while (e && e !== root) { const p = e.parentElement; if (!p) return null; parts.unshift(':nth-child(' + (Array.prototype.indexOf.call(p.children, e) + 1) + ')'); e = p; }
    return '#slide > ' + parts.join(' > '); };
  const chromeTop = 1080 - 100;
  const isChrome = el => { const b = box(el); return b.y >= chromeTop || /EPAM|Proprietary/i.test(el.getAttribute('aria-label') || '') ; };

  // ── HTML text regions ──
  const regions = [];
  const roleOf = el => { const c = el.className && el.className.baseVal !== undefined ? '' : (el.className || '');
    if (/eyebrow|caption/.test(c)) return 'eyebrow'; if (el.tagName === 'H1') return 'title'; if (el.tagName === 'H2' || el.tagName === 'H3') return 'heading';
    if (/metric|stat/.test(c)) return 'kpi'; if (el.tagName === 'LI') return 'list-item'; return 'text'; };
  root.querySelectorAll('h1, h2, h3, p, li, [class*="metric"], [class*="stat"]').forEach(el => {
    if (isChrome(el) || el.closest('svg') || !txt(el)) return;
    if (el.tagName === 'P' && el.closest('li')) return;
    regions.push({role: roleOf(el), text: txt(el).slice(0, 120), box: box(el), sel: path(el)});
  });
  // cards: elements with a border/background that hold a heading
  const cards = [];
  root.querySelectorAll('div').forEach(el => {
    if (isChrome(el) || el.closest('svg')) return; const cs = getComputedStyle(el); const b = box(el);
    const framed = (cs.borderStyle !== 'none' && parseFloat(cs.borderWidth) > 0) || (cs.backgroundColor !== 'rgba(0, 0, 0, 0)' && cs.backgroundColor !== 'transparent');
    if (!framed || b.w < 120 || b.h < 60 || b.w > 1700) return;
    const h = el.querySelector('h2,h3,h4,strong,[class*="metric"],[class*="stat"]'); if (!h) return;
    if (cards.some(c => el.contains(document.querySelector(c.sel)))) return;
    cards.push({heading: txt(h).slice(0, 60), text: txt(el).slice(0, 100), box: b, sel: path(el)});
  });

  // ── SVG diagrams ──
  const diagrams = [];
  root.querySelectorAll('svg').forEach(svg => {
    if (isChrome(svg) || svg.getAttribute('aria-label') === 'EPAM') return;
    const sb = box(svg); if (sb.w < 200 || sb.h < 120) return;
    const vb = svg.viewBox.baseVal; const k = vb && vb.width ? sb.w / vb.width : 1;   // user units → slide px
    const toSlide = (x, y) => ({x: Math.round(sb.x + x * k), y: Math.round(sb.y + y * k)});
    const ctmOf = el => { try { const m = el.getCTM(), r = svg.getScreenCTM(); return m && r ? r.inverse().multiply(m) : null; } catch (e) { return null; } };
    const userPt = (el, x, y) => { const m = ctmOf(el); if (!m) return {x, y}; return {x: m.a * x + m.c * y + m.e, y: m.b * x + m.d * y + m.f}; };
    const centerOf = el => { const tag = el.tagName.toLowerCase();
      if (tag === 'circle' || tag === 'ellipse') return userPt(el, +el.getAttribute('cx'), +el.getAttribute('cy'));
      const bb = el.getBBox(); return userPt(el, bb.x + bb.width / 2, bb.y + bb.height / 2); };
    const sizeOf = el => { const bb = el.getBBox(); return {w: Math.round(bb.width * k), h: Math.round(bb.height * k)}; };
    const nodes = [], edges = [], labels = [];
    const shapes = Array.from(svg.querySelectorAll('circle, ellipse, rect, polygon, path')).filter(el => !el.closest('defs, marker, clipPath, mask'));
    shapes.forEach(el => { const cs = getComputedStyle(el); const sz = sizeOf(el); const tag = el.tagName.toLowerCase();
      const filled = cs.fill && cs.fill !== 'none' && cs.fill !== 'rgba(0, 0, 0, 0)';
      const stroked = cs.stroke && cs.stroke !== 'none';
      if (filled && sz.w >= 36 && sz.h >= 24 && !(tag === 'path' && sz.w > 1500)) {
        const c = centerOf(el); nodes.push({el, tag, c, size: sz, fill: cs.fill.slice(0, 40), sel: path(el), label: null, kind: tag === 'polygon' && sz.w < 40 ? 'arrowhead' : 'node'}); }
      else if (stroked && !filled && (tag === 'path' || tag === 'polygon')) edges.push({el, tag});
    });
    Array.from(svg.querySelectorAll('line, polyline')).filter(el => !el.closest('defs, marker')).forEach(el => edges.push({el, tag: el.tagName.toLowerCase()}));
    // labels: text elements; attach to the node whose shape contains the text centre
    Array.from(svg.querySelectorAll('text')).forEach(t => { const tx = txt(t); if (!tx) return; const c = centerOf(t);
      let host = null, best = 1e9;
      nodes.forEach(n => { const d = Math.hypot(n.c.x - c.x, n.c.y - c.y); const r = Math.max(n.size.w, n.size.h) / (2 * k); if (d < r * 0.95 && d < best) { host = n; best = d; } });
      const cs = getComputedStyle(t);
      if (host && !host.label) host.label = tx.slice(0, 60); else labels.push({text: tx.slice(0, 80), at: toSlide(c.x, c.y), fill: cs.fill.slice(0, 30), size: Math.round(parseFloat(cs.fontSize) * k), sel: path(t)}); });
    // edges: endpoints → nearest nodes; direction from marker-end / marker-start (own or inherited)
    const markerOf = (el, which) => { let p = el; while (p && p !== svg) { const v = p.getAttribute && p.getAttribute(which); if (v) return v; p = p.parentElement; } return null; };
    const nearest = (pt) => { let n = null, best = 1e9; nodes.forEach(nd => { const d = Math.hypot(nd.c.x - pt.x, nd.c.y - pt.y); const r = Math.max(nd.size.w, nd.size.h) / (2 * k) + 30; if (d < r && d < best) { n = nd; best = d; } }); return n; };
    const edgesOut = [];
    edges.forEach(e => { let a, b; const el = e.el;
      try { if (e.tag === 'line') { a = userPt(el, +el.getAttribute('x1'), +el.getAttribute('y1')); b = userPt(el, +el.getAttribute('x2'), +el.getAttribute('y2')); }
        else { const L = el.getTotalLength(); const p0 = el.getPointAtLength(0), p1 = el.getPointAtLength(L); a = userPt(el, p0.x, p0.y); b = userPt(el, p1.x, p1.y); } } catch (err) { return; }
      const dash = getComputedStyle(el).strokeDasharray; const cs = getComputedStyle(el);
      const from = nearest(a), to = nearest(b); const mEnd = markerOf(el, 'marker-end'), mStart = markerOf(el, 'marker-start');
      const len = Math.round(Math.hypot(b.x - a.x, b.y - a.y) * k);
      edgesOut.push({from: from ? (from.label || from.tag + '@' + Math.round(from.c.x) + ',' + Math.round(from.c.y)) : null, to: to ? (to.label || to.tag + '@' + Math.round(to.c.x) + ',' + Math.round(to.c.y)) : null,
        a: toSlide(a.x, a.y), b: toSlide(b.x, b.y), len, arrow: mEnd ? 'end' : mStart ? 'start' : null, dashed: !!(dash && dash !== 'none'), stroke: cs.stroke.slice(0, 30), sel: path(el)}); });
    const nodesOut = nodes.filter(n => n.kind === 'node').map(n => ({label: n.label, shape: n.tag, at: toSlide(n.c.x, n.c.y), size: n.size, fill: n.fill, sel: n.sel}));
    // flow direction: where do arrowed edges point?
    const arrowed = edgesOut.filter(e => e.arrow); let dx = 0, dy = 0;
    arrowed.forEach(e => { const s = e.arrow === 'end' ? 1 : -1; dx += s * (e.b.x - e.a.x); dy += s * (e.b.y - e.a.y); });
    const flow = arrowed.length ? (Math.abs(dx) > Math.abs(dy) ? (dx > 0 ? 'left → right' : 'right → left') : (dy > 0 ? 'top → bottom' : 'bottom → top')) : (nodesOut.length >= 5 ? 'ring / cluster' : 'none');
    // a protagonist candidate: a node that only has edges OUT and sits at the flow's start
    const outOnly = nodesOut.filter(n => edgesOut.some(e => e.from === n.label && e.arrow === 'end') && !edgesOut.some(e => e.to === n.label && e.arrow === 'end'));
    diagrams.push({box: sb, label: svg.getAttribute('aria-label') || null, nodes: nodesOut, edges: edgesOut.filter(e => e.len > 12), labels, flow, protagonists: outOnly.map(n => n.label).filter(Boolean), sel: path(svg)});
  });
  return {canvas: [1920, 1080], template: root.getAttribute('data-template'), regions, cards, diagrams};
}
"""


def brief_lines(deck_dir, n):
    out = {}
    if not deck_dir or n is None:
        return out
    p = os.path.join(deck_dir, "narrative-outline.md")
    if not os.path.isfile(p):
        return out
    try:
        from narrative_brief import split_outline
    except Exception:
        return out
    _, briefs, _ = split_outline(open(p, encoding="utf-8").read())
    for line in briefs.get(n, []):
        m = re.match(r"^\s*[-*]?\s*\**(Message|Structure|Visual|Emphasis|Motion|Key data)\**:\s*(.*)$", line, re.I)
        if m:
            out[m.group(1).capitalize()] = m.group(2).strip()
    return out


def render(g, brief):
    L = []
    L.append(f"# Scene graph — {g.get('template') or '?'}")
    for k in ("Message", "Visual", "Emphasis", "Motion"):
        if brief.get(k):
            L.append(f"{k}: {brief[k]}")
    L.append("")
    L.append("## Text")
    for r in g["regions"]:
        b = r["box"]
        L.append(f"- {r['role']:9s} @({b['x']},{b['y']} {b['w']}×{b['h']}) “{r['text']}”")
    if g["cards"]:
        L.append("")
        L.append("## Cards")
        for c in g["cards"]:
            b = c["box"]
            L.append(f"- @({b['x']},{b['y']} {b['w']}×{b['h']}) {c['heading']} — {c['text'][:70]}")
    for d in g["diagrams"]:
        L.append("")
        b = d["box"]
        L.append(f"## Diagram @({b['x']},{b['y']} {b['w']}×{b['h']}) {('“' + d['label'] + '”') if d['label'] else ''}  flow: {d['flow']}"
                 + (f"  protagonist: {', '.join(d['protagonists'])}" if d['protagonists'] else ""))
        for n in d["nodes"]:
            L.append(f"- node {n['shape']:7s} @({n['at']['x']},{n['at']['y']}) {n['size']['w']}×{n['size']['h']} {('“' + n['label'] + '”') if n['label'] else '(no label)'}")
        for e in d["edges"]:
            arrow = "→" if e["arrow"] == "end" else ("←" if e["arrow"] == "start" else "—")
            L.append(f"- edge {e['from'] or '?'} {arrow} {e['to'] or '?'}  ({e['len']}px{', dashed' if e['dashed'] else ''})")
        for t in d["labels"]:
            L.append(f"- label @({t['at']['x']},{t['at']['y']}) {t['size']}px “{t['text']}”")
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser(description=__doc__.strip().split("\n")[0])
    ap.add_argument("slide")
    ap.add_argument("--deck-dir", default=None)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    path = os.path.abspath(args.slide)
    if not os.path.isfile(path):
        sys.exit(f"error: no such file: {path}")
    deck_dir = os.path.abspath(args.deck_dir) if args.deck_dir else os.path.dirname(path)
    m = re.match(r"^(\d{2})-", os.path.basename(path))
    n = int(m.group(1)) if m else None
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1920, "height": 1080})
        page.goto("file://" + path + "?static=1", wait_until="networkidle")
        page.evaluate("document.fonts.ready || Promise.resolve()")
        page.wait_for_timeout(350)
        g = page.evaluate(GRAPH_JS)
        browser.close()
    if g.get("error"):
        sys.exit(f"error: {g['error']}")
    brief = brief_lines(deck_dir, n)
    if args.json:
        g["brief"] = brief
        print(json.dumps(g, ensure_ascii=False, indent=1))
    else:
        print(render(g, brief))


if __name__ == "__main__":
    main()
