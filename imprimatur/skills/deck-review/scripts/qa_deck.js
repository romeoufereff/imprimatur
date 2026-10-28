// In-browser QA for a FOREIGN deck: one HTML file holding every slide (an interactive
// presentation someone else built), not an imprimatur NN-*.html folder. The imprimatur
// render checks need one slide per file inside #slide; this runs the same lessons on any
// slide engine. Driven by qa_deck.py, or by hand in the browser console:
//
//   eval(await (await fetch('/qa_deck.js?' + Date.now())).text());
//   __qa.configure({ slide: '.slide', hash: '#slide={n}', reveal: [['.reveal', 'shown']],
//                    footer: '.zoom-strip', minFont: 13.5 });
//   await document.fonts.ready; r = await __qa.runSlides(['fit', 'svg', 'bars', 'rows', 'pad', 'minfont']);
//
// Every rule below is one a 2026-10-26 restyle review learned the hard way:
//   · a "box" has a fill or borders on 3+ sides — a one-sided border is a rule, not a box;
//   · screen-reader-only text is never measured;
//   · the freeze beats a deck's own `!important` transitions (four ids in :not()), and
//     running CSS animations are finished — otherwise the check measures mid-fade;
//   · every <details> is opened before measuring;
//   · text is checked against the footer row and against the slide edge;
//   · connectors are tested at every point, endpoints included, against the full glyph band
//     (a 2 px inset missed a route starting in a descender), unless an opaque box or shape
//     painted above the line hides it there;
//   · arrow tips: buried in their node, or a near miss; nothing ahead = a deliberate exit;
//   · connector strokes need 3:1 against what is behind them;
//   · a coloured stripe on one edge of a card (left bar, 3px top stripe) is not a pack card;
//   · cards in one row end level (a grid stretches the wrapper, not the card inside it);
//   · text keeps clear of a rounded card's edge;
//   · the smallest rendered text accounts for SVG and CSS transforms.
// Distances are in the deck's own stage px (the slide's layout width), so a deck scaled
// to fit the window measures the same as one at 100 %.
window.__qa = {};
__qa.cfg = {
  slide: '.slide',                 // every slide
  active: null,                    // the slide on show; default: `${slide}.active`, else the most visible one
  hash: null,                      // navigation, e.g. '#slide={n}' or '#/{i}' ({n} 1-based, {i} 0-based)
  activeClass: 'active',           // used when there is no hash: set on the nth slide, removed from the rest
  reveal: [],                      // [[selector, 'class names to add']] — build steps shown at once
  footer: '[data-qa-footer], footer, .slide-footer',   // the footer row text must stay clear of
  chrome: '.slide-number, [data-qa-chrome]',          // skipped for box spills (page numbers, …)
  minFont: null,                   // stage px floor; qa_deck.py derives it from the pack
  settle: 140,                     // ms after navigating
  buried: 3, float: 12, tol: 2, pad: 8,   // stage px
};
__qa.configure = o => Object.assign(__qa.cfg, o || {});
__qa.FREEZE = 'html body *:not(#_qf0#_qf1#_qf2#_qf3), html body *:not(#_qf0#_qf1#_qf2#_qf3)::before, html body *:not(#_qf0#_qf1#_qf2#_qf3)::after'
  + '{transition-duration:0s!important;transition-delay:0s!important;animation-duration:0s!important;animation-delay:0s!important;animation-iteration-count:1!important}';
__qa.SR = '[class*="sr-only"]:not(.not-sr-only), [class*="visually-hidden"]';
// screen-reader-only by class, or by the pattern itself: an ancestor clipped to a 1 px box (2 px leaves room for a scaled stage)
__qa.hidden = (el, root) => {
  if (el.closest(__qa.SR)) return true;
  for (let e = el; e && e !== root; e = e.parentElement) { const r = e.getBoundingClientRect(), s = getComputedStyle(e);
    if (r.width <= 2 && r.height <= 2 && (s.overflow !== 'visible' || s.clip !== 'auto' || s.clipPath !== 'none')) return true; }
  return false;
};

__qa.parse = c => { const m = (c || '').match(/[\d.]+/g); if (!m || m.length < 3) return null; return [+m[0], +m[1], +m[2], m.length < 4 ? 1 : +m[3]]; };
__qa.alpha = c => { const p = __qa.parse(c); return p ? p[3] : 0; };
__qa.lum = c => { const p = typeof c === 'string' ? __qa.parse(c) : c; const [r, g, b] = p.slice(0, 3).map(v => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); }); return 0.2126 * r + 0.7152 * g + 0.0722 * b; };
__qa.cr = (a, b) => { const x = __qa.lum(a), y = __qa.lum(b); return +(((Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05)).toFixed(2)); };
__qa.sleep = ms => new Promise(r => setTimeout(r, ms));
__qa.frames = () => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));
__qa.slides = () => [...document.querySelectorAll(__qa.cfg.slide)];
__qa.current = () => {
  const c = __qa.cfg, a = c.active ? document.querySelector(c.active) : document.querySelector(c.slide + '.' + c.activeClass);
  if (a) return a;
  const vw = innerWidth, vh = innerHeight, area = e => { const r = e.getBoundingClientRect(); return Math.max(0, Math.min(r.right, vw) - Math.max(r.left, 0)) * Math.max(0, Math.min(r.bottom, vh) - Math.max(r.top, 0)) * (getComputedStyle(e).visibility === 'hidden' ? 0 : 1); };
  return __qa.slides().sort((x, y) => area(y) - area(x))[0];
};
__qa.scale = root => { root = root || __qa.current(); return root.offsetWidth ? root.getBoundingClientRect().width / root.offsetWidth : 1; };
__qa.goto = async n => {
  const c = __qa.cfg;
  if (c.hash) location.hash = c.hash.replace('{n}', n).replace('{i}', n - 1);
  else __qa.slides().forEach((s, i) => s.classList.toggle(c.activeClass, i === n - 1));
  await __qa.sleep(c.settle);
};
__qa.freeze = async root => {
  root = root || __qa.current();
  if (!document.getElementById('qa-freeze')) { const st = document.createElement('style'); st.id = 'qa-freeze'; st.textContent = __qa.FREEZE; document.head.appendChild(st); }
  (__qa.cfg.reveal || []).forEach(([sel, cls]) => root.querySelectorAll(sel).forEach(e => e.classList.add(...cls.split(/\s+/))));
  root.querySelectorAll('details').forEach(d => { d.open = true; });
  for (const a of document.getAnimations()) if (a instanceof CSSAnimation || a instanceof CSSTransition) { try { a.finish(); } catch (e) {} }
  await __qa.frames();
};
__qa.vis = (el, stop) => { for (let e = el; e && e !== stop; e = e.parentElement) { const s = getComputedStyle(e); if (s.display === 'none' || s.visibility === 'hidden' || +s.opacity < 0.05) return false; } return true; };
__qa.sides = s => ['Top', 'Right', 'Bottom', 'Left'].filter(k => parseFloat(s['border' + k + 'Width']) > 0 && !/none|hidden/.test(s['border' + k + 'Style']) && __qa.alpha(s['border' + k + 'Color']) > 0.05);
__qa.filled = s => __qa.alpha(s.backgroundColor) > 0.05 || /gradient|url\(/.test(s.backgroundImage);
__qa.boxed = el => { const s = getComputedStyle(el); return __qa.filled(s) || __qa.sides(s).length >= 3; };
__qa.masks = e => {
  const s = getComputedStyle(e);
  if (__qa.alpha(s.backgroundColor) >= 0.85 || /gradient|url\(/.test(s.backgroundImage)) return true;
  if (e instanceof SVGGeometryElement && !/^(line|polyline)$/.test(e.tagName) && s.fill !== 'none')
    return (parseFloat(s.fillOpacity) || 1) * (parseFloat(s.opacity) || 1) >= 0.85 && (/url\(/.test(s.fill) || __qa.alpha(s.fill) >= 0.85);
  return false;
};
__qa.name = el => { const c = (typeof el.className === 'string' ? el.className : (el.getAttribute('class') || '')).trim().split(/\s+/).filter(x => x).slice(0, 3).join('.');
  return el.tagName.toLowerCase() + (c ? '.' + c : '') + ' "' + (el.innerText || el.textContent || '').trim().replace(/\s+/g, ' ').slice(0, 30) + '"'; };
__qa.toScreen = (el, x, y) => { const p = (el.ownerSVGElement || el).createSVGPoint(); p.x = x; p.y = y; return p.matrixTransform(el.getScreenCTM()); };
__qa.pathPts = (p, step) => { const L = p.getTotalLength(), out = []; for (let t = 0; t < L; t += step) { const q = p.getPointAtLength(t); out.push(__qa.toScreen(p, q.x, q.y)); } const q = p.getPointAtLength(L); out.push(__qa.toScreen(p, q.x, q.y)); return out; };
__qa.lines = root => {
  const out = [], tw = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, { acceptNode: n => n.textContent.trim() && !n.parentElement.closest('script, style, marker, defs, symbol') ? 1 : 2 }); let n;
  while ((n = tw.nextNode())) {
    const el = n.parentElement; if (__qa.hidden(el, root) || !__qa.vis(el, root.parentElement)) continue;
    const rg = document.createRange(); rg.selectNodeContents(n);
    [...rg.getClientRects()].filter(r => r.width > 2 && r.height > 4).forEach(r => out.push({ r, el, txt: n.textContent.trim().replace(/\s+/g, ' ').slice(0, 44) }));
  }
  return out;
};
// probes need hit-testing on overlays that set pointer-events:none
__qa.probe = on => { let st = document.getElementById('qa-probe'); if (on && !st) { st = document.createElement('style'); st.id = 'qa-probe'; st.textContent = '*:not(#_qp0#_qp1#_qp2){pointer-events:auto!important}'; document.head.appendChild(st); } if (!on && st) st.remove(); };

// text in its box, the footer row, the slide edge, text on text, connectors through text
__qa.fit = (root, label) => {
  const c = __qa.cfg, sc = __qa.scale(root), R = v => Math.round(v / sc), F = [], lines = __qa.lines(root);
  lines.forEach(l => {
    if (l.el.closest('svg') || l.el.closest(c.chrome) || l.el.closest(c.footer)) return;
    let box = l.el; while (box && box !== root && !__qa.boxed(box)) box = box.parentElement;
    if (!box || box === root) return;
    const br = box.getBoundingClientRect(), lh = parseFloat(getComputedStyle(l.el).lineHeight), allow = isNaN(lh) ? 0 : Math.max(0, (l.r.height - lh * sc) / 2);
    const ob = Math.max(br.top - l.r.top - allow, l.r.bottom - br.bottom - allow, br.left - l.r.left, l.r.right - br.right);
    if (ob / sc > c.tol) F.push(`${label}: "${l.txt}" spills ${R(ob)}px out of its box`);
  });
  const foot = c.footer ? [...root.querySelectorAll(c.footer)].filter(e => __qa.vis(e, root.parentElement)) : [];
  foot.forEach(f => { const fr = f.getBoundingClientRect(); lines.forEach(l => { if (f.contains(l.el)) return; const o = Math.min(l.r.right, fr.right) - Math.max(l.r.left, fr.left), v = Math.min(l.r.bottom, fr.bottom) - Math.max(l.r.top, fr.top); if (o > 2 && v > 2) F.push(`${label}: "${l.txt}" runs into the footer row (${R(v)}px)`); }); });
  const rr = root.getBoundingClientRect();
  lines.forEach(l => { const ob = Math.max(rr.left - l.r.left, l.r.right - rr.right, rr.top - l.r.top, l.r.bottom - rr.bottom); if (ob > 2) F.push(`${label}: "${l.txt}" leaves the slide by ${R(ob)}px`); });
  const seen = new Set();
  for (let i = 0; i < lines.length; i++) for (let j = i + 1; j < lines.length; j++) {
    const a = lines[i], b = lines[j]; if (a.el === b.el || a.el.contains(b.el) || b.el.contains(a.el)) continue;
    const o = Math.min(a.r.right, b.r.right) - Math.max(a.r.left, b.r.left), v = Math.min(a.r.bottom, b.r.bottom) - Math.max(a.r.top, b.r.top);
    if (o > 2 && v > 3) { const k = a.txt + '|' + b.txt; if (!seen.has(k)) { seen.add(k); F.push(`${label}: text "${a.txt}" collides with "${b.txt}" (${R(o)}x${R(v)}px)`); } }
  }
  __qa.probe(true);
  root.querySelectorAll('svg path, svg line, svg polyline').forEach(p => {
    if (p.closest('marker, defs, symbol, clipPath, mask, pattern') || !p.getTotalLength || !__qa.vis(p, root.parentElement)) return;
    const cs = getComputedStyle(p); if (cs.stroke === 'none' || __qa.alpha(cs.stroke) < 0.05) return;
    if (p.tagName === 'path' && /z\s*$/i.test(p.getAttribute('d') || '') && cs.fill !== 'none') return;
    let L; try { L = p.getTotalLength(); } catch (e) { return; } if (L * sc < 20) return;
    const hit = new Set();
    __qa.pathPts(p, 2).forEach(z => lines.forEach(l => {
      if (hit.has(l.txt) || !(z.x > l.r.left + 0.5 && z.x < l.r.right - 0.5 && z.y > l.r.top + 0.5 && z.y < l.r.bottom - 0.5)) return;
      const stack = document.elementsFromPoint(z.x, z.y), svg = p.ownerSVGElement; let i = stack.indexOf(p); if (i < 0) i = stack.indexOf(svg);
      if (i >= 0 && stack.slice(0, i).some(e => !e.contains(p) && __qa.masks(e))) return;   // a box painted above hides the line here
      hit.add(l.txt);
    }));
    hit.forEach(h => F.push(`${label}: connector runs through text "${h}"`));
  });
  __qa.probe(false);
  return F;
};

// connectors: stroke contrast and arrow tips; SVG labels
__qa.svg = (root, label) => {
  const c = __qa.cfg, sc = __qa.scale(root), R = v => Math.round(v / sc), F = [], lines = __qa.lines(root);
  const rectDist = (z, r) => { const dx = Math.max(r.left - z.x, 0, z.x - r.right), dy = Math.max(r.top - z.y, 0, z.y - r.bottom); return (dx || dy) ? Math.hypot(dx, dy) : -Math.min(z.x - r.left, r.right - z.x, z.y - r.top, r.bottom - z.y); };
  const nodes = [...root.querySelectorAll('*')].filter(e => e !== root && __qa.vis(e, root.parentElement) && (() => {
    if (e.closest('marker, defs, symbol')) return false;
    if (e instanceof SVGElement) { if (!/^(rect|circle|ellipse|polygon)$/.test(e.tagName)) return false; const s = getComputedStyle(e); return (s.fill !== 'none' && (/url\(/.test(s.fill) || __qa.alpha(s.fill) > 0.05)) || (s.stroke !== 'none' && __qa.alpha(s.stroke) > 0.05); }
    const r = e.getBoundingClientRect(); return __qa.boxed(e) && r.width > 16 && r.height > 12;
  })()).map(e => ({ e, r: e.getBoundingClientRect(), name: __qa.name(e) }));
  const contains = (o, r) => r.left >= o.left - 1 && r.right <= o.right + 1 && r.top >= o.top - 1 && r.bottom <= o.bottom + 1;
  __qa.probe(true);
  root.querySelectorAll('svg path, svg line, svg polyline').forEach((p, pi) => {
    if (p.closest('marker, defs, symbol') || !p.getTotalLength || !__qa.vis(p, root.parentElement)) return;
    const cs = getComputedStyle(p); if (cs.stroke === 'none' || __qa.alpha(cs.stroke) < 0.05) return;
    let L; try { L = p.getTotalLength(); } catch (e) { return; } if (L * sc < 8) return;
    const mref = /url\(["']?#([^"')]+)/.exec(p.getAttribute('marker-end') || cs.markerEnd || ''), marker = mref && document.getElementById(mref[1]);
    const isConn = !!(marker || p.getAttribute('marker-start') || p.closest('[data-connector]'));
    const pts = __qa.pathPts(p, 4), mid = pts[Math.floor(pts.length / 2)], svg = p.ownerSVGElement;
    if (isConn) {
      const under = document.elementsFromPoint(mid.x, mid.y).filter(e => !svg.contains(e) && e !== svg);
      let bg = null, grad = false; for (const e of under) { const s = getComputedStyle(e); if (/gradient|url\(/.test(s.backgroundImage)) { grad = true; break; } const q = __qa.parse(s.backgroundColor); if (q && q[3] >= 0.85) { bg = q; break; } }
      if (!grad) { const k = __qa.cr(__qa.parse(cs.stroke), bg || [255, 255, 255, 1]); if (k < 3) F.push(`${label} path${pi}: connector stroke ${cs.stroke} = ${k}:1 against what is behind it (<3)`); }
    }
    if (!marker) return;
    // tip = line end pushed out by the marker's own geometry
    const a = p.getPointAtLength(L), b = p.getPointAtLength(Math.max(0, L - 2)); let dx = a.x - b.x, dy = a.y - b.y; const dl = Math.hypot(dx, dy) || 1; dx /= dl; dy /= dl;
    let off = 0; try { const vb = marker.viewBox.baseVal && marker.viewBox.baseVal.width ? marker.viewBox.baseVal : null, mw = marker.markerWidth.baseVal.value || 3, refX = marker.refX.baseVal.value || 0;
      let maxX = vb ? vb.x + vb.width : mw; const kids = [...marker.querySelectorAll('path, polygon, polyline, line, rect, circle')]; if (kids.length) { maxX = -Infinity; kids.forEach(k => { const bb = k.getBBox(); maxX = Math.max(maxX, bb.x + bb.width); }); }
      off = Math.max(0, (maxX - refX) * (vb ? mw / vb.width : 1) * ((marker.getAttribute('markerUnits') || 'strokeWidth') === 'strokeWidth' ? parseFloat(cs.strokeWidth) || 1 : 1)); } catch (e) { off = 0; }
    const tip = __qa.toScreen(p, a.x + dx * off, a.y + dy * off), u = __qa.toScreen(p, a.x + dx * (off + 1), a.y + dy * (off + 1)), ul = Math.hypot(u.x - tip.x, u.y - tip.y) || 1, hd = { x: (u.x - tip.x) / ul, y: (u.y - tip.y) / ul };
    const start = pts[0], T = nodes.filter(n => !n.e.contains(p) && rectDist(start, n.r) >= 0).map(n => ({ ...n, text: false }))
      .concat(lines.map(l => ({ r: l.r, name: '"' + l.txt + '"', text: true })));
    if (!T.length) return;
    const d = T.map(t => rectDist(tip, t.r));
    if (d.some(x => Math.abs(x) / sc <= c.buried)) return;
    let gap = null, ahead = '';
    for (let g = 1; g <= 4 * c.float * sc && gap === null; g++) { const z = { x: tip.x + hd.x * g, y: tip.y + hd.y * g }; T.forEach((t, i) => { if (gap === null && d[i] >= 0 && (!t.text || g / sc <= c.float) && rectDist(z, t.r) <= 0) { gap = g; ahead = t.name; } }); }
    if (gap !== null && gap / sc <= c.float) return;
    const leaf = T.map((t, i) => ({ t, d: d[i] })).filter(x => x.d < 0 && !x.t.text && !T.some(o => o !== x.t && !o.text && contains(x.t.r, o.r))).sort((x, y) => y.d - x.d)[0];
    if (leaf) F.push(`${label} path${pi}: arrow tip buried ${R(-leaf.d)}px inside ${leaf.t.name}`);
    else if (gap !== null) F.push(`${label} path${pi}: arrow tip floats ${R(gap)}px short of ${ahead}`);
  });
  __qa.probe(false);
  root.querySelectorAll('svg').forEach((svg, si) => {
    if (svg.parentElement.closest('svg')) return;
    const host = svg.getBoundingClientRect(), texts = [...svg.querySelectorAll('text')].filter(t => t.getBoundingClientRect().width > 0 && __qa.vis(t, root.parentElement));
    texts.forEach((t, ti) => { const r = t.getBoundingClientRect(), nm = t.textContent.trim().slice(0, 30);
      texts.slice(ti + 1).forEach(u => { const q = u.getBoundingClientRect(), o = Math.min(r.right, q.right) - Math.max(r.left, q.left), v = Math.min(r.bottom, q.bottom) - Math.max(r.top, q.top); if (o > 1 && v > 1) F.push(`${label} svg${si}: labels "${nm}" / "${u.textContent.trim().slice(0, 30)}" overlap`); });
      if (r.left < host.left - 1 || r.right > host.right + 1 || r.top < host.top - 1 || r.bottom > host.bottom + 1) F.push(`${label} svg${si}: label "${nm}" outside its diagram`); });
  });
  return F;
};

// accent stripes: a heavier coloured edge on ONE side (left bar, or a top stripe over a box).
// Two critique rounds approved 3px top-stripe cards; the owner rejected them as a generic,
// non-pack pattern. Card styling comes from the pack's card templates, never a stripe.
__qa.bars = (root, label) => {
  const F = [], sc = __qa.scale(root);
  root.querySelectorAll('*').forEach(e => {
    if (e instanceof SVGElement || e.closest('[data-accent-bar="ok"]')) return;
    const s = getComputedStyle(e), r = e.getBoundingClientRect();
    if (r.height / sc <= 10 || r.width / sc < 24 || !(e.innerText || '').trim() || !__qa.vis(e, root.parentElement)) return;
    const w = k => (!/none|hidden/.test(s['border' + k + 'Style']) && __qa.alpha(s['border' + k + 'Color']) > 0.05) ? parseFloat(s['border' + k + 'Width']) : 0;
    const W = { Top: w('Top'), Right: w('Right'), Bottom: w('Bottom'), Left: w('Left') };
    ['Left', 'Top'].forEach(side => {
      const others = Object.keys(W).filter(k => k !== side).map(k => W[k]);
      if (side === 'Top' && !__qa.filled(s) && Math.max(...others) === 0) return;   // a divider rule, not a stripe
      if (W[side] >= 2 && Math.max(...others) <= W[side] - 1) F.push(`${label}: ${side.toLowerCase()} stripe ${W[side]}px ${s['border' + side + 'Color']} on ${__qa.name(e)}`);
    });
  });
  return F;
};

// sibling cards that share a row top but end at different heights: the "one short card" a grid
// leaves when it stretches each wrapper and not the card inside it. A card under 60 % of its
// neighbour spans fewer rows by design and is skipped.
__qa.rows = (root, label) => {
  const sc = __qa.scale(root), F = [];
  root.querySelectorAll('*').forEach(c => {
    if (c instanceof SVGElement || !/grid|flex/.test(getComputedStyle(c).display) || c.children.length < 2 || !__qa.vis(c, root.parentElement)) return;
    const cards = [...c.children].map(k => __qa.boxed(k) ? k : [...k.querySelectorAll('*')].find(x => !(x instanceof SVGElement) && __qa.boxed(x) && x.getBoundingClientRect().height / sc > 40))
      .filter(k => { if (!k || !__qa.vis(k, root.parentElement)) return false; const r = k.getBoundingClientRect(); return r.width / sc > 80 && r.height / sc > 60; });
    const rows = {}; cards.forEach(k => { const t = Math.round(k.getBoundingClientRect().top / sc / 4); (rows[t] = rows[t] || []).push(k); });
    Object.values(rows).filter(g => g.length > 1).forEach(g => {
      const hs = g.map(k => Math.round(k.getBoundingClientRect().height / sc)), mn = Math.min(...hs), mx = Math.max(...hs);
      if (mx - mn > 2 * __qa.cfg.tol && mn >= 0.6 * mx) F.push(`${label}: cards in one row end at different heights (${hs.join('/')}px) — ${__qa.name(g[hs.indexOf(mn)])} is short`);
    });
  });
  return F;
};

// text closer than `pad` stage px to the edge of a rounded card (cards that became cards in a
// restyle kept their old zero padding)
__qa.pad = (root, label) => {
  const sc = __qa.scale(root), F = [], seen = new Set(), pad = __qa.cfg.pad;
  __qa.lines(root).forEach(l => {
    if (l.el.closest('svg')) return;
    let box = l.el; while (box && box !== root && !__qa.boxed(box)) box = box.parentElement;
    if (!box || box === root || seen.has(box)) return;
    const bs = getComputedStyle(box), br = box.getBoundingClientRect();
    if (!(parseFloat(bs.borderTopLeftRadius) > 0) || br.width / sc < 120 || br.height / sc < 48) return;
    const t = Math.min(l.r.left - br.left, br.right - l.r.right, l.r.top - br.top, br.bottom - l.r.bottom);
    if (t >= 0 && t / sc < pad) { seen.add(box); F.push(`${label}: "${l.txt}" sits ${Math.round(t / sc)}px from the edge of its rounded card ${__qa.name(box)}`); }
  });
  return F;
};

// smallest rendered text, in stage px: SVG text through its screen CTM, HTML text through the
// accumulated CSS transform scale (rendered width / layout width), both over the slide's scale
__qa.minfont = (root, label) => {
  const floor = __qa.cfg.minFont; if (!floor) return [];
  const sc = __qa.scale(root), F = [], seen = new Set();
  __qa.lines(root).forEach(l => {
    if (seen.has(l.el)) return; seen.add(l.el);
    const fs = parseFloat(getComputedStyle(l.el).fontSize), svg = l.el.closest('svg');
    let k;
    if (svg) { const m = (l.el.getScreenCTM ? l.el : svg).getScreenCTM(); k = m ? Math.sqrt(Math.abs(m.a * m.d - m.b * m.c)) : 1; }
    else { let e = l.el; while (e && !e.offsetWidth) e = e.parentElement; k = e ? e.getBoundingClientRect().width / e.offsetWidth : 1; }
    const eff = fs * k / sc;
    if (eff < floor - 0.25) F.push(`${label}: ${eff.toFixed(1)}px "${l.txt.slice(0, 30)}" (< ${floor})`);
  });
  return F;
};

__qa.runRoot = async (root, label, checks) => { await __qa.freeze(root); return checks.flatMap(c => __qa[c](root, label)); };
__qa.runSlides = async (checks, which) => {
  const out = {}, n = __qa.slides().length;
  for (let i = 1; i <= n; i++) {
    if (which && !which.includes(i)) continue;
    await __qa.goto(i);
    const s = __qa.current(); const f = await __qa.runRoot(s, 's' + String(i).padStart(2, '0'), checks); if (f.length) out[i] = f;
  }
  return out;
};
// overlays (zoom panels, appendices): open(key) shows one and returns its root element
__qa.runPanels = async (keys, open, close, checks) => {
  const out = {};
  for (const k of keys) { const root = await open(k); await __qa.sleep(__qa.cfg.settle); const f = await __qa.runRoot(root, 'panel:' + k, checks); if (f.length) out[k] = f; }
  if (close) await close(); return out;
};

// try one type-scale factor on a slide body (a wider brand font kept the old 20–24 px body and
// read as dense; one factor for all body text fixed it). Reads EVERY size first, then writes,
// so nothing is scaled twice; SVG <text> is included or labels end up oversized; floored at
// the pack minimum. Returns how many elements changed. Bake the result into the restyle as a
// load-time script once the factor is chosen.
__qa.typeScale = (root, factor, floor) => {
  floor = floor || __qa.cfg.minFont || 0;
  if (!root || root.dataset.qaScaled) return 0; root.dataset.qaScaled = '1';
  const els = [root, ...root.querySelectorAll('*')].filter(e => !(e instanceof SVGElement) || e.tagName.toLowerCase() === 'text');
  const orig = els.map(e => { const c = getComputedStyle(e); return [parseFloat(c.fontSize), c.lineHeight]; });
  els.forEach((e, i) => { const [fs, lh] = orig[i]; if (!fs) return; const nf = Math.max(floor, fs * factor);
    e.style.setProperty('font-size', nf.toFixed(2) + 'px', 'important');
    const l = parseFloat(lh); if (l) e.style.setProperty('line-height', (l * nf / fs).toFixed(2) + 'px', 'important'); });
  return els.length;
};
// for each text that leaves its box: selector, size, and the largest size that fits (null = none ≥ floor)
__qa.spillers = (root, label) => {
  const sc = __qa.scale(root), out = [], done = new Set(), floor = __qa.cfg.minFont || 0;
  __qa.lines(root).forEach(l => {
    const el = l.el; if (done.has(el) || el.closest('svg')) return;
    let box = el; while (box && box !== root && !__qa.boxed(box)) box = box.parentElement; if (!box || box === root || box === el) return;
    const spill = () => { const br = box.getBoundingClientRect(); let mx = -99; const rg = document.createRange(); rg.selectNodeContents(el); [...rg.getClientRects()].forEach(r => { if (r.width > 2) mx = Math.max(mx, br.top - r.top, r.bottom - br.bottom, br.left - r.left, r.right - br.right); }); return mx / sc; };
    const sp = spill(); if (sp <= 3) return; done.add(el);
    const fs0 = parseFloat(getComputedStyle(el).fontSize); let fit = null;
    for (let f = fs0 - 0.5; f >= floor; f -= 0.5) { el.style.setProperty('font-size', f + 'px', 'important'); if (spill() <= 1) { fit = f; break; } }
    el.style.removeProperty('font-size');
    out.push(`${label} | ${__qa.name(el)} < ${__qa.name(box)} | spill ${Math.round(sp)} | fs ${fs0} → fits ${fit}`);
  });
  return out;
};
// the boxes on a slide: class, stage rect, fill, borders, first words — input for a layout rebuild
__qa.outline = root => {
  root = root || __qa.current(); const sc = __qa.scale(root), st = root.getBoundingClientRect(), out = [];
  root.querySelectorAll('*').forEach(e => { if (e instanceof SVGElement || !__qa.vis(e, root.parentElement) || !__qa.boxed(e)) return; const r = e.getBoundingClientRect(); if (r.width / sc < 60 || r.height / sc < 24) return; const c = getComputedStyle(e);
    const b = ['Top', 'Right', 'Bottom', 'Left'].map(k => parseFloat(c['border' + k + 'Width']) ? c['border' + k + 'Width'] + ' ' + c['border' + k + 'Style'][0] + ' ' + c['border' + k + 'Color'].replace(/rgba?\(|\)| /g, '') : '-').join('|');
    out.push(`${__qa.name(e)} @${Math.round((r.left - st.left) / sc)},${Math.round((r.top - st.top) / sc)} ${Math.round(r.width / sc)}x${Math.round(r.height / sc)} bg=${c.backgroundColor.replace(/rgba?\(|\)| /g, '')} b=${b}`); });
  return out.join('\n');
};
// try a stylesheet live (a candidate rebuild) and re-run checks against it
__qa.setCss = css => { let st = document.getElementById('qa-fix'); if (!st) { st = document.createElement('style'); st.id = 'qa-fix'; document.head.appendChild(st); } st.textContent = css; };
// findings grouped by shape, numbers and quoted text folded — the summary to triage from
__qa.cats = res => { const c = {}; Object.values(res).flat().forEach(s => { const k = s.replace(/^\S+( (svg|path)\d+)?:? /, '').replace(/".*?"/g, '"…"').replace(/rgba?\([^)]*\)/g, 'rgb').replace(/\d+(\.\d+)?/g, 'N'); c[k] = (c[k] || 0) + 1; }); return c; };
'qa loaded';
