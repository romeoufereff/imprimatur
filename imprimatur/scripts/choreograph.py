#!/usr/bin/env python3
"""
deck-motion §7b — read each finished slide's STRUCTURE and derive how it constructs itself.

One Chromium launch per deck (the render_checks.run shape). For every slide: load it static,
classify regions with the pack's `motion.roleSelectors` (eyebrow, title, subtitle, kpi, bar,
arc, connector, chartBlock, image; `never` = logo / footer / decor), detect structural groups
(≥ 2 siblings with the same tag+class signature under a flex/grid parent → cards, columns,
list items), measure boxes, order hierarchy-first (eyebrow → title → subtitle → containers →
details → connectors → kpi → emphasis; within a tier top-to-bottom then left-to-right), time
the beats inside the pack's entrance budget, pick the EMPHASIS (the brief's `Emphasis:` line
matched against region text; else the largest kpi / gradient-text) as the last beat, and emit
a per-slide spec.

The spec + the runtime (`motion/motion.js`) are INJECTED into the slide head before `</head>`
— the one place validate.py tolerates additions (insert-only head diff; precedent:
deck-review's apply_edits.py). Selectors are `#slide > :nth-child(n)` paths only, so no
palette/class regex can ever match them and Edit-mode class changes never break them. The
block is idempotent (re-running replaces it) and `--strip` removes it byte-for-byte.

The runtime is a NO-OP under Playwright (navigator.webdriver), so PDF, PPTX and every QA
screenshot see the untouched slide; `check_motion.py` (in qa.py) proves the end state equals
the static state pixel-for-pixel and fails on a stale spec (`body_hash`).

Decided ONCE at §1 intake: deck-state.json `motion.enabled` false (or absent) → this script
exits 0 immediately, no browser, no bytes written. A pack without a `motion` block → same.

Usage:
    choreograph.py --deck-dir D                      # every slide in deck-state.json; inject
    choreograph.py --deck-dir D --files 03-x.html …  # only these (after an edit)
    choreograph.py --deck-dir D --check              # exit 1 if any spec's body_hash is stale
    choreograph.py --deck-dir D --summary            # one line per slide from motion/motion.json
    choreograph.py --deck-dir D --strip              # remove every injected block
    choreograph.py --dry-run --json --files T/*.html # plan only (templates, tests); writes nothing
"""
import argparse
import glob
import hashlib
import json
import math
import os
import re
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ds_config import load  # noqa: E402
try:
    from narrative_brief import split_outline  # noqa: E402
except Exception:  # pragma: no cover — the brief is optional input
    split_outline = None

ENGINE_VERSION = "choreograph.py 1.6.0"
SPEC_ID = "imprimatur-motion-spec"
RUNTIME_ID = "imprimatur-motion"
BLOCK_RE = re.compile(
    r"[ \t]*<script id=\"" + SPEC_ID + r"\"[^>]*>.*?</script>\s*"
    r"<script id=\"" + RUNTIME_ID + r"\"[^>]*>\s*</script>\n?",
    re.DOTALL | re.IGNORECASE)
BODY_RE = re.compile(r"<body\b.*?</body\s*>", re.DOTALL | re.IGNORECASE)
RUNTIME_SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "motion", "motion.js")
SLIDE_RE = re.compile(r"^\d{2}-[\w.-]*\.html$")

MAX_BEATS = 12           # more than this and an entrance reads as noise; dense slides merge beats
MERGEABLE = {"eyebrow", "subtitle", "text", "list-item", "row", "svg-text", "svg-card", "kpi", "bar", "arc", "connector", "image", "card", "chartBlock"}
SEL_PATH_RE = re.compile(r":nth-child\((\d+)\)")


def _union_box(bxs):
    bxs = [b for b in bxs if b]
    if not bxs:
        return {}
    x0 = min(b.get("x", 0) for b in bxs); y0 = min(b.get("y", 0) for b in bxs)
    x1 = max(b.get("x", 0) + b.get("w", 0) for b in bxs); y1 = max(b.get("y", 0) + b.get("h", 0) for b in bxs)
    return {"x": x0, "y": y0, "w": x1 - x0, "h": y1 - y0}


def _sels(r):
    return list(r["sel"]) if isinstance(r["sel"], list) else [r["sel"]]


def _merge(a, b):
    sels = _sels(a) + _sels(b)
    out = {"role": a["role"], "sel": sels, "n": len(sels), "box": _union_box([a.get("box"), b.get("box")]),
           "text": " | ".join(x for x in (a.get("text"), b.get("text")) if x)[:160]}
    ba, bb = _boxes_of(a), _boxes_of(b)
    if ba and bb:
        out["boxes"] = ba + bb       # member boxes survive a merge, so a grid still cascades by row
    return out


def merge_beats(regions, max_beats=MAX_BEATS):
    """Collapse an over-long plan: first adjacent same-role runs (three kpi beats → one
    staggered group), then same-role beats anywhere (text, list items, data), until the plan
    has ≤ max_beats. Order is preserved: a merged group sits where its first member was."""
    regions = list(regions)
    changed = True
    while len(regions) > max_beats and changed:
        changed = False
        for i in range(len(regions) - 1):
            a, b = regions[i], regions[i + 1]
            if a["role"] == b["role"] and a["role"] in MERGEABLE:
                regions[i:i + 2] = [_merge(a, b)]
                changed = True
                break
    for role in ("eyebrow", "text", "svg-text", "list-item", "row", "kpi", "image", "connector", "bar", "arc", "card", "svg-card", "subtitle"):
        if len(regions) <= max_beats:
            break
        idx = [i for i, r in enumerate(regions) if r["role"] == role]
        if len(idx) >= 2:
            merged = regions[idx[0]]
            for j in idx[1:]:
                merged = _merge(merged, regions[j])
            regions = [r for i, r in enumerate(regions) if i not in idx[1:]]
            regions[idx[0]] = merged
    return regions


def sel_to_path(sel):
    """'#slide > :nth-child(1) > :nth-child(3)' → [1, 3]; anything else stays a string."""
    if isinstance(sel, str) and sel.startswith("#slide") and ">" in sel:
        nums = SEL_PATH_RE.findall(sel)
        rest = SEL_PATH_RE.sub("", sel).replace("#slide", "").replace(">", "").strip()
        if nums and not rest:
            return [int(n) for n in nums]
    return sel


def compact_spec(spec):
    """The inline form: compact paths, no debug text. motion.json keeps the readable form."""
    out = {k: v for k, v in spec.items() if k not in ("engine", "effects")}
    beats = []
    for b in spec["beats"]:
        nb = {k: v for k, v in b.items() if k != "text"}
        nb["sel"] = [sel_to_path(s) for s in b["sel"]] if isinstance(b["sel"], list) else sel_to_path(b["sel"])
        if isinstance(b.get("waypoints"), list):
            nb["waypoints"] = [sel_to_path(s) for s in b["waypoints"]]
        if isinstance(b.get("onVisit"), list):
            nb["onVisit"] = [[sel_to_path(s) for s in x] if isinstance(x, list) else sel_to_path(x) for x in b["onVisit"]]
        beats.append(nb)
    out["beats"] = beats
    if spec.get("emphasis"):
        out["emphasis"] = dict(spec["emphasis"], sel=sel_to_path(spec["emphasis"]["sel"]))
    out["idle"] = [dict(b, sel=[sel_to_path(s) for s in b["sel"]] if isinstance(b["sel"], list) else sel_to_path(b["sel"]))
                   for b in spec.get("idle") or []]
    return out


# Hierarchy tiers: lower plays earlier. Emphasis is appended last whatever its role.
TIER = {"eyebrow": 0, "title": 1, "subtitle": 2, "card": 3, "svg-card": 3, "image": 4, "text": 4, "list-item": 4,
        "row": 4, "svg-text": 4, "chartBlock": 4, "connector": 5, "bar": 6, "arc": 6, "kpi": 6}
ROLE_DUR = {"eyebrow": "fast", "title": "base", "subtitle": "fast", "card": "base", "svg-card": "base",
            "list-item": "fast", "row": "fast", "text": "fast", "svg-text": "fast", "image": "base",
            "chartBlock": "base", "connector": "base", "bar": "base", "arc": "slow", "kpi": "slow", "emphasis": "base"}
# Effects that need an HTML element (they split or clip text); on anything else they fall back.
HTML_ONLY_EFFECTS = {"words", "words-mask", "lines-mask", "whip", "slam", "snap", "rise-rotate"}
# Cinematic speed weights (seconds): the hero carries gravity, structure is the professional
# standard, details are quick. Slowest ≈ 3× fastest within a scene, as the craft rules ask.
CINEMATIC_DUR = {"eyebrow": 0.25, "title": 0.6, "subtitle": 0.35, "card": 0.5, "svg-card": 0.45, "image": 0.5,
                 "list-item": 0.28, "row": 0.28, "text": 0.3, "svg-text": 0.26, "chartBlock": 0.5,
                 "connector": 0.55, "arc": 0.8, "bar": 0.7, "kpi": 1.4, "emphasis": 0.6}
# Per-slide direction schemes so consecutive slides do not all enter from "y: 30, opacity: 0".
DIRECTION_SCHEMES = [
    {"card": "up", "text": "left", "from": "start"},
    {"card": "left", "text": "up", "from": "center"},
    {"card": "up", "text": "right", "from": "edges"},
    {"card": "right", "text": "left", "from": "start"},
    {"card": "down", "text": "up", "from": "center"},
]
# Motion personality (1.6.0): ONE arrival ease, ONE hero ease (title-card gestures, kinetic text)
# and ONE move ease (on-screen travel) per deck — never per slide. A deck that rotated six curves
# read as noise; consistency reads as confidence (iart motion-art-direction, LottieFiles brand
# motion identity). Variety lives in the gesture: effect, direction, stagger origin. baseMs
# scales the cinematic weights, holdMs is the reading beat of stillness before the point,
# staggerMs the group rhythm. No personality ever overshoots: arrivals stay out-eased.
PERSONALITIES = {
    "corporate": {"ease": "power3.out", "hero": "power4.out", "move": "power2.inOut", "baseMs": 400, "holdMs": 300, "staggerMs": 60,
                  "scaleIn": 0.94, "heroScale": 1.12, "textScale": False},
    "premium":   {"ease": "power2.out", "hero": "expo.out",   "move": "sine.inOut",   "baseMs": 500, "holdMs": 450, "staggerMs": 80,
                  "scaleIn": 0.97, "heroScale": 1.06, "textScale": False},
    "playful":   {"ease": "power4.out", "hero": "circ.out",   "move": "power2.inOut", "baseMs": 300, "holdMs": 250, "staggerMs": 50,
                  "scaleIn": 0.8, "heroScale": 1.3, "textScale": True},
    "energetic": {"ease": "expo.out",   "hero": "power4.out", "move": "power3.inOut", "baseMs": 250, "holdMs": 200, "staggerMs": 40,
                  "scaleIn": 0.6, "heroScale": 1.4, "textScale": True},
}
# Scale budget (Roman, 2026-10-10: "we use zoom in / zoom out too much, and at the end of the
# motion the element looks like it flickers"): a scaled text element is re-rasterised every
# frame and snaps to crisp pixels when the scale ends — that snap is the flicker. corporate and
# premium never scale text (settle → a lift, counters do not grow, rise has no scale); shapes
# and cards settle from scaleIn instead of popping from nothing; the hero slam from heroScale.
# Entrance–exit continuity: the cut that brought a slide in decides where its elements come from
# (a push to the left is followed by cards entering from the right, along the push; a zoom
# settles). Cuts not listed here leave the per-slide rotation in charge.
TRANSITION_SCHEMES = {
    "push":         {"card": "right", "text": "right", "from": "start"},
    "whip-pan":     {"card": "right", "text": "right", "from": "start"},
    "push-depth":   {"card": "up", "text": "up", "from": "center"},
    "zoom-blur":    {"card": "up", "text": "up", "from": "center"},
    "zoom-through": {"card": "up", "text": "up", "from": "center"},
}
# The narrative's logical connective between a slide and the one before (the brief's `Link:`
# line) → the cut that marks it. A cut that does not mark a logical step is decoration.
LINK_TRANSITIONS = {"and-also": "crossfade", "therefore": "push", "but": "whip-pan", "proof": "zoom-blur", "new-act": "push-depth"}


def language_of(m):
    """The deck's motion language from the pack: the personality preset, with any explicit
    `motion.language` keys (ease, hero, move, baseMs, holdMs, staggerMs) on top."""
    name = str(m.get("personality") or "corporate").lower()
    lang = dict(PERSONALITIES.get(name) or PERSONALITIES["corporate"])
    over = m.get("language") if isinstance(m.get("language"), dict) else {}
    lang.update({k: v for k, v in over.items() if k in lang})
    e = m.get("easing") if isinstance(m.get("easing"), dict) else {}
    for src, dst in (("in", "ease"), ("hero", "hero"), ("move", "move")):
        if isinstance(e.get(src), str) and e[src]:
            lang[dst] = e[src]
    lang["name"] = name if name in PERSONALITIES else "corporate"
    return lang

# Runs inside the slide (static, 1920×1080 viewport, scale 1). Returns regions with role,
# box, nth-child selector and text; the Python side orders and times them.
CLASSIFY_JS = r"""
(params) => {
  const root = document.getElementById('slide');
  if (!root) return {error: 'no #slide'};
  const W = params.canvas[0], H = params.canvas[1];
  const rb = root.getBoundingClientRect();
  const sx = rb.width ? W / rb.width : 1, sy = rb.height ? H / rb.height : 1;
  const box = el => { const b = el.getBoundingClientRect();
    return {x: (b.left - rb.left) * sx, y: (b.top - rb.top) * sy, w: b.width * sx, h: b.height * sy}; };
  const SVG_SHAPE = /^(path|line|polyline|polygon|circle|ellipse|rect)$/i;
  const visible = el => { const cs = getComputedStyle(el); const b = box(el);
    if (cs.display === 'none' || cs.visibility === 'hidden') return false;
    // a straight connector has a zero-height box; any stroked SVG shape with extent counts
    if (SVG_SHAPE.test(el.tagName)) return (b.w > 1 || b.h > 1);
    return b.w > 1 && b.h > 1; };
  const path = el => { const parts = [];
    while (el && el !== root) { const p = el.parentElement; if (!p) return null;
      const i = Array.prototype.indexOf.call(p.children, el) + 1; parts.unshift(':nth-child(' + i + ')'); el = p; }
    return el === root ? '#slide > ' + parts.join(' > ') : null; };
  const chromeTop = H - (params.chromeZonePx || 100);
  const never = new Set();
  const markNever = el => { never.add(el); el.querySelectorAll('*').forEach(d => never.add(d)); };
  (params.neverSelectors || []).forEach(s => { try { root.querySelectorAll(s).forEach(markNever); } catch (e) {} });
  root.querySelectorAll('[data-motion="none"]').forEach(markNever);
  root.querySelectorAll('*').forEach(el => { if (never.has(el)) return; const b = box(el);
    if (b.y >= chromeTop && b.h < 80 && !el.querySelector('h1,h2')) markNever(el); });   // footer strip
  root.querySelectorAll('script,style,template,defs,marker,lineargradient,radialgradient,filter').forEach(markNever);
  const isNever = el => { while (el && el !== root) { if (never.has(el)) return true; el = el.parentElement; } return false; };

  const regions = []; const taken = new Set();
  const take = (el, role) => { if (taken.has(el) || isNever(el) || !visible(el)) return null;
    const sel = path(el); if (!sel) return null; taken.add(el);
    const r = {role, sel, box: box(el), text: (el.textContent || '').replace(/\s+/g, ' ').trim().slice(0, 160),
               fontPx: parseFloat(getComputedStyle(el).fontSize) || 0, gradientText: /gradient-text/.test(el.className || '')};
    regions.push(r); return r; };

  // 1 · role selectors from the pack (brand knowledge)
  const roleOrder = ['eyebrow', 'title', 'subtitle', 'kpi', 'bar', 'arc', 'connector', 'chartBlock', 'image'];
  const sels = params.roleSelectors || {};
  const TABLE_TAG = /^(TABLE|THEAD|TBODY|TR|TD|TH)$/;
  roleOrder.forEach(role => { (sels[role] || []).forEach(s => { let list = [];
    try { list = Array.from(root.querySelectorAll(s)); } catch (e) {}
    list = list.filter(el => !TABLE_TAG.test(el.tagName) && !el.closest('table'));   // a table is read as header + rows, never as eyebrows or kpis
    if (role === 'eyebrow' || role === 'subtitle') list = list.filter(el => { const b = box(el), bg = getComputedStyle(el).backgroundColor;
      return !(b.w >= 200 && bg && bg !== 'rgba(0, 0, 0, 0)' && bg !== 'transparent'); });   // a filled bar with a label class is a block (a column header), not an eyebrow
    list.forEach(el => { if (role === 'chartBlock') { take(el, role); el.querySelectorAll('*').forEach(d => taken.add(d)); }
      else take(el, role); }); }); });
  root.querySelectorAll('img, picture, video').forEach(el => take(el, 'image'));

  const insideTaken = el => { let p = el.parentElement; while (p && p !== root) { if (taken.has(p)) return true; p = p.parentElement; } return false; };
  // 1b · bespoke SVG diagrams: boxes → svg-card groups (by parent), labels → svg-text groups,
  //      stroked paths/lines with a marker (own or inherited from a <g>) → connectors,
  //      dashed/arc paths → arc. The logo and decor are already in `never`.
  const SVG_SHAPE_RE = /^(rect|circle|ellipse|polygon|path|line|polyline)$/i;
  const hasMarker = el => { let p = el; while (p && p.tagName.toLowerCase() !== 'svg') { if (p.getAttribute && (p.getAttribute('marker-end') || p.getAttribute('marker-start'))) return true; p = p.parentElement; } return false; };
  const memberText = [];   // every group member with text, for the emphasis matcher
  const groupOf = (members, role) => { const sels = [], bxs = [], texts = [];
    members.forEach(m => { const p = path(m); if (p) { sels.push(p); bxs.push(box(m)); taken.add(m);
      const tx = (m.textContent || '').replace(/\s+/g, ' ').trim(); texts.push(tx.slice(0, 40));
      if (tx) memberText.push({sel: p, text: tx.slice(0, 160), role, fontPx: parseFloat(getComputedStyle(m).fontSize) || 0}); } });
    if (!sels.length) return null;
    const u = {x: Math.min(...bxs.map(b => b.x)), y: Math.min(...bxs.map(b => b.y)),
               w: Math.max(...bxs.map(b => b.x + b.w)) - Math.min(...bxs.map(b => b.x)), h: Math.max(...bxs.map(b => b.y + b.h)) - Math.min(...bxs.map(b => b.y))};
    return sels.length === 1 ? {role, sel: sels[0], box: u, text: texts[0]} : {role, sel: sels, n: sels.length, box: u, text: texts.filter(Boolean).join(' | ').slice(0, 160), boxes: bxs}; };
  const readingOrder = (a, b) => { const A = box(a), B = box(b); return Math.round(A.y / 24) - Math.round(B.y / 24) || A.x - B.x; };
  const svgGroups = [];
  root.querySelectorAll('svg').forEach(svg => {
    if (isNever(svg) || taken.has(svg) || insideTaken(svg)) return;
    const shapes = Array.from(svg.querySelectorAll('rect,circle,ellipse,polygon,path,line,polyline,text')).filter(el => !isNever(el) && !taken.has(el) && visible(el));
    if (shapes.length < 3) return;                       // an icon, not a diagram
    const sb = box(svg); if (sb.w < 200 || sb.h < 120) return;
    const byParent = new Map(); const texts = new Map(); const conns = [], arcs = [];
    shapes.forEach(el => {
      const tag = el.tagName.toLowerCase(); const b = box(el);
      if (tag === 'text') { const k = el.parentElement; (texts.get(k) || texts.set(k, []).get(k)).push(el); return; }
      const stroked = getComputedStyle(el).stroke && getComputedStyle(el).stroke !== 'none';
      if ((tag === 'path' || tag === 'line' || tag === 'polyline') && hasMarker(el)) { conns.push(el); return; }
      if ((tag === 'line' || tag === 'polyline' || tag === 'path') && stroked && (tag === 'line' || getComputedStyle(el).fill === 'none') && !(el.getAttribute('stroke-dasharray') || getComputedStyle(el).strokeDasharray !== 'none') && (b.w >= 20 || b.h >= 20)) { conns.push(el); return; }
      if ((tag === 'path' || tag === 'circle') && stroked && (el.getAttribute('stroke-dasharray') || getComputedStyle(el).strokeDasharray !== 'none') && getComputedStyle(el).fill === 'none') { arcs.push(el); return; }
      if (tag === 'rect' && b.w >= 40 && b.h >= 24) { const k = el.parentElement; (byParent.get(k) || byParent.set(k, []).get(k)).push(el); return; }
      if ((tag === 'circle' || tag === 'ellipse' || tag === 'polygon' || tag === 'path') && !stroked && b.w >= 40 && b.h >= 40) { const k = el.parentElement; (byParent.get(k) || byParent.set(k, []).get(k)).push(el); }
    });
    byParent.forEach(members => { const g = groupOf(members.sort(readingOrder), 'svg-card'); if (g) svgGroups.push(g); });
    texts.forEach(members => { const g = groupOf(members.sort(readingOrder), 'svg-text'); if (g) svgGroups.push(g); });
    if (conns.length) { const g = groupOf(conns.sort(readingOrder), 'connector'); if (g) svgGroups.push(g); }
    if (arcs.length) { const g = groupOf(arcs.sort(readingOrder), 'arc'); if (g) svgGroups.push(g); }
    taken.add(svg); svg.querySelectorAll('*').forEach(d => taken.add(d));
  });
  // 1c · tables: header row → text, body rows → one staggered 'row' group
  root.querySelectorAll('table').forEach(tbl => {
    if (isNever(tbl) || taken.has(tbl) || insideTaken(tbl)) return;
    const head = Array.from(tbl.querySelectorAll('thead tr')).filter(visible);
    const rows = Array.from(tbl.querySelectorAll('tbody tr, :scope > tr')).filter(r => visible(r) && !head.includes(r));
    if (head.length) { const g = groupOf(head, 'text'); if (g) svgGroups.push(g); }
    if (rows.length) { const g = groupOf(rows, rows.length > 1 ? 'row' : 'text'); if (g) svgGroups.push(g); }
    taken.add(tbl); tbl.querySelectorAll('*').forEach(d => taken.add(d));
  });

  // 2 · structural groups: ≥2 siblings, same tag + class signature, under a flex/grid parent
  const sig = el => el.tagName + '|' + Array.from(el.classList).sort().join('.');
  const groups = [];
  const walk = el => {
    if (isNever(el) || taken.has(el)) return;
    const cs = getComputedStyle(el);
    const kids = Array.from(el.children).filter(k => !isNever(k) && visible(k) && !taken.has(k) && !insideTaken(k));
    // a flex/grid row, a list (ul/ol: its items carry their own markers), or a plain block stack of
    // card-sized siblings (three cards one under another need no flex parent to be a group)
    const isList = /^(UL|OL)$/.test(el.tagName), isFlow = /flex|grid/.test(cs.display);
    if ((isFlow || isList || true) && kids.length >= 2) {
      const by = {}; kids.forEach(k => { (by[sig(k)] = by[sig(k)] || []).push(k); });
      // a sibling with a different class but the same tag and a similar box (a highlighted card, the
      // "featured" column) is still a member: alone it would never animate and sit there from frame one
      const big = Object.values(by).filter(ms => ms.length >= 2);
      if (big.length === 1) { const g = big[0]; const a0 = Math.min(...g.map(k => { const b = box(k); return b.w * b.h; }));
        kids.forEach(k => { if (g.includes(k) || k.tagName !== g[0].tagName) return; const b = box(k);
          if (b.w * b.h >= a0 * 0.5 && b.w * b.h <= a0 * 2.5) { g.push(k); const sg = sig(k); if (by[sg] && by[sg].length === 1) delete by[sg]; } });
        g.sort(readingOrder); }
      // no class signature repeats: siblings of the same tag with a similar width and text of their own
      // still form a stack (three cards, three column headers, three bodies — classes may differ per column)
      if (!big.length) {
        const loose = {};
        kids.forEach(k => { const b = box(k); if (b.w < 200 || b.h < 40 || !(k.textContent || '').trim()) return;
          const key = k.tagName + '|' + Math.round(b.w / 40) + '|' + (b.h >= 200 ? 'tall' : 'short'); (loose[key] = loose[key] || []).push(k); });
        Object.values(loose).forEach(ms => { if (ms.length >= 2) { const key = 'loose|' + sig(ms[0]) + '|' + ms.length; by[key] = ms.sort(readingOrder); ms.forEach(k => { const sg = sig(k); if (by[sg] && by[sg].length === 1) delete by[sg]; }); } });
      }
      Object.values(by).forEach(members => {
        if (members.length < 2) return;
        const bxs = members.map(box);
        const minW = Math.min(...bxs.map(b => b.w)), minH = Math.min(...bxs.map(b => b.h));
        if (minW < 40 || minH < 16) return;
        if (!isFlow && !isList && !(minW >= 200 && minH >= 48 && members.every(m => (m.textContent || '').trim()))) return;   // in block flow only card-sized text-bearing siblings group
        const area = Math.min(...bxs.map(b => b.w * b.h));
        const role = (area >= 60000 || members.some(m => m.querySelector('h2,h3,h4'))) ? 'card' : 'list-item';
        const sels = [], texts = [];
        members.forEach(m => { const p = path(m); if (p) { sels.push(p); taken.add(m); m.querySelectorAll('*').forEach(d => { if (!taken.has(d)) taken.add(d); });
          const tx = (m.textContent || '').replace(/\s+/g, ' ').trim(); texts.push(tx.slice(0, 60));
          if (tx) memberText.push({sel: p, text: tx.slice(0, 160), role, fontPx: parseFloat(getComputedStyle(m).fontSize) || 0}); } });
        if (sels.length >= 2) { const b0 = bxs[0];
          groups.push({role, sel: sels, box: {x: Math.min(...bxs.map(b => b.x)), y: Math.min(...bxs.map(b => b.y)),
            w: Math.max(...bxs.map(b => b.x + b.w)) - Math.min(...bxs.map(b => b.x)), h: Math.max(...bxs.map(b => b.y + b.h)) - Math.min(...bxs.map(b => b.y))},
            text: texts.join(' | ').slice(0, 160), n: sels.length, boxes: bxs}); }
      });
    }
    Array.from(el.children).forEach(walk);
  };
  walk(root);
  // kpi / bar / arc / connector found INSIDE a group member still get their own beat (data
  // reads after its container lands); everything else inside a member rides with the member.
  const dataRoles = new Set(['kpi', 'bar', 'arc', 'connector']);
  const keep = regions.filter(r => dataRoles.has(r.role) || !groups.some(g => g.sel.some(s => { const m = document.querySelector(s); return m && m.contains(document.querySelector(r.sel)) && m !== document.querySelector(r.sel); })));

  // 3 · remaining text blocks (a standalone paragraph, a caption) → 'text'
  const textBlocks = [];
  root.querySelectorAll('p, h2, h3, h4, blockquote, figcaption, li, span, div').forEach(el => {
    if (isNever(el) || taken.has(el) || insideTaken(el)) return;
    const own = Array.from(el.childNodes).some(n => n.nodeType === 3 && n.textContent.trim().length > 1);
    const kidsInline = el.children.length > 0 && Array.from(el.children).every(c => /^inline/.test(getComputedStyle(c).display) || c.tagName === 'B' || c.tagName === 'SPAN' && !c.children.length);
    if (!own && !(kidsInline && (el.textContent || '').trim())) return;   // a block holding only inline text (a node's digit in a span) is a text block
    const cs = getComputedStyle(el);
    if (cs.display.indexOf('inline') === 0) {   // inline text rides with its block — unless it is a flex/grid item
      const pd = el.parentElement ? getComputedStyle(el.parentElement).display : '';
      if (!/flex|grid/.test(pd)) return;
    }
    if (!visible(el)) return;
    const r = take(el, 'text'); if (r) textBlocks.push(r);
  });
  const all = keep.concat(svgGroups).concat(groups);
  // Merge stray text blocks sharing a parent into one beat so a dense slide stays ≤ ~12 beats.
  const byParent = {};
  textBlocks.forEach(r => { const el = document.querySelector(r.sel); const p = el && el.parentElement ? path(el.parentElement) || 'root' : 'root';
    (byParent[p] = byParent[p] || []).push(r); });
  Object.values(byParent).forEach(list => {
    if (list.length === 1) { all.push(list[0]); return; }
    const bxs = list.map(r => r.box);
    all.push({role: 'text', sel: list.map(r => r.sel), n: list.length, text: list.map(r => r.text).join(' | ').slice(0, 160),
      box: {x: Math.min(...bxs.map(b => b.x)), y: Math.min(...bxs.map(b => b.y)),
            w: Math.max(...bxs.map(b => b.x + b.w)) - Math.min(...bxs.map(b => b.x)), h: Math.max(...bxs.map(b => b.y + b.h)) - Math.min(...bxs.map(b => b.y))}});
  });

  // 3b · idle drift targets (decorative washes are never-animate for the ENTRANCE, but may drift while the slide is on screen)
  const driftTargets = {};
  (params.driftSelectors || []).forEach(s => { try { const list = Array.from(root.querySelectorAll(s)).map(path).filter(Boolean); if (list.length) driftTargets[s] = list; } catch (e) {} });

  // 4 · emphasis candidates: the explicit attribute wins, then the brief text, then the loudest number
  const explicit = Array.from(root.querySelectorAll('[data-motion="emphasis"]')).filter(el => !isNever(el)).map(path).filter(Boolean);
  const kpis = regions.filter(r => r.role === 'kpi' || r.gradientText).sort((a, b) => (b.fontPx || 0) - (a.fontPx || 0));
  // dark slide? (motion scales down 15 % on a dark ground: it reads brighter on a projector)
  const lum = el => { const c = getComputedStyle(el).backgroundColor || ''; const mm = /rgba?\((\d+),\s*(\d+),\s*(\d+)(?:,\s*([\d.]+))?\)/.exec(c);
    if (!mm || (mm[4] !== undefined && parseFloat(mm[4]) < 0.5)) return null; return (0.2126 * mm[1] + 0.7152 * mm[2] + 0.0722 * mm[3]) / 255; };
  const L0 = lum(root), L1 = lum(document.body), L = L0 !== null ? L0 : (L1 !== null ? L1 : 1);
  return {canvas: [W, H], template: root.getAttribute('data-template') || null, regions: all, driftTargets, dark: L < 0.35,
          explicitEmphasis: explicit[0] || null, loudest: kpis[0] ? kpis[0].sel : null,
          allText: regions.map(r => ({sel: r.sel, text: r.text, role: r.role, fontPx: r.fontPx || 0})).concat(memberText)};
}
"""


# Resolves a director scene's CSS selectors inside #slide to nth-child paths (the only form the
# inline spec carries). Returns {selector: [path, …]}.
RESOLVE_JS = r"""
(sels) => {
  const root = document.getElementById('slide'); if (!root) return {};
  const path = el => { const parts = [];
    while (el && el !== root) { const p = el.parentElement; if (!p) return null;
      const i = Array.prototype.indexOf.call(p.children, el) + 1; parts.unshift(':nth-child(' + i + ')'); el = p; }
    return el === root ? '#slide > ' + parts.join(' > ') : null; };
  const out = {};
  sels.forEach(s => { try { out[s] = Array.from(root.querySelectorAll(s)).map(path).filter(Boolean); } catch (e) { out[s] = []; } });
  return out;
}
"""

DIRECTOR_FILE = "director.json"


def load_director(deck_dir):
    """<deck>/motion/director*.json — scenes the motion director(s) authored per slide, merged
    (several directors may work in parallel, each on its own file), or {}."""
    if not deck_dir:
        return {}
    out = {}
    for p in sorted(glob.glob(os.path.join(deck_dir, "motion", "director*.json"))):
        try:
            data = json.load(open(p, encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(data, dict) and isinstance(data.get("slides"), dict):
            out.update(data["slides"])
    return out


def scene_selectors(scene):
    out = []
    for b in scene.get("beats", []):
        for key in ("sel", "waypoints"):
            v = b.get(key)
            if isinstance(v, str):
                out.append(v)
            elif isinstance(v, list):
                out += [x for x in v if isinstance(x, str)]
        for v in b.get("onVisit") or []:
            if isinstance(v, str):
                out.append(v)
            elif isinstance(v, list):
                out += [x for x in v if isinstance(x, str)]
    e = scene.get("emphasis") or {}
    if isinstance(e.get("sel"), str):
        out.append(e["sel"])
    return sorted(set(out))


def apply_scene(spec, scene, resolved, d_base):
    """Merge a director scene into an auto spec. `keep` roles stay as the opening (eyebrow, title,
    the side panel…); every other auto beat is replaced by the scene's beats, which start when
    the kept beats are done and run on their own clock (a story takes the time it takes)."""
    keep = set(scene.get("keep") or ["eyebrow", "title", "subtitle"])
    kept = [b for b in spec["beats"] if b["role"] in keep and b["role"] != "emphasis"]
    dropped = [b for b in spec["beats"] if b not in kept]
    kept_end = max((b["at"] + b["dur"] + b.get("stagger", 0) * max(0, b.get("n", 1) - 1) for b in kept), default=0.0)
    t0 = round(kept_end * 0.6 + float(scene.get("offset", 0.0)), 3)

    def conv(v):
        if isinstance(v, str):
            paths = resolved.get(v) or []
            return paths[0] if len(paths) == 1 else (paths if paths else v)
        if isinstance(v, list):
            flat = []
            for x in v:
                r = resolved.get(x) if isinstance(x, str) else None
                flat += r if r else ([x] if isinstance(x, str) else [])
            return flat
        return v

    beats = list(kept)
    for i, b in enumerate(scene.get("beats", [])):
        nb = dict(b)
        nb["id"] = b.get("id") or f"d{i + 1}"
        nb["role"] = b.get("role", "scene")
        nb["sel"] = conv(b.get("sel"))
        if isinstance(nb["sel"], list) and len(nb["sel"]) > 1:
            nb["n"] = len(nb["sel"])
        if "waypoints" in b:
            nb["waypoints"] = conv(b["waypoints"])
        if "onVisit" in b:
            nb["onVisit"] = [conv(x) for x in b["onVisit"]]
        nb["at"] = round(t0 + float(b.get("at", 0)), 3)
        nb["dur"] = round(float(b.get("dur", 0.4)), 3)
        beats.append(nb)
    # the end of the scene: a travel beat lasts 0.4 + legs + dwells + 0.4
    def span(b):
        if b.get("effect") == "travel":
            if b.get("along"):
                return 0.25 + float(b.get("dur", 0.8)) + 0.5
            n = len(b.get("waypoints") or []) if isinstance(b.get("waypoints"), list) else 1
            return 0.4 + n * (float(b.get("leg", 0.55)) + float(b.get("dwell", 0.3))) + 0.4
        if b.get("effect") == "focus-pull":
            return 0.45 + max(0.5, float(b.get("dur", 0.6))) + 0.6
        return b["dur"] + b.get("stagger", 0) * max(0, b.get("n", 1) - 1)
    total = max((b["at"] + span(b) for b in beats), default=0.0)
    e = scene.get("emphasis")
    if isinstance(e, dict) and e.get("sel"):
        sel = conv(e["sel"])
        if isinstance(sel, list) and len(sel) == 1:
            sel = sel[0]                       # several focal elements stay a list: focus-pull keeps them all sharp
        # the point comes AFTER the last beat has landed (a reading beat of its own), not over it
        beats.append({"id": f"d{len(scene.get('beats', [])) + 1}", "role": "emphasis", "sel": sel,
                      "effect": e.get("effect", "focus-pull"), "at": round(total + float(scene.get("emphasisGap", 0.35)), 3), "dur": float(e.get("dur", d_base))})
        spec["emphasis"] = {"sel": sel if isinstance(sel, str) else sel[0], "from": "director"}
        total = max(total, beats[-1]["at"] + span(beats[-1]))
    spec["beats"] = beats
    spec["total_ms"] = int(round(total * 1000))
    spec["budget_ms"] = max(spec.get("budget_ms", 0), spec["total_ms"])
    spec["peak_moving"], spec["moving"] = concurrency([b for b in beats if b["role"] != "emphasis"])   # reported, never enforced: a scene is authored
    spec["scene"] = scene.get("name") or "director"
    spec["effects"] = dict(spec.get("effects") or {}, scene=f"{len(scene.get('beats', []))} directed beats, {len(dropped)} auto beats replaced")
    return spec


# ── spec building (pure Python; testable without a browser) ──────────────────

def _words(s):
    return {w for w in re.findall(r"[a-z0-9%€$]{3,}", (s or "").lower())}


def match_emphasis(emphasis_text, candidates, font_of=None):
    """Best region for the brief's `Emphasis:` sentence by word overlap (ties → larger type);
    None below 0.25."""
    want = _words(emphasis_text)
    if not want:
        return None
    font_of = font_of or {}
    best, score = None, (0.0, 0.0)
    for c in candidates:
        have = _words(c.get("text"))
        if not have:
            continue
        inter = len(want & have)
        s = (inter / max(1, min(len(want), len(have))), float(font_of.get(c["sel"], 0)))
        if s > score:
            best, score = c, s
    return best["sel"] if best and score[0] >= 0.25 else None


def pick_effect(role_effects, role, slide_n, prev_choice=None, variety="rotate", fallback="fade"):
    """The pack binds a role to one effect or to a LIST of variants. With variety=rotate the
    variant turns with the slide number and never repeats the previous slide's choice for the
    same role, so two consecutive slides never construct the same way; variety=fixed takes the
    first entry (a brand that wants one gesture everywhere)."""
    v = role_effects.get(role, fallback)
    if isinstance(v, str):
        return v
    if not v:
        return fallback
    if variety == "fixed" or len(v) == 1:
        return v[0]
    i = (int(slide_n or 0) + sum(ord(c) for c in role)) % len(v)
    if v[i] == prev_choice:
        i = (i + 1) % len(v)
    return v[i]


def _span(b):
    """How long a beat occupies the stage: its duration plus the spread of its members."""
    n = b.get("n", 1)
    order = b.get("order")
    spread = (max(order) if order else max(0, n - 1)) * b.get("stagger", 0)
    return b["dur"] + spread


def _boxes_of(r):
    """Per-member boxes of a region when they line up with its selectors (else None)."""
    if isinstance(r.get("sel"), list):
        bx = r.get("boxes")
        return list(bx) if bx and len(bx) == len(r["sel"]) else None
    return [r["box"]] if r.get("box") else None


def member_order(r):
    """Stagger order for a group's members, as multiples of the stagger: a grid cascades in
    reading order with a third of a step added per row (LottieFiles' +20 ms per row); a large
    group (> 8) staggers by distance from its reading origin, so the feel is constant whatever
    the count (iart). None → the runtime's start / center / edges order applies."""
    bxs = _boxes_of(r)
    sels = r.get("sel")
    if not isinstance(sels, list) or not bxs or len(sels) < 4:
        return None
    if len(sels) > 8:
        x0, y0 = min(b["x"] for b in bxs), min(b["y"] for b in bxs)
        dist = [math.hypot(b["x"] - x0, b["y"] - y0) for b in bxs]
        mx = max(dist) or 1.0
        return [round(dd / mx * (len(sels) - 1), 2) for dd in dist]
    rows = {}
    for i, b in enumerate(bxs):
        rows.setdefault(int(round(b["y"] / 40.0)), []).append(i)
    if len(rows) < 2 or max(len(v) for v in rows.values()) < 2:
        return None
    order = [0.0] * len(sels)
    for ri, key in enumerate(sorted(rows)):
        members = sorted(rows[key], key=lambda i: bxs[i]["x"])
        for ci, i in enumerate(members):
            order[i] = round(ri * (len(members) + 0.33) + ci, 2)
    return order


_NUM_RE = re.compile(r"-?\d[\d,]*(?:\.\d+)?")


def _is_ordinal(text):
    """True for a step number or zero-padded label ('01', '6', '3'), False for a quantity."""
    text = (text or "").strip()
    m = _NUM_RE.search(text)
    if not m:
        return True
    raw = m.group(0)
    if re.match(r"^0\d", raw):
        return True
    return text == raw and "." not in raw and abs(float(raw.replace(",", ""))) <= 20


def pair_columns(regions):
    """Two groups with the same member count whose members line up in columns (a header row of
    boxes over a body row of boxes, no wrapper around each column) become column singles in
    reading order: header 1, body 1, header 2, body 2 … The retiming lands a body after its header
    and the next column after the previous one."""
    groups = [r for r in regions if isinstance(r.get("sel"), list) and _boxes_of(r) and r.get("n", 0) >= 2]
    pairs, used = [], set()
    for i, a in enumerate(groups):
        for b in groups[i + 1:]:
            if a["n"] != b["n"] or a["n"] > 4 or id(a) in used or id(b) in used:
                continue
            ba, bb = _boxes_of(a), _boxes_of(b)
            ia = sorted(range(a["n"]), key=lambda k: (round(ba[k]["x"] / 40), ba[k]["y"]))
            ib = sorted(range(b["n"]), key=lambda k: (round(bb[k]["x"] / 40), bb[k]["y"]))
            ok, top = True, None
            for ka, kb in zip(ia, ib):
                A, B = ba[ka], bb[kb]
                ov = min(A["x"] + A["w"], B["x"] + B["w"]) - max(A["x"], B["x"])
                lo, hi = (A, B) if A["y"] < B["y"] else (B, A)
                gap = hi["y"] - (lo["y"] + lo["h"])
                if ov < 0.8 * min(A["w"], B["w"]) or A["w"] < 120 or gap < -8 or gap > 90:
                    ok = False
                    break
                t = A["y"] < B["y"]
                if top is None:
                    top = t
                elif top != t:
                    ok = False
                    break
            if ok:
                pairs.append((a, b, ia, ib, top))
                used.add(id(a)); used.add(id(b))
    if not pairs:
        return regions
    heads = {id(p[0] if p[4] else p[1]): p for p in pairs}
    out = []
    for r in regions:
        if id(r) in heads:
            a, b, ia, ib, top = heads[id(r)]
            head, body, ih, ibd = (a, b, ia, ib) if top else (b, a, ib, ia)
            bh, bbx = _boxes_of(head), _boxes_of(body)
            for c, (kh, kb) in enumerate(zip(ih, ibd)):
                out.append({"role": head["role"], "sel": head["sel"][kh], "box": bh[kh], "text": "", "col": [c, 0]})
                out.append({"role": body["role"], "sel": body["sel"][kb], "box": bbx[kb], "text": "", "col": [c, 1]})
        elif id(r) in used:
            continue
        else:
            out.append(r)
    return out


def _vertical(r):
    """True when a group's members are stacked top to bottom (a list, a column of cards)."""
    bxs = _boxes_of(r)
    if not bxs or len(bxs) < 2:
        return False
    xs = max(b["x"] for b in bxs) - min(b["x"] for b in bxs)
    ys = max(b["y"] for b in bxs) - min(b["y"] for b in bxs)
    return ys > xs


def _tall(r):
    bxs = _boxes_of(r) or ([r["box"]] if r.get("box") else [])
    return bool(bxs) and all(b["h"] > 1.2 * b["w"] for b in bxs)


def _below(k, b):
    """Is box b the caption directly under box k (same column, just beneath)?"""
    if not k or not b:
        return False
    ov = min(k["x"] + k["w"], b["x"] + b["w"]) - max(k["x"], b["x"])
    if ov < 0.5 * min(k["w"], b["w"]):
        return False
    return k["y"] + k["h"] - 12 <= b["y"] <= k["y"] + k["h"] + 90


def retime(beats, overlap, t0):
    """Waterfall timing: each beat starts inside the previous one (a new tier waits a little
    longer). Counters run one after another — the eye reads one moving number at a time."""
    t, last_tier = t0, None
    for i, b in enumerate(beats):
        tier = TIER.get(b["role"], 4)
        if i > 0:
            prev = beats[i - 1]
            if b.get("col") and prev.get("col") and prev["col"][0] == b["col"][0]:
                t = prev["at"] + 0.3                                  # a column's body follows its header
            elif b.get("col") and prev.get("col"):
                t = prev["at"] + max(0.45, _span(prev) * 0.8)         # the next column once this one has landed
            else:
                if b["role"] == "kpi" and prev["role"] == "kpi" and b["effect"] == "count-up":
                    f = 0.6
                else:
                    f = overlap[0] if tier != last_tier else overlap[1]
                t = prev["at"] + _span(prev) * f
        b["at"] = round(t, 3)
        last_tier = tier


def concurrency(beats, slot=0.05):
    """(peak, total): the most elements in motion in any 50 ms slot, and how many move at all.
    The 1/3 rule (LottieFiles): with 3+ elements, no more than a third moving at once."""
    spans, total = [], 0
    for b in beats:
        n = b.get("n", 1) if isinstance(b.get("sel"), list) else 1
        order = b.get("order")
        for i in range(n):
            s = b["at"] + (order[i] if order and i < len(order) else i) * b.get("stagger", 0)
            spans.append((s, s + b["dur"]))
        total += n
    if not spans:
        return 0, 0
    end = max(e for _, e in spans)
    peak, t = 0, 0.0
    while t <= end:
        peak = max(peak, sum(1 for s, e in spans if s <= t < e))
        t += slot
    return peak, total


def build_spec(classified, pack_motion, file, template, body_hash, emphasis_text=None,
               slide_override=None, want_steps=False, slide_n=0, prev_choices=None, variety=None, hero=False,
               link=None):
    """Order, time and name the beats. Returns the per-slide spec dict.
    `prev_choices` ({role: effect} from the previous slide) is updated in place so the
    rotation remembers what the deck just did. `link` is the narrative's connective to the
    previous slide (and-also | therefore | but | proof | new-act): it picks the cut in."""
    m = pack_motion
    lang = language_of(m)
    variety = variety or m.get("variety", "rotate")
    prev_choices = prev_choices if prev_choices is not None else {}
    durs = m.get("durationMs") or {}
    d = {k: (durs.get(k, v) or v) / 1000.0 for k, v in (("fast", 300), ("base", 450), ("slow", 700))}
    role_effects = m.get("roleEffects") or {}
    allowed = set(m.get("allowedEffects") or [])
    level = (slide_override.get("level") if slide_override else None) or m.get("level", "auto")
    cinematic = level == "cinematic"
    budget_ms = int(m.get("entranceBudgetMs", 1600))
    if cinematic:
        budget_ms = int(budget_ms * float(m.get("cinematicBudgetFactor", 1.4)))
    stagger_cap = int(m.get("staggerCapMs", 500)) / 1000.0
    transition_in = None
    overrides = m.get("templateOverrides") or {}
    stem = template or ""
    for key in (stem, re.sub(r"-(focal|asymmetric|compact|enhanced|featured|minimal|dark|classic|panel)$", "", stem)):
        if key and isinstance(overrides.get(key), dict):
            o = overrides[key]
            budget_ms = int(o.get("budgetMs", budget_ms))
            if cinematic and "budgetMs" in o:
                budget_ms = int(budget_ms * float(m.get("cinematicBudgetFactor", 1.4)))
            transition_in = o.get("transition_in", transition_in)
            break
    slide_override = slide_override or {}
    # The cut in carries the argument (iart presentation-video): slide override > the narrative's
    # connective to the previous slide > the template's override > the deck default. The first
    # slide has nothing before it, so a Link there is ignored.
    link_key = re.sub(r"[\s_]+", "-", str(link or "").strip().lower())
    link_used = link_key if link_key in LINK_TRANSITIONS and int(slide_n or 0) > 1 else None
    if link_used:
        transition_in = LINK_TRANSITIONS[link_used]
    if slide_override.get("transition_in"):
        transition_in = slide_override["transition_in"]

    regions = [r for r in classified.get("regions", []) if r.get("sel")]
    # order: tier, then row (24 px tolerance), then x
    def key(r):
        b = r.get("box") or {}
        return (TIER.get(r["role"], 4), round((b.get("y", 0)) / 24.0), b.get("x", 0))
    regions.sort(key=key)
    # An ordinal label ("01", "6", a bare step number) is not a statistic: it never counts and
    # never grows — it appears as a mark, one after another, after its card (Roman liked the
    # numbers arriving one by one). Only a quantity counts up.
    regions = [dict(r, ordinal=True) if r["role"] == "kpi" and _is_ordinal(r.get("text")) else r for r in regions]
    bars = [r for r in regions if r["role"] == "bar" and r.get("box")]
    horizontal_bars = False
    if len(bars) >= 2:
        xs = {round(b["box"]["x"]) for b in bars}
        ws = {round(b["box"]["w"]) for b in bars}
        horizontal_bars = len(xs) <= 2 and len(ws) > 1          # left-aligned bars of varying width
        x0 = min(b["box"]["x"] for b in bars)
        for r in regions:   # an outlined box aligned with the bars (the reference bar) is read with them
            if r["role"] == "svg-card" and not isinstance(r.get("sel"), list) and r.get("box") and abs(r["box"]["x"] - x0) < 6:
                r["role"] = "bar"
        regions.sort(key=key)
    regions = merge_beats(regions, int(m.get("maxBeats", MAX_BEATS)))
    paired = pair_columns(regions)       # column by column — unless that turns a tidy plan into noise
    if len(paired) <= int(m.get("maxBeats", MAX_BEATS)):
        regions = paired
    if bars:   # in a bar chart the marker lines and arrows come after the bars they annotate
        regions.sort(key=lambda r: (6.5 if r["role"] == "connector" else TIER.get(r["role"], 4), round((r.get("box") or {}).get("y", 0) / 24.0), (r.get("box") or {}).get("x", 0)))

    beats = []
    chosen, boxes = {}, {}
    # One motion language per deck (1.6.0): the personality fixes the arrival ease, the hero
    # ease and the base unit; variety lives in effect, direction and stagger origin. Craft rules
    # kept from 1.5.x: out-eases only, speed carries weight (hero 0.5–0.8 s, structure 0.3–0.5,
    # details 0.15–0.3), a group's build window stays under 0.5 s, the hero is on screen by
    # 0.5 s, nothing starts at t = 0. Entrance–exit continuity: the transition that brought the
    # slide in decides where its elements come from; otherwise directions rotate per slide.
    k_base = lang["baseMs"] / 400.0
    n_kpi = sum(1 for r in regions if r["role"] == "kpi" and not r.get("ordinal"))
    scheme = TRANSITION_SCHEMES.get(transition_in or "") or DIRECTION_SCHEMES[int(slide_n or 0) % len(DIRECTION_SCHEMES)]
    for i, r in enumerate(regions):
        role = r["role"]
        eff_role = "hero-title" if (hero and role == "title" and role_effects.get("hero-title")) else role
        effect = chosen.get(role) or pick_effect(role_effects, eff_role, slide_n, prev_choices.get(eff_role), variety)
        if effect in HTML_ONLY_EFFECTS and (role.startswith("svg") or "svg" in str(r.get("sel"))):
            effect = "fade-up"
        # The word waterfall (binary opacity, words pop into place) is a title-card gesture: on a
        # long, wrapping title the not-yet-arrived words read as holes in the sentence. Long titles
        # rise line by line through a mask (the calmest headline reveal); a slam becomes a snap.
        words_n = len((r.get("text") or "").split())
        if role == "title" and words_n > 8:
            if effect in ("words", "words-mask"):
                effect = "lines-mask" if "lines-mask" in allowed else "words-mask"
            elif effect == "slam":
                effect = "snap"
        if role == "bar" and effect == "grow-y":
            bx = r.get("box") or {}
            if horizontal_bars or bx.get("w", 0) > 2 * max(1, bx.get("h", 1)):
                effect = "grow-x" if "grow-x" in allowed else effect      # horizontal bars grow from their left edge
        if effect == "wipe-up" and "wipe-down" in allowed:
            bxs = _boxes_of(r) or ([r["box"]] if r.get("box") else [])
            if bxs and min(b["h"] for b in bxs) > 150:
                effect = "wipe-down"                                    # a block of several lines is read top to bottom: it reveals downward
        if r.get("ordinal") and effect == "count-up":
            effect = ("spring" if lang["textScale"] else "whip") if ("whip" in allowed) else "fade-up"
        if effect not in allowed:
            effect = "fade"
        chosen[eff_role] = effect
        n = r.get("n", 1) if isinstance(r.get("sel"), list) else 1
        if cinematic:
            dur = CINEMATIC_DUR.get(role, 0.4) * k_base
        else:
            dur = d[ROLE_DUR.get(role, "base")]
        if role == "kpi" and effect == "count-up" and n_kpi >= 3:
            dur = min(dur, 0.9 * k_base)      # three or more counters settle faster so they can run one after another
        stagger = 0.0
        if n > 1:
            stagger = min(lang["staggerMs"] / 1000.0, min(stagger_cap, 0.5) / n) if cinematic else min(0.12, stagger_cap / n)
            if role == "card" and n <= 4 and _vertical(r):
                stagger = 0.6                                 # a short vertical stack of cards: one card, its content, then the next (Roman)
                budget_ms += int((stagger - 0.06) * (n - 1) * 1000)
            elif role == "card" and n <= 4:
                stagger = min(0.25, 0.75 / max(1, n - 1))
            elif role == "bar":
                stagger = min(0.18, 0.7 / max(1, n - 1))      # bars one by one, top to bottom
        beat = {"id": f"b{i + 1}", "role": role, "sel": r["sel"], "effect": effect,
                "at": 0.0, "dur": round(dur, 3)}
        if n > 1:
            beat["stagger"] = round(stagger, 3)
            beat["n"] = n
            order = member_order(r)
            if order:
                beat["order"] = order
        if cinematic:
            if role in ("card", "svg-card", "image"):
                beat["parallax"] = True
                beat["dist"] = int(m.get("distancePx", 24) * 1.6)
                if n > 1 and _vertical(r):
                    # stacked cards: the travel must fit the gap, or the next card rises through the
                    # one above it (seen on a 22 px gap with 55 px of parallax travel)
                    bxs = sorted(_boxes_of(r) or [], key=lambda b: b["y"])
                    gaps = [bxs[k + 1]["y"] - (bxs[k]["y"] + bxs[k]["h"]) for k in range(len(bxs) - 1)]
                    gap = min(gaps) if gaps else 24
                    beat["parallax"] = False
                    beat["dist"] = int(max(6, min(beat["dist"], gap * 0.7)))
                beat["dir"] = scheme["card"]
                beat["ease"] = lang["ease"]
                if n > 1 and "order" not in beat and not _vertical(r):
                    beat["from"] = scheme["from"]            # centre-out / edges-in only on a horizontal row; a stack reads top to bottom
                if role == "card" and m.get("followThrough", True):
                    beat["followThrough"] = True     # the card's content settles a beat after its container
            elif role in ("list-item", "row", "text", "svg-text"):
                beat["dir"] = scheme["text"]
                beat["ease"] = lang["ease"]
                if role in ("list-item", "row") and effect == "whip":
                    beat["weight"] = "normal"
            elif role in ("eyebrow", "subtitle"):
                beat["ease"] = lang["ease"]
            elif role == "title":
                beat["dist"] = int(m.get("distancePx", 24) * 1.3)
                beat["ease"] = lang["hero"]
                if effect == "snap":
                    beat["dir"] = "left" if (int(slide_n or 0) % 2) else "right"
        if r.get("text"):
            beat["text"] = r["text"][:80]
        if r.get("col"):
            beat["col"] = r["col"]
        boxes[beat["id"]] = r.get("box")
        beats.append(beat)

    t0 = 0.15 if cinematic else 0.0
    overlap = (0.5, 0.35) if cinematic else (0.7, 0.5)
    retime(beats, overlap, t0)
    # the 1/3 rule: when more than a third of the animated elements would move at once, the
    # waterfall loosens (less overlap) before the budget fitter shortens anything
    peak, moving = concurrency(beats)
    # (the factor is the share of the previous beat that plays before the next one starts, so
    # loosening RAISES it: 0.5 → 0.75 → 1.0, i.e. the next beat waits for the previous to land)
    loose, rounds = overlap, 0
    while beats and peak > max(4, -(-moving // 3)) and rounds < 3:
        loose = (min(1.2, loose[0] + 0.25), min(1.2, loose[1] + 0.25))
        retime(beats, loose, t0)
        peak, moving = concurrency(beats)
        rounds += 1
    # a number is read after it has settled: the caption directly under a counted KPI lands
    # when the count is done, not while the digits are still moving
    for kb in [b for b in beats if b["role"] == "kpi" and b["effect"] == "count-up" and boxes.get(b["id"])]:
        for tb in [b for b in beats if b["role"] in ("text", "subtitle") and boxes.get(b["id"])]:
            if _below(boxes[kb["id"]], boxes[tb["id"]]) and tb["at"] < kb["at"] + kb["dur"] * 0.85:
                tb["at"] = round(kb["at"] + kb["dur"] * 0.85, 3)

    # emphasis — explicit attribute > deck-state override > brief text > loudest number
    emph_sel, emph_from = None, None
    if classified.get("explicitEmphasis"):
        emph_sel, emph_from = classified["explicitEmphasis"], "data-motion"
    elif slide_override.get("emphasis_sel"):
        emph_sel, emph_from = slide_override["emphasis_sel"], "deck-state"
    elif emphasis_text:
        # Labels are never the eye-landing element: eyebrows, captions and small SVG labels are
        # excluded; among the rest the brief's sentence is matched by word overlap, ties going to
        # the larger type (a title or a number beats a body line).
        LABEL_ROLES = {"eyebrow", "connector", "arc", "bar", "image", "chartBlock"}
        def is_label(a):
            return a.get("role") in LABEL_ROLES or (a.get("role") == "svg-text" and float(a.get("fontPx") or 0) < 22)
        cands = [{"sel": b["sel"], "text": b.get("text"), "role": b["role"]}
                 for b in beats if not isinstance(b["sel"], list) and b["role"] not in LABEL_ROLES]
        font_of = {a["sel"]: a.get("fontPx", 0) for a in classified.get("allText", [])}
        cands += [{"sel": a["sel"], "text": a["text"], "role": a.get("role")} for a in classified.get("allText", [])
                  if not is_label(a) and a["sel"] not in {c["sel"] for c in cands}]
        emph_sel = match_emphasis(emphasis_text, cands, font_of)
        emph_from = "brief" if emph_sel else None
    if not emph_sel and classified.get("loudest"):
        emph_sel, emph_from = classified["loudest"], "loudest"
    if emph_sel and beats and not lang["textScale"]:
        # The point is made by ORDER and STILLNESS, never by a gesture on a landed element (corporate /
        # premium): the focal element's own arrival is moved to the end, after a hold of stillness.
        # Titles keep their place (the hero must be on screen by 0.5 s): their point is the hold.
        own_beat = next((b for b in beats if b["sel"] == emph_sel), None)
        host = next((b for b in beats if isinstance(b["sel"], list) and emph_sel in b["sel"]), None)
        if own_beat and own_beat["role"] not in ("title", "eyebrow", "subtitle", "row"):
            beats.remove(own_beat)
            own_beat["at"] = round(max(b["at"] + _span(b) for b in beats) + lang["holdMs"] / 1000.0, 3)
            beats.append(own_beat)
            budget_ms += int(lang["holdMs"])
            chosen["emphasis"] = "last"
        elif host and host.get("n", 0) > 2 and host["role"] in ("card", "list-item", "text", "kpi", "svg-card"):
            k = host["sel"].index(emph_sel)
            host["sel"] = [x for x in host["sel"] if x != emph_sel]
            host["n"] = len(host["sel"])
            if host.get("order") and len(host["order"]) > k:
                host["order"] = [o for i, o in enumerate(host["order"]) if i != k]
            last = {kk: vv for kk, vv in host.items() if kk not in ("n", "stagger", "order", "from", "id")}
            last.update({"id": f"b{len(beats) + 1}", "sel": emph_sel, "dur": round(host["dur"] * 1.3, 3)})
            last["at"] = round(max(b["at"] + _span(b) for b in beats) + lang["holdMs"] / 1000.0, 3)
            beats.append(last)
            budget_ms += int(lang["holdMs"])
            chosen["emphasis"] = "last"
        else:
            chosen["emphasis"] = "hold"
    elif emph_sel and beats:
        eff = pick_effect(role_effects, "emphasis", slide_n, prev_choices.get("emphasis"), variety, fallback="settle")
        if eff == "focus-pull" and len(beats) < 3:
            eff = "lift"
        if eff in allowed:
            chosen["emphasis"] = eff
            # the point comes AFTER the last beat has landed, plus a reading beat of stillness
            # (hold discipline) — never over an arrival. The hold is not construction time: it
            # is added to the budget rather than squeezed out of it.
            at = max(b["at"] + _span(b) for b in beats) + lang["holdMs"] / 1000.0
            budget_ms += int(lang["holdMs"])
            beats.append({"id": f"b{len(beats) + 1}", "role": "emphasis", "sel": emph_sel, "effect": eff,
                          "at": round(at, 3), "dur": round((CINEMATIC_DUR["emphasis"] * k_base) if cinematic else d["base"], 3)})
    prev_choices.update(chosen)

    # fit the budget: scale start times (durations keep a floor) until total ≤ budget; the
    # floor can keep a dense slide over, so finish by sliding late beats back onto the budget
    def total(bs):
        return max((b["at"] + _span(b)) for b in bs) if bs else 0.0
    tot = total(beats)
    budget = budget_ms / 1000.0
    rounds = 0
    while tot > budget and beats and rounds < 4:
        k = budget / tot
        for b in beats:
            b["at"] = round(b["at"] * k, 3)
            b["dur"] = round(max(0.2, b["dur"] * k), 3)
            if "stagger" in b:
                b["stagger"] = round(b["stagger"] * k, 3)
        tot = total(beats)
        rounds += 1
    if tot > budget:
        for b in beats:
            if b["at"] + _span(b) > budget:
                b["at"] = round(max(0.0, budget - _span(b)), 3)
                if _span(b) > budget:   # a single huge group: shrink its stagger, then its duration
                    if "stagger" in b and b.get("n", 1) > 1:
                        b["stagger"] = round(max(0.0, (budget - b["dur"]) / (b["n"] - 1)), 3)
                    if _span(b) > budget:
                        b["dur"] = round(max(0.12, budget - b.get("stagger", 0) * max(0, b.get("n", 1) - 1)), 3)
        tot = total(beats)
    if beats:
        peak, moving = concurrency([b for b in beats if b["role"] != "emphasis"])

    steps = []
    if want_steps:
        # Build-ins: every group beat (cards, list items, text blocks) and every data beat waits
        # for a keypress; the title tier plays on arrival. One step per such beat.
        for b in beats:
            if b["role"] in ("card", "list-item", "text", "kpi", "bar", "arc", "chartBlock", "image"):
                steps.append({"id": f"s{len(steps) + 1}", "beats": [b["id"]]})

    # idle motion (cinematic): camera toward the emphasis (else the title), drift on the washes
    idle = []
    idle_cfg = m.get("idle") or {}
    if cinematic and idle_cfg:
        # ONE ambient motion per scene ("don't use the same ambient zoom on every scene"), rotating
        # camera push → drift (when the slide has washes) → a slower, smaller push → stillness.
        cam = idle_cfg.get("camera") if isinstance(idle_cfg.get("camera"), dict) else {}
        drift = idle_cfg.get("drift") if isinstance(idle_cfg.get("drift"), dict) else {}
        focus_sel = emph_sel or next((b["sel"] for b in beats if b["role"] == "title" and not isinstance(b["sel"], list)), None)
        targets = []
        for s_ in (drift.get("selectors") or []):
            targets += (classified.get("driftTargets") or {}).get(s_, [])
        mode = ["camera", "drift", "camera-slow", "still"][int(slide_n or 0) % 4]
        if mode == "drift" and not (targets and drift.get("enabled", True)):
            mode = "camera"
        if mode in ("camera", "camera-slow") and cam.get("enabled", True) and focus_sel:
            idle.append({"effect": "camera", "sel": focus_sel,
                         "scale": cam.get("scale", 1.035) if mode == "camera" else 1 + (cam.get("scale", 1.035) - 1) * 0.6,
                         "dur": cam.get("durationMs", 7000) if mode == "camera" else int(cam.get("durationMs", 7000) * 1.4)})
        elif mode == "drift":
            idle.append({"effect": "drift", "sel": targets, "px": drift.get("px", 18), "rot": drift.get("rot", 1.5), "dur": drift.get("durationMs", 9000)})
        breathe = idle_cfg.get("breathe")
        if isinstance(breathe, dict) and breathe.get("enabled", False) and emph_sel and mode == "still":
            idle.append({"effect": "breathe", "sel": emph_sel, "scale": breathe.get("scale", 1.015), "dur": breathe.get("durationMs", 4000)})

    return {
        "v": 1, "file": file, "template": template, "body_hash": body_hash, "engine": ENGINE_VERSION,
        "level": level, "idle": idle,
        "budget_ms": budget_ms, "total_ms": int(round(tot * 1000)), "transition_in": transition_in, "link": link_used,
        "language": lang["name"],
        "easing": {"in": lang["ease"], "hero": lang["hero"], "move": lang["move"],
                   "transition": (m.get("easing") or {}).get("transition", "power2.inOut")},
        "scale": {"in": lang["scaleIn"], "hero": lang["heroScale"], "textScale": bool(lang["textScale"])},
        "distancePx": m.get("distancePx", 24), "gsapUrl": m.get("gsapUrl"),
        # dark slides read brighter on a projector: travel and defocus scale down (LottieFiles)
        "intensity": 0.85 if classified.get("dark") else 1,
        "blur": m.get("blur", "subtle"), "focusPull": m.get("focusPull", "on"),
        "peak_moving": peak, "moving": moving,
        "never": list((m.get("roleSelectors") or {}).get("never") or []),
        "emphasis": {"sel": emph_sel, "from": emph_from} if emph_sel else None,
        "effects": chosen,
        "beats": beats, "steps": steps,
    }

# ── file I/O ─────────────────────────────────────────────────────────────────

def body_hash(html):
    m = BODY_RE.search(html)
    region = m.group(0) if m else html
    return "sha256:" + hashlib.sha256(region.encode("utf-8")).hexdigest()[:32]


def block_for(spec, gsap_url):
    payload = json.dumps(compact_spec(spec), ensure_ascii=False, separators=(",", ":"))
    payload = payload.replace("</", "<\\/")   # never close our own tag early
    return (f'<script id="{SPEC_ID}" type="application/json">{payload}</script>\n'
            f'<script id="{RUNTIME_ID}" src="motion/motion.js" data-gsap="{gsap_url}"></script>\n')


def strip_block(html):
    return BLOCK_RE.sub("", html)


def read_spec(html):
    m = re.search(r'<script id="' + SPEC_ID + r'"[^>]*>(.*?)</script>', html, re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(1).replace("<\\/", "</"))
    except ValueError:
        return None


def inject(path, spec, gsap_url):
    src = open(path, encoding="utf-8").read()
    stripped = strip_block(src)
    idx = stripped.lower().rfind("</head>")
    if idx < 0:
        return "SKIPPED (no </head>)"
    out = stripped[:idx] + block_for(spec, gsap_url) + stripped[idx:]
    if out == src:
        return "unchanged"
    with open(path, "w", encoding="utf-8") as f:
        f.write(out)
    return "replaced" if BLOCK_RE.search(src) else "inserted"


INDEX_CFG_RE = re.compile(r"(window\.__DECK\s*=\s*)(\{.*?\})(;\s*\n)", re.DOTALL)


def write_index_transitions(deck_dir, transitions):
    """Per-slide transitions live in the pack's templateOverrides, which only choreograph.py
    resolves; the viewer reads them from window.__DECK in index.html (no fetch — file:// has
    none). assemble_deck.py leaves an empty map; this fills it, idempotently."""
    p = os.path.join(deck_dir, "index.html")
    if not os.path.isfile(p):
        return
    src = open(p, encoding="utf-8").read()
    m = INDEX_CFG_RE.search(src)
    if not m:
        return
    try:
        cfg = json.loads(m.group(2))
    except ValueError:
        return
    cfg["transitions"] = transitions
    out = src[:m.start(2)] + json.dumps(cfg, ensure_ascii=False) + src[m.end(2):]
    if out != src:
        open(p, "w", encoding="utf-8").write(out)


def load_state(deck_dir):
    p = os.path.join(deck_dir, "deck-state.json")
    try:
        return json.load(open(p, encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def deck_motion(state, deck_dir):
    m = state.get("motion")
    if isinstance(m, dict):
        return m
    # brief fallback — same reading assemble_deck.py does
    try:
        from assemble_deck import parse_motion_line
        return parse_motion_line(os.path.join(deck_dir, "deck-brief.md")) or {"enabled": False}
    except Exception:
        return {"enabled": False}


def brief_field(deck_dir, field):
    """{n: text} of one `Field:` line per slide brief in narrative-outline.md, when it exists."""
    out = {}
    p = os.path.join(deck_dir, "narrative-outline.md")
    if not split_outline or not os.path.isfile(p):
        return out
    _, briefs, _ = split_outline(open(p, encoding="utf-8").read())
    pat = re.compile(r"^\s*[-*]?\s*\**" + re.escape(field) + r":?\**\s*(.+)$", re.I)
    for n, lines in briefs.items():
        for line in lines:
            m = pat.match(line)
            if m:
                out[n] = m.group(1).strip()
                break
    return out


def emphasis_by_slide(deck_dir):
    """{n: 'Emphasis: …' text} from narrative-outline.md."""
    return brief_field(deck_dir, "Emphasis")


def links_by_slide(deck_dir):
    """{n: 'Link: …'} — the logical connective to the previous slide (and-also | therefore | but |
    proof | new-act); the first word of the line is what counts."""
    out = {}
    for n, v in brief_field(deck_dir, "Link").items():
        w = re.split(r"[\s(—–:,.]+", v.strip().lower().replace("_", "-"), 1)[0]
        if w in LINK_TRANSITIONS:
            out[n] = w
    return out


def slide_number(name):
    m = re.match(r"^(\d{2})-", name)
    return int(m.group(1)) if m else None


def summary_lines(manifest):
    out = []
    lang = manifest.get("language")
    if isinstance(lang, dict):
        out.append(f"language: {lang.get('name')} · ease {lang.get('ease')} · hero {lang.get('hero')} · move {lang.get('move')}"
                   f" · base {lang.get('baseMs')} ms · hold {lang.get('holdMs')} ms · stagger {lang.get('staggerMs')} ms")
    for s in manifest.get("slides", []):
        e = s.get("emphasis") or {}
        beats = s.get("beats", [])
        roles = ",".join(f"{b['role']}" + (f"×{b['n']}" if b.get("n") else "") + f":{b['effect']}" for b in beats)
        idle = ",".join(b["effect"] for b in s.get("idle") or [])
        if s.get("scene"):
            idle = f"{idle or '-'}  SCENE={s['scene']}"
        out.append(f"{s['file']:34s} {s.get('template') or '?':30s} {len(beats):2d} beats {s.get('total_ms', 0):5d} ms"
                   f"{'  steps ' + str(len(s.get('steps', []))) if s.get('steps') else ''}"
                   f"  in={s.get('transition_in') or 'deck'}{'/' + s['link'] if s.get('link') else ''}"
                   f"  moving={s.get('peak_moving', '-')}/{s.get('moving', '-')}  idle={idle or '-'}  emphasis={e.get('from') or '-'}  [{roles}]")
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.strip().split("\n")[0])
    ap.add_argument("--deck-dir", default=None)
    ap.add_argument("--files", nargs="*", default=None, help="Slide files (default: deck-state slides[])")
    ap.add_argument("--dry-run", action="store_true", help="Plan only; write nothing")
    ap.add_argument("--json", action="store_true", help="Print the specs as JSON")
    ap.add_argument("--strip", action="store_true", help="Remove the injected block from the slides")
    ap.add_argument("--check", action="store_true", help="Exit 1 if any injected spec is stale (body changed)")
    ap.add_argument("--summary", action="store_true", help="One line per slide from motion/motion.json")
    ap.add_argument("--stats", action="store_true", help="Print browser launches / timings on stderr")
    ap.add_argument("--steps", action="store_true", help="Force build-in steps on (default: deck-state motion.steps)")
    ap.add_argument("--design-system", default=None)
    args = ap.parse_args()

    deck_dir = os.path.abspath(args.deck_dir) if args.deck_dir else None
    if not deck_dir and not args.files:
        sys.exit("error: pass --deck-dir D, or --files … with --dry-run")
    if deck_dir and not os.path.isdir(deck_dir):
        sys.exit(f"error: no such deck dir: {deck_dir}")

    state = load_state(deck_dir) if deck_dir else {}
    motion_dir = os.path.join(deck_dir, "motion") if deck_dir else None
    manifest_path = os.path.join(motion_dir, "motion.json") if motion_dir else None

    # files
    if args.files:
        files = [os.path.abspath(f) for f in args.files]
    else:
        files = [os.path.join(deck_dir, s["file"]) for s in sorted(state.get("slides", []), key=lambda s: s.get("n", 0)) if s.get("file")]
        if not files:
            files = sorted(p for p in glob.glob(os.path.join(deck_dir, "*.html")) if SLIDE_RE.match(os.path.basename(p)))
    missing = [f for f in files if not os.path.isfile(f)]
    if missing:
        sys.exit("error: no such file: " + ", ".join(missing))

    if args.summary:
        if not manifest_path or not os.path.isfile(manifest_path):
            sys.exit("no motion/motion.json — run choreograph.py --deck-dir D first (or motion is disabled)")
        for line in summary_lines(json.load(open(manifest_path, encoding="utf-8"))):
            print(line)
        return 0

    if args.strip:
        n = 0
        for f in files:
            src = open(f, encoding="utf-8").read()
            out = strip_block(src)
            if out != src:
                open(f, "w", encoding="utf-8").write(out); n += 1
        if manifest_path and os.path.isfile(manifest_path):
            os.remove(manifest_path)
        print(f"stripped motion block from {n} slide(s)")
        return 0

    if args.check:
        stale, clean = [], 0
        for f in files:
            html = open(f, encoding="utf-8").read()
            spec = read_spec(html)
            if not spec:
                continue
            if spec.get("body_hash") != body_hash(html):
                stale.append(os.path.basename(f))
            else:
                clean += 1
        if stale:
            print("STALE motion spec (body changed since choreography): " + ", ".join(stale))
            print(f"re-run: choreograph.py --deck-dir D --files {' '.join(stale)}")
            return 1
        print(f"motion specs current on {clean} slide(s)")
        return 0

    # gating — the §1 decision, then the pack
    dm = deck_motion(state, deck_dir) if deck_dir else {"enabled": True}
    if deck_dir and os.path.isfile(os.path.join(deck_dir, "deck-state.json")) and not dm.get("enabled") and not args.dry_run:
        print("motion disabled for this deck (deck-state.json motion.enabled is not true) — nothing to do")
        return 0
    ds = load(args.design_system, deck_dir=deck_dir)
    if not ds.motion_enabled():
        print(f"pack {ds.name} declares no `motion` block — nothing to do")
        return 0
    pack_m = ds.motion()
    want_steps = bool(args.steps or dm.get("steps"))
    emph = emphasis_by_slide(deck_dir) if deck_dir else {}
    links = links_by_slide(deck_dir) if deck_dir else {}
    per_slide = {s.get("file"): (s.get("motion") or {}) for s in state.get("slides", []) if isinstance(s, dict)}

    params = {
        "canvas": list(ds.canvas),
        "roleSelectors": {k: v for k, v in (pack_m.get("roleSelectors") or {}).items() if not str(k).startswith("$") and k != "never"},
        "neverSelectors": (pack_m.get("roleSelectors") or {}).get("never", []),
        "chromeZonePx": int(pack_m.get("chromeZonePx", 100)),
        "driftSelectors": ((pack_m.get("idle") or {}).get("drift") or {}).get("selectors", []),
    }

    from playwright.sync_api import sync_playwright
    import time
    t0 = time.time()
    specs, results = [], []
    prev_choices = {}
    director = load_director(deck_dir)
    variety = dm.get("variety") if isinstance(dm.get("variety"), str) else None
    # hero slides (cover, dividers/breathers, closing) take the hero-title gestures (slam, snap…)
    hero_roles = {k: v for k, v in (ds.get("templateRoles") or {}).items()
                  if k in ("cover", "breather", "closing") and isinstance(v, list)}
    if isinstance(dm.get("level"), str):
        pack_m = dict(pack_m, level=dm["level"])
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": ds.canvas[0], "height": ds.canvas[1]})
        for f in files:
            name = os.path.basename(f)
            html = open(f, encoding="utf-8").read()
            override = per_slide.get(name) or {}
            if override.get("enabled") is False:
                if not args.dry_run and BLOCK_RE.search(html):
                    open(f, "w", encoding="utf-8").write(strip_block(html))
                results.append(f"{name}: motion off for this slide (deck-state override)")
                continue
            page.goto("file://" + f + "?static=1", wait_until="networkidle")
            page.evaluate("document.fonts.ready || Promise.resolve()")
            page.wait_for_timeout(350)
            classified = page.evaluate(CLASSIFY_JS, params)
            if classified.get("error"):
                results.append(f"{name}: {classified['error']}")
                continue
            n = slide_number(name)
            stem = classified.get("template") or ""
            base = re.sub(r"-(focal|asymmetric|compact|enhanced|featured|minimal|dark|classic|panel|left)$", "", stem)
            hero = any(stem in v or base in v for k, v in hero_roles.items())
            spec = build_spec(classified, pack_m, name, classified.get("template"), body_hash(strip_block(html)),
                              emphasis_text=emph.get(n), slide_override=override, want_steps=want_steps,
                              slide_n=n if n is not None else len(specs) + 1, prev_choices=prev_choices, variety=variety,
                              hero=hero, link=links.get(n))
            scene = director.get(name)
            if isinstance(scene, dict) and scene.get("beats"):
                resolved = page.evaluate(RESOLVE_JS, scene_selectors(scene))
                missing = [k for k, v in resolved.items() if not v]
                if missing:
                    results.append(f"{name}: director scene — {len(missing)} selector(s) resolve to nothing: {', '.join(missing[:3])}")
                spec = apply_scene(spec, scene, resolved, (pack_m.get("durationMs") or {}).get("base", 450) / 1000.0)
            specs.append(spec)
            if not args.dry_run:
                what = inject(f, spec, pack_m.get("gsapUrl"))
                results.append(f"{name}: {what} — {len(spec['beats'])} beats, {spec['total_ms']} ms"
                               f"{', emphasis via ' + spec['emphasis']['from'] if spec.get('emphasis') else ''}")
            else:
                results.append(f"{name}: {len(spec['beats'])} beats, {spec['total_ms']} ms (dry run)")
        browser.close()

    if not args.dry_run and deck_dir:
        os.makedirs(motion_dir, exist_ok=True)
        shutil.copyfile(RUNTIME_SRC, os.path.join(motion_dir, "motion.js"))
        manifest = {"v": 1, "engine": ENGINE_VERSION, "deck": state.get("deck"), "language": language_of(pack_m),
                    "transition": {**(pack_m.get("transition") or {}), **({"type": dm["transition"]} if isinstance(dm.get("transition"), str) else {})},
                    "steps": want_steps, "slides": specs}
        if manifest_path and os.path.isfile(manifest_path):
            # keep specs of slides not re-choreographed this run (--files subset)
            try:
                old = json.load(open(manifest_path, encoding="utf-8"))
                done = {s["file"] for s in specs}
                manifest["slides"] = sorted([s for s in old.get("slides", []) if s["file"] not in done] + specs,
                                            key=lambda s: s["file"])
            except (OSError, ValueError):
                pass
        manifest["transitions"] = {s["file"]: s["transition_in"] for s in manifest["slides"] if s.get("transition_in")}
        json.dump(manifest, open(manifest_path, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
        write_index_transitions(deck_dir, manifest["transitions"])

    if args.json:
        print(json.dumps({"slides": specs}, indent=1, ensure_ascii=False))
    else:
        for r in results:
            print(r)
        if not args.dry_run and deck_dir:
            print(f"wrote {manifest_path}; runtime motion/motion.js")
    if args.stats:
        print(f"browser_launches=1 files={len(files)} seconds={time.time() - t0:.1f}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
