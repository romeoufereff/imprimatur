/* imprimatur deck-motion — slide runtime (copied into <deck>/motion/ by choreograph.py).
 *
 * Loaded synchronously from the slide's <head> next to an inline JSON spec
 * (<script id="imprimatur-motion-spec" type="application/json">). It plays the slide's
 * entrance choreography as ONE paused GSAP timeline, hyperframes-contract style:
 * registered at window.__timelines[file], seek-safe fromTo tweens, transforms and
 * opacity only, nothing time- or random-dependent.
 *
 * STATIC MODE — the guarantee every exporter relies on. When any of these hold the script
 * returns before touching the DOM: navigator.webdriver (Playwright: PDF, PPTX IR, QA),
 * ?static=1 in the URL, window.__IMPRIMATUR_STATIC, prefers-reduced-motion. The slide is
 * then byte-for-byte what the designer wrote. QA still gets `__imprimaturMotion.build({force:true})`
 * to prove the END state equals the static state (check_motion.py).
 *
 * END STATE = ORIGINAL DOM, by construction: every animated element's inline `style`
 * attribute is recorded before the first tween and restored when the timeline completes
 * or is sent to its end; count-ups write the original string back verbatim.
 *
 * Messages (parent viewer ↔ this slide), {ns:"imprimatur-motion", type, ...}:
 *   out: ready{total_ms, steps, static} · key{key, shiftKey} · step{remaining} · complete
 *   in : play · next-step · to-end · restart · set-static{value}
 * Standalone (no parent): autoplay on load. `?t=1.25` builds the timeline and freezes it at that
 * second (no autoplay): the frozen frame any screenshot, filmstrip or critic can rely on.
 */
(function () {
  "use strict";
  var NS = "imprimatur-motion";
  var specEl = document.getElementById("imprimatur-motion-spec");
  var selfEl = document.getElementById("imprimatur-motion");
  if (!specEl) return;
  var spec;
  try { spec = JSON.parse(specEl.textContent || "{}"); } catch (e) { return; }
  if (!spec || !Array.isArray(spec.beats)) return;

  var reduced = false;
  try { reduced = !!(window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches); } catch (e) {}
  var isStatic = !!(navigator.webdriver || /[?&]static=1(?:&|$)/.test(location.search) ||
                    window.__IMPRIMATUR_STATIC || reduced);
  var embedded = window.parent && window.parent !== window;
  var seekT = null;   // ?t=<seconds>: build, then hold the timeline at that moment
  try { var mt = /[?&]t=(\d+(?:\.\d+)?)(?:&|$)/.exec(location.search); if (mt) seekT = parseFloat(mt[1]); } catch (e) {}
  var gsapUrl = (selfEl && selfEl.getAttribute("data-gsap")) || spec.gsapUrl ||
                "https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js";

  var api = {
    spec: spec, static: isStatic, built: false, tl: null, steps: 0, stepsDone: 0,
    build: build, play: play, toEnd: toEnd, restart: restart, nextStep: nextStep,
    stepsRemaining: function () { return Math.max(0, api.steps - api.stepsDone); },
    seek: function (t) { if (api.tl) { stopIdle(); api.tl.pause(); api.tl.time(Math.max(0, Math.min(+t || 0, api.tl.duration())), true); } },
    seekT: seekT, info: null,
  };
  window.__imprimaturMotion = api;
  window.__timelines = window.__timelines || {};

  function post(msg) {
    if (!embedded) return;
    try { window.parent.postMessage(Object.assign({ ns: NS }, msg), "*"); } catch (e) {}
  }

  // ── veil: nothing paints before the from-states are applied ──────────────
  var veil = null;
  if (!isStatic) {
    veil = document.createElement("style");
    veil.id = "imprimatur-motion-veil";
    veil.textContent = "#slide{visibility:hidden !important}";
    (document.head || document.documentElement).appendChild(veil);
  }
  function unveil() { if (veil && veil.parentNode) veil.parentNode.removeChild(veil); veil = null; }

  // ── GSAP ─────────────────────────────────────────────────────────────────
  function loadGsap() {
    return new Promise(function (resolve, reject) {
      if (window.gsap) return resolve(window.gsap);
      var s = document.createElement("script");
      s.src = gsapUrl; s.async = true;
      s.onload = function () { window.gsap ? resolve(window.gsap) : reject(new Error("gsap missing after load")); };
      s.onerror = function () { reject(new Error("gsap failed to load: " + gsapUrl)); };
      (document.head || document.documentElement).appendChild(s);
    });
  }
  function loadMotionPath() {
    return new Promise(function (resolve) {
      if (window.MotionPathPlugin) { try { window.gsap.registerPlugin(window.MotionPathPlugin); } catch (e) {} return resolve(true); }
      var sc = document.createElement("script");
      sc.src = gsapUrl.replace(/gsap(\.min)?\.js(\?.*)?$/, "MotionPathPlugin$1.js"); sc.async = true;
      sc.onload = function () { try { window.gsap.registerPlugin(window.MotionPathPlugin); resolve(true); } catch (e) { resolve(false); } };
      sc.onerror = function () { resolve(false); };
      (document.head || document.documentElement).appendChild(sc);
    });
  }
  function domReady() {
    return new Promise(function (resolve) {
      if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", resolve, { once: true });
      else resolve();
    });
  }
  function stylesReady() {
    // Tailwind Play CDN injects its stylesheet after parse; measuring before that is wrong.
    var start = Date.now();
    return new Promise(function (resolve) {
      (function poll() {
        var ok = [].slice.call(document.querySelectorAll("style")).some(function (s) {
          return (s.textContent || "").indexOf("--tw-") >= 0 || (s.textContent || "").indexOf("tailwind") >= 0;
        }) || !document.querySelector('script[src*="tailwindcss"]');
        if (ok || Date.now() - start > 2500) return resolve();
        setTimeout(poll, 30);
      })();
    }).then(function () { return (document.fonts && document.fonts.ready) || Promise.resolve(); })
      .then(function () { return new Promise(function (r) { requestAnimationFrame(function () { r(); }); }); });
  }

  // ── selectors & restore ───────────────────────────────────────────────────
  // A selector is a CSS string, or a compact path: child indexes from #slide ([1,3,2] →
  // "#slide > :nth-child(1) > :nth-child(3) > :nth-child(2)"). A group is an array of either.
  function isPath(p) { return Array.isArray(p) && p.length > 0 && p.every(function (x) { return typeof x === "number"; }); }
  function toSel(p) {
    if (isPath(p)) return "#slide" + p.map(function (i) { return " > :nth-child(" + i + ")"; }).join("");
    return String(p);
  }
  function resolve(sel) {
    if (sel && sel.nodeType === 1) return [sel];
    var list = (Array.isArray(sel) && !isPath(sel)) ? sel : [sel];
    var out = [];
    list.forEach(function (s) {
      if (s && s.nodeType === 1) { out.push(s); return; }
      try { var el = document.querySelector(toSel(s)); if (el) out.push(el); } catch (e) {}
    });
    return out;
  }
  // Every selector in the spec is resolved BEFORE any beat is built. Positional paths are only
  // valid against the untouched DOM: a travelling token inserted into an SVG during the build
  // would shift the :nth-child index of every sibling after it, and a later beat (or the scene's
  // emphasis, or a travel's own onVisit) would land on the wrong node (found by a director,
  // 2026-10-04). Resolved elements are kept on the beat; `resolve()` passes them through.
  function preResolve(spec) {
    var fix = function (b) {   // the spec itself stays untouched (QA re-reads its selectors); refs ride alongside
      if (!b) return;
      if (b.sel !== undefined) b._els = resolve(b.sel);
      if (b.along) b._along = resolve(b.along)[0] || null;
      if (Array.isArray(b.waypoints)) b._wps = b.waypoints.map(function (w) { return resolve(w)[0] || null; });
      if (Array.isArray(b.onVisit)) b._visits = b.onVisit.map(function (v) { return v ? resolve(v) : null; });
    };
    (spec.beats || []).forEach(fix);
    (spec.idle || []).forEach(fix);
    owned = [];
    (spec.beats || []).forEach(function (b) { (b._els || []).forEach(function (e) { owned.push(e); }); });
  }
  api.resolve = resolve; api.toSelector = toSel;

  // END STATE = ORIGINAL DOM: snapshot every attribute (GSAP writes `style`, and on SVG
  // nodes `transform` + `data-svg-origin`) and the text of count-up targets; put them back.
  var originals = [];  // [{el, attrs:{name:value}, text, html}]
  function remember(el, withText, withHtml) {
    for (var i = 0; i < originals.length; i++) if (originals[i].el === el) {
      if (withText && originals[i].text == null) originals[i].text = el.textContent;
      if (withHtml && originals[i].html == null) originals[i].html = el.innerHTML;
      return;
    }
    var attrs = {};
    for (var a = 0; a < el.attributes.length; a++) attrs[el.attributes[a].name] = el.attributes[a].value;
    originals.push({ el: el, attrs: attrs, text: withText ? el.textContent : null, html: withHtml ? el.innerHTML : null });
  }
  var created = [];   // nodes the runtime added (travelling tokens, trail marks) — removed on restore
  // keepSplits: leave word-split markup in place. Un-splitting a title re-flows it by a few
  // pixels (kerning across word boundaries is lost inside atomic inline-blocks — measured as a
  // 2.3 MAE jump on the title band), so the entrance's completion keeps the spans and only the
  // moment the slide is LEFT (toEnd / export / QA) restores the markup, when nobody is looking.
  var idleEls = [];   // what the idle timeline drives: restored only when the slide is left
  function restoreAll(opts) {
    var keepSplits = !!(opts && opts.keepSplits), exceptIdle = !!(opts && opts.exceptIdle);
    created.forEach(function (n) { if (n.parentNode) n.parentNode.removeChild(n); });
    created = [];
    originals.forEach(function (o) {
      if (keepSplits && o.html != null) return;
      if (exceptIdle && idleEls.indexOf(o.el) >= 0) return;
      var el = o.el, names = [];
      for (var a = 0; a < el.attributes.length; a++) names.push(el.attributes[a].name);
      names.forEach(function (n) { if (!(n in o.attrs)) el.removeAttribute(n); });
      Object.keys(o.attrs).forEach(function (n) { if (el.getAttribute(n) !== o.attrs[n]) el.setAttribute(n, o.attrs[n]); });
      if (o.html != null && el.innerHTML !== o.html) el.innerHTML = o.html;
      else if (o.text != null && el.textContent !== o.text) el.textContent = o.text;
    });
  }
  // Word split for the kinetic text effects: every text node under the element is split into
  // inline-block word spans IN PLACE, so an accent <span class="text-…-blue"> keeps its colour and
  // its words simply become children of it. innerHTML is snapshotted before and restored after.
  function splitWords(el) {
    if (!(el.textContent || "").trim()) return null;
    // A gradient-text element (background clipped to its own glyphs) cannot be split: child boxes
    // would inherit the transparent fill with no gradient behind them and render invisible. Such an
    // element moves as ONE word unit instead.
    var clipped = function (node) {
      for (var a = node.parentElement; a && a !== el; a = a.parentElement) {
        var cs = getComputedStyle(a);
        if ((cs.webkitBackgroundClip === "text" || cs.backgroundClip === "text") || /gradient-text/.test(a.className || "")) return a;
      }
      return null;
    };
    var walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT, null), nodes = [], units = [];
    while (walker.nextNode()) {
      var tn = walker.currentNode;
      if (!tn.textContent.trim() || /^(script|style)$/i.test(tn.parentNode.tagName)) continue;
      var unit = clipped(tn);
      if (unit) { if (units.indexOf(unit) < 0) units.push(unit); continue; }
      nodes.push(tn);
    }
    if (!nodes.length && !units.length) return null;
    // assistive tech reads the sentence, never the fragments (restored with the markup on leave)
    el.setAttribute("aria-label", (el.textContent || "").replace(/\s+/g, " ").trim());
    var spans = [];
    nodes.forEach(function (tn) {
      var parts = tn.textContent.split(/(\s+)/), frag = document.createDocumentFragment();
      parts.forEach(function (ptxt) {
        if (!ptxt) return;
        if (/^\s+$/.test(ptxt)) { frag.appendChild(document.createTextNode(ptxt)); return; }
        var sp = document.createElement("span"); sp.textContent = ptxt; sp.style.position = "relative"; sp.setAttribute("aria-hidden", "true");   // inline + relative: no reflow, movable through `top`
        spans.push(sp); frag.appendChild(sp);
      });
      tn.parentNode.replaceChild(frag, tn);
    });
    // units (gradient phrases) are left untouched and fade as one. Word spans are inline too, so a
    // split title lays out exactly like the static one — inline-block spans reflowed it by 2–5 MAE,
    // which is why 1.5.x had to keep the split until the slide was left; `top` moves an inline span.
    units.forEach(function (u) { u.setAttribute("data-motion-unit", ""); spans.push(u); });
    // keep document order so the cascade reads left to right
    spans.sort(function (a, b) { return (a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING) ? -1 : 1; });
    return spans.length ? spans : null;
  }
  // Split by rendered LINE: each text node's words are located with a Range (no DOM change), grouped
  // by line, and each line's exact characters are wrapped in ONE inline span. A span boundary only
  // ever falls where the line already broke, so shaping and kerning are untouched: the split title
  // is pixel-identical to the static one (word spans were not — Blink breaks shaping at element
  // boundaries, 0.7–1.6 MAE on wrapped titles). Units (gradient phrases) stay whole.
  function splitLines(el) {
    if (!(el.textContent || "").trim()) return null;
    var clipped = function (node) {
      for (var a = node.parentElement; a && a !== el; a = a.parentElement) {
        var cs = getComputedStyle(a);
        if ((cs.webkitBackgroundClip === "text" || cs.backgroundClip === "text") || /gradient-text/.test(a.className || "")) return a;
      }
      return null;
    };
    var walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT, null), nodes = [], units = [];
    while (walker.nextNode()) {
      var tn = walker.currentNode;
      if (!tn.textContent.trim() || /^(script|style)$/i.test(tn.parentNode.tagName)) continue;
      var unit = clipped(tn);
      if (unit) { if (units.indexOf(unit) < 0) units.push(unit); continue; }
      nodes.push(tn);
    }
    if (!nodes.length && !units.length) return null;
    el.setAttribute("aria-label", (el.textContent || "").replace(/\s+/g, " ").trim());
    var spans = [];
    nodes.forEach(function (tn) {
      var text = tn.textContent, re = /\S+/g, m, pieces = [], lastTop = null, start = 0;
      // find the first character of every word and the line it renders on
      while ((m = re.exec(text))) {
        var r = document.createRange(); r.setStart(tn, m.index); r.setEnd(tn, m.index + 1);
        var rect = r.getBoundingClientRect(), top = Math.round(rect.top / 4) * 4;
        if (lastTop !== null && top !== lastTop) { pieces.push(text.slice(start, m.index)); start = m.index; }
        lastTop = top;
      }
      pieces.push(text.slice(start));
      var frag = document.createDocumentFragment();
      pieces.forEach(function (ptxt) {
        if (!ptxt) return;
        var sp = document.createElement("span"); sp.textContent = ptxt; sp.style.position = "relative"; sp.setAttribute("aria-hidden", "true");
        spans.push(sp); frag.appendChild(sp);
      });
      tn.parentNode.replaceChild(frag, tn);
    });
    units.forEach(function (u) { u.setAttribute("data-motion-unit", ""); spans.push(u); });
    spans.sort(function (a, b) { return (a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING) ? -1 : 1; });
    return spans.length ? spans : null;
  }
  // Member order for a stagger: start (reading order), center-out, edges-in.
  function orderIndex(i, n, from) {
    if (from === "center") { var c = (n - 1) / 2; return Math.abs(i - c); }
    if (from === "edges") { var c2 = (n - 1) / 2; return c2 - Math.abs(i - c2); }
    if (from === "end") return n - 1 - i;
    return i;
  }

  // ── effects (transforms + opacity + a text proxy; never layout) ──────────
  var NUM_RE = /-?\d[\d,]*(?:\.\d+)?/;
  // Travel for the i-th member of a beat: `dist` (px) and `dir` (up/down/left/right) are
  // per-beat; `parallax` gives members different depths so a group reads as layered, not stamped.
  function travel(beat, i, cfg) {
    var d = typeof beat.dist === "number" ? beat.dist : cfg.distancePx;
    if (beat.parallax) d = d * (1 + 0.45 * (i % 3));
    var dir = beat.dir || "up";
    return { x: dir === "left" ? -d : dir === "right" ? d : 0, y: dir === "up" ? d : dir === "down" ? -d : 0 };
  }
  // An SVG node with its own `transform` attribute (an icon group translated into place) keeps
  // that as its base: GSAP would otherwise REPLACE the translate with the tween value and park the
  // node at the origin until restore.
  function base(gsap, el) {
    if (!el.ownerSVGElement || !el.getAttribute("transform")) return { x: 0, y: 0 };
    return { x: +gsap.getProperty(el, "x") || 0, y: +gsap.getProperty(el, "y") || 0 };
  }
  // Defocus is hardware-accelerated but not free: its cost grows with radius × layer area, and
  // above ~10 px it is the usual cause of a dropped frame (Motion's performance tier list). The
  // dial scales it; this caps it whatever the dial says.
  var BLUR_MAX = 10;
  function blurPx(px, cfg) { return Math.min(BLUR_MAX, Math.round(px * cfg.blur)); }
  // Follow-through (1.6.0): a card's content settles a beat after its container — the secondary
  // layer that makes an arrival read as layered instead of stamped (children trail the parent by
  // 50–150 ms). Still fromTo tweens: the end state is the static DOM.
  var owned = [];   // every element any beat targets (filled by preResolve)
  function ownedElsewhere(c) { return owned.some(function (o) { return o === c || c.contains(o) || o.contains(c); }); }
  function followThrough(gsap, tl, el, t, dur, cfg) {
    if (el.ownerSVGElement) return;
    var kids = [].slice.call(el.children).filter(function (c) { return c.nodeType === 1 && !/^(script|style)$/i.test(c.tagName); });
    var ownText = function (c) { return [].slice.call(c.childNodes).some(function (n) { return n.nodeType === 3 && n.textContent.trim().length > 1; }); };
    var flat = [];   // a wrapper without text of its own (a flex column holding title + body) opens one level, so the title leads and its text follows
    kids.forEach(function (c) { if (!ownText(c) && c.children.length >= 2 && c.children.length <= 6) [].slice.call(c.children).forEach(function (g) { flat.push(g); }); else flat.push(c); });
    kids = flat;
    // a child another beat owns (a KPI counting inside the card, a bar, a connector) is that beat's:
    // two tweens on one opacity made the number appear, vanish and reappear (slide 16, 2026-10-10)
    kids = kids.filter(function (c) { var r = c.getBoundingClientRect(); return r.width > 1 && r.height > 1 && !ownedElsewhere(c); }).slice(0, 8);
    if (kids.length < 2) return;
    kids.forEach(function (c, k) {
      remember(c);
      var o = parseFloat(getComputedStyle(c).opacity); if (isNaN(o)) o = 1;
      tl.fromTo(c, { opacity: 0, y: 8 }, { opacity: o, y: 0, duration: 0.3, ease: cfg.ease, immediateRender: true }, t + dur * 0.45 + k * 0.04);
    });
  }
  // The emphasis gesture: out of rest and back to rest, both `to` tweens, so it starts from
  // whatever the entrance left (the resting state) and ends there. Position on text; a 3 % scale
  // only where the personality allows text to scale.
  function nudge(gsap, tl, el, t, dur, cfg, px) {
    var b0 = base(gsap, el), up = dur * 0.4, down = dur * 0.6;
    if (cfg.textScale) { tl.to(el, { scale: 1.03, transformOrigin: "50% 50%", duration: up, ease: cfg.ease }, t); tl.to(el, { scale: 1, duration: down, ease: cfg.move }, t + up); return; }
    tl.to(el, { y: b0.y - px, duration: up, ease: cfg.ease }, t);
    tl.to(el, { y: b0.y, duration: down, ease: cfg.move }, t + up);
  }
  // An SVG node whose own transform carries a scale, rotation or matrix cannot be moved through
  // GSAP's transform model: it re-serialises the transform and drops the native scale (slide 13's
  // icon, `translate(134 440) scale(2.6667)`, ended at `matrix(1,0,0,1,154,460)`, 44 MAE off its
  // place until the restore). Such a node arrives by opacity alone.
  function lockedTransform(el) {
    if (!el.ownerSVGElement) return false;
    // the PRISTINE attribute: an earlier beat's tween has already written `matrix(…)` onto any
    // element it touched (immediateRender), which is not a native transform
    var tf = null;
    for (var i = 0; i < originals.length; i++) if (originals[i].el === el) { tf = originals[i].attrs.transform || ""; break; }
    if (tf === null) tf = el.getAttribute("transform") || "";
    return /scale|rotate|matrix|skew/i.test(tf);
  }
  function addBeat(gsap, tl, beat, cfg) {
    var els = beat._els || resolve(beat.sel);
    if (!els.length) return 0;
    // (never on an emphasis: a locked icon inside the focal element would vanish and fade back at the point)
    if (beat.effect !== "draw" && beat.effect !== "travel" && beat.effect !== "count-up" && beat.effect !== "pulse" &&
        beat.role !== "emphasis" && !/^(lift|settle|pop|focus-pull)$/.test(beat.effect)) {
      var locked = els.filter(lockedTransform);
      if (locked.length) {
        var atL = Math.max(0, +beat.at || 0), durL = Math.max(0.1, +beat.dur || 0.4), stL = els.length > 1 ? Math.max(0, +beat.stagger || 0) : 0;
        locked.forEach(function (el) { var k = els.indexOf(el), o = parseFloat(getComputedStyle(el).opacity); if (isNaN(o)) o = 1; remember(el);
          tl.fromTo(el, { opacity: 0 }, { opacity: o, duration: durL, ease: beat.ease || cfg.ease, immediateRender: true }, atL + orderIndex(k, els.length, beat.from) * stL); });
        els = els.filter(function (el) { return !lockedTransform(el); });
        if (!els.length) return locked.length;
      }
    }
    var n = els.length;
    var dur = Math.max(0.1, +beat.dur || 0.4);
    var at = Math.max(0, +beat.at || 0);
    var stagger = n > 1 ? Math.max(0, +beat.stagger || 0) : 0;
    var ease = beat.ease || cfg.easeIn;                 // arrivals: out-eases only; the pack never asks for a bounce
    var dist = typeof beat.dist === "number" ? beat.dist : cfg.distancePx;
    var own = function (el) { var o = parseFloat(getComputedStyle(el).opacity); return isNaN(o) ? 1 : o; };
    var order = Array.isArray(beat.order) && beat.order.length === n ? beat.order : null;   // grid / distance cascade from the choreographer
    var when = function (i) { return at + (order ? order[i] : orderIndex(i, n, beat.from)) * stagger; };
    var split = beat.effect === "words" || beat.effect === "words-mask" || beat.effect === "lines-mask";
    els.forEach(function (el) { remember(el, beat.effect === "count-up", split); });
    switch (beat.effect) {
      // ── soft arrivals (details, context) ──
      case "fade":
        els.forEach(function (el, i) { tl.fromTo(el, { opacity: 0 }, { opacity: own(el), duration: dur, ease: ease, immediateRender: true }, when(i)); }); break;
      case "fade-up": case "fade-left":
        els.forEach(function (el, i) { var t = travel(beat.effect === "fade-left" ? Object.assign({ dir: "left" }, beat) : beat, i, cfg), b0 = base(gsap, el);
          tl.fromTo(el, { opacity: 0, x: b0.x + t.x, y: b0.y + t.y }, { opacity: own(el), x: b0.x, y: b0.y, duration: dur + (beat.parallax ? 0.08 * (i % 3) : 0), ease: ease, immediateRender: true }, when(i));
          if (beat.followThrough) followThrough(gsap, tl, el, when(i), dur, cfg); }); break;
      case "blur-in": {
        var bpx = blurPx(10, cfg);
        if (!bpx) { els.forEach(function (el, i) { var b0 = base(gsap, el); tl.fromTo(el, { opacity: 0, x: b0.x, y: b0.y + 12 }, { opacity: own(el), x: b0.x, y: b0.y, duration: dur, ease: ease, immediateRender: true }, when(i)); }); break; }
        els.forEach(function (el, i) { tl.fromTo(el, { opacity: 0, filter: "blur(" + bpx + "px)" }, { opacity: own(el), filter: "blur(0px)", duration: dur, ease: ease, immediateRender: true }, when(i)); }); break;
      }
      case "wipe-right":
        els.forEach(function (el, i) { tl.fromTo(el, { clipPath: "inset(-25% 100% -25% -25%)" }, { clipPath: "inset(-25% -25% -25% -25%)", duration: dur, ease: ease, immediateRender: true }, when(i)); }); break;
      case "wipe-down":   // a column reveals from the top down (a wipe-up on a tall member read bottom-to-top)
        els.forEach(function (el, i) { tl.fromTo(el, { clipPath: "inset(-25% -25% 100% -25%)", y: -dist * 0.5 }, { clipPath: "inset(-25% -25% -25% -25%)", y: 0, duration: dur, ease: ease, immediateRender: true }, when(i));
          if (beat.followThrough) followThrough(gsap, tl, el, when(i), dur, cfg); }); break;
      case "wipe-up":
        els.forEach(function (el, i) { tl.fromTo(el, { clipPath: "inset(100% -25% -25% -25%)", y: dist * 0.5 }, { clipPath: "inset(-25% -25% -25% -25%)", y: 0, duration: dur, ease: ease, immediateRender: true }, when(i));
          if (beat.followThrough) followThrough(gsap, tl, el, when(i), dur, cfg); }); break;

      // ── kinetic arrivals (structure, heroes) ──
      case "spring":   // emergent arrival: settles from scaleIn (corporate 94 %) with a little rise; never from nothing, never an overshoot
        els.forEach(function (el, i) { var b0 = base(gsap, el), sc = cfg.textScale ? cfg.scaleIn : 1;   // corporate / premium: no transform-scale on anything (a tweened `scale: 1` also overwrote the native scale of an SVG <g transform>)
          tl.fromTo(el, { opacity: 0, scale: sc, x: b0.x, y: b0.y + Math.min(24, dist), transformOrigin: "50% 50%" },
          { opacity: own(el), scale: 1, x: b0.x, y: b0.y, duration: dur, ease: beat.ease || cfg.ease, immediateRender: true }, when(i));
          if (beat.followThrough) followThrough(gsap, tl, el, when(i), dur, cfg); }); break;
      case "rise":
        els.forEach(function (el, i) { var t = travel(beat, i, cfg), b0 = base(gsap, el); tl.fromTo(el, { opacity: 0, x: b0.x + t.x * 1.5, y: b0.y + t.y * 1.5, scale: cfg.textScale ? 0.985 : 1, transformOrigin: "50% 100%" },
          { opacity: own(el), x: b0.x, y: b0.y, scale: 1, duration: dur + (beat.parallax ? 0.1 * (i % 3) : 0), ease: ease, immediateRender: true }, when(i));
          if (beat.followThrough) followThrough(gsap, tl, el, when(i), dur, cfg); }); break;
      case "whip":     // waterfall arrival: hidden until its beat, then binary opacity + whip from below, power4.out
        els.forEach(function (el, i) { var w = (beat.weight === "heavy" ? 70 : beat.weight === "light" ? 36 : 48), b0 = base(gsap, el), o = own(el);
          gsap.set(el, { opacity: 0 });
          // an 80 ms ramp instead of a hard cut: on a projector a binary appearance reads as a flicker
          tl.fromTo(el, { opacity: 0, y: b0.y + w }, { opacity: o, duration: 0.08, ease: "none", immediateRender: false }, when(i));
          tl.to(el, { y: b0.y, duration: Math.max(0.13, dur), ease: cfg.hero }, when(i)); }); break;
      case "slam":     // kinetic slam: scale 1.5 → 1 with the blur clearing — the hero statement hit
        els.forEach(function (el, i) { tl.fromTo(el, { opacity: 0, scale: cfg.heroScale, filter: "blur(" + blurPx(16, cfg) + "px)", transformOrigin: "50% 50%" },
          { opacity: own(el), scale: 1, filter: "blur(0px)", duration: dur, ease: cfg.hero, immediateRender: true }, when(i)); }); break;
      case "snap":     // side-snap with a motion-blur streak that resolves at settle
        els.forEach(function (el, i) { var from = (beat.dir === "right" ? 1 : -1) * Math.max(160, dist * 10);
          tl.fromTo(el, { opacity: 1, x: from, filter: "blur(" + blurPx(14, cfg) + "px)" }, { x: 0, filter: "blur(0px)", duration: dur, ease: cfg.hero, immediateRender: true }, when(i));
          tl.fromTo(el, { opacity: 0 }, { opacity: own(el), duration: Math.min(0.12, dur / 3), ease: "power1.out", immediateRender: true }, when(i)); }); break;
      case "rise-rotate":
        els.forEach(function (el, i) { tl.fromTo(el, { opacity: 0, y: 90, rotation: 6, transformOrigin: "0% 100%" },
          { opacity: own(el), y: 0, rotation: 0, duration: dur, ease: cfg.hero, immediateRender: true }, when(i)); }); break;

      // ── kinetic text ──
      case "words": {  // the waterfall: words whip in from below, binary opacity, gaps shrinking toward the end
        els.forEach(function (el, i) {
          var spans = splitWords(el);
          if (!spans) { tl.fromTo(el, { opacity: 0, y: dist }, { opacity: own(el), y: 0, duration: dur, ease: ease, immediateRender: true }, when(i)); return; }
          var t = when(i), count = spans.length, wdur = count > 12 ? 0.13 : count > 6 ? 0.15 : 0.18;
          var gap0 = Math.min(0.09, 0.6 / count);          // first gap; shrinks across the cascade
          spans.forEach(function (sp, k) {
            var w = sp.textContent.length > 7 ? 64 : sp.textContent.length > 3 ? 48 : 36;
            if (sp.hasAttribute("data-motion-unit")) { tl.fromTo(sp, { opacity: 0 }, { opacity: 1, duration: wdur * 1.6, ease: cfg.ease, immediateRender: false }, t); }
            else { tl.fromTo(sp, { opacity: 0, top: w }, { opacity: 1, duration: 0.08, ease: "none", immediateRender: false }, t);
                   tl.to(sp, { top: 0, duration: wdur, ease: cfg.hero }, t); }
            t += gap0 * (1 - 0.5 * (k / Math.max(1, count - 1)));
          });
          tl.set(el, { opacity: own(el) }, when(i));
          spans.forEach(function (sp) { gsap.set(sp, { opacity: 0 }); });   // hidden until each word's beat
        });
        break;
      }
      case "words-mask": { // masked rise: each word lifts through a clip window, power3.out
        els.forEach(function (el, i) {
          var spans = splitWords(el);
          if (!spans) { tl.fromTo(el, { opacity: 0, y: dist, clipPath: "inset(0% 0% 100% 0%)" }, { opacity: own(el), y: 0, clipPath: "inset(0% 0% -30% 0%)", duration: dur, ease: ease, immediateRender: true }, when(i)); return; }
          var st = Math.min(0.06, 0.45 / spans.length), words = spans.filter(function (sp) { return !sp.hasAttribute("data-motion-unit"); });
          if (words.length) tl.fromTo(words, { top: dist * 0.9, clipPath: "inset(100% 0% -30% 0%)" }, { top: 0, clipPath: "inset(-30% 0% -30% 0%)", duration: Math.max(0.35, dur), ease: cfg.ease, stagger: { each: st, from: beat.from || "start" }, immediateRender: true }, when(i));
          spans.forEach(function (sp, k) { if (sp.hasAttribute("data-motion-unit")) tl.fromTo(sp, { opacity: 0 }, { opacity: own(sp), duration: Math.max(0.35, dur), ease: cfg.ease, immediateRender: true }, when(i) + k * st); });
        });
        break;
      }

      case "lines-mask": { // the premium headline reveal: each rendered LINE lifts through a clip window, lines ~80 ms apart
        els.forEach(function (el, i) {
          var spans = splitLines(el);
          if (!spans) { tl.fromTo(el, { opacity: 0, y: dist, clipPath: "inset(0% 0% 100% 0%)" }, { opacity: own(el), y: 0, clipPath: "inset(0% 0% -30% 0%)", duration: dur, ease: ease, immediateRender: true }, when(i)); return; }
          var tops = [], lineOf = spans.map(function (sp) { var y = Math.round(sp.getBoundingClientRect().top / 4) * 4; var k = tops.indexOf(y); if (k < 0) { tops.push(y); k = tops.length - 1; } return k; });
          var st = Math.min(0.08, 0.45 / tops.length), ldur = Math.max(0.45, dur);
          spans.forEach(function (sp, k) {
            var t = when(i) + lineOf[k] * st;
            if (sp.hasAttribute("data-motion-unit")) tl.fromTo(sp, { opacity: 0 }, { opacity: own(sp), duration: ldur, ease: cfg.ease, immediateRender: true }, t);
            else tl.fromTo(sp, { top: dist * 1.2, clipPath: "inset(100% 0% -30% 0%)" }, { top: 0, clipPath: "inset(-30% 0% -30% 0%)", duration: ldur, ease: cfg.hero, immediateRender: true }, t);
          });
        });
        break;
      }

      // ── data ──
      case "grow-y":
        els.forEach(function (el, i) { tl.fromTo(el, { scaleY: 0, transformOrigin: "50% 100%" }, { scaleY: 1, duration: dur, ease: beat.ease || cfg.ease, immediateRender: true }, when(i)); }); break;
      case "grow-x":
        els.forEach(function (el, i) { tl.fromTo(el, { scaleX: 0, transformOrigin: "0% 50%" }, { scaleX: 1, duration: dur, ease: beat.ease || cfg.ease, immediateRender: true }, when(i)); }); break;
      case "draw":     // pen draw, segments overlapping ~75 %, power2.out; markers fade in with the stroke
        els.forEach(function (el, i) {
          var t = at + i * (stagger || dur * 0.25);
          var len = 0; try { len = el.getTotalLength ? el.getTotalLength() : 0; } catch (e) {}
          if (!len) { tl.fromTo(el, { opacity: 0 }, { opacity: own(el), duration: dur, ease: ease, immediateRender: true }, t); return; }
          var cs = getComputedStyle(el);
          var dash = cs.strokeDasharray && cs.strokeDasharray !== "none" ? cs.strokeDasharray : null;
          tl.fromTo(el, { opacity: 0 }, { opacity: own(el), duration: Math.max(0.12, dur * 0.35), ease: "power1.out", immediateRender: true }, t);
          if (dash) tl.fromTo(el, { strokeDasharray: "0 " + Math.ceil(len) }, { strokeDasharray: dash, duration: dur, ease: cfg.ease, immediateRender: true }, t);
          else tl.fromTo(el, { strokeDasharray: len, strokeDashoffset: len }, { strokeDashoffset: 0, duration: dur, ease: cfg.ease, immediateRender: true }, t);
          // An arrow marker renders at the path's end from the first frame, ahead of the stroke. Hold it
          // (own or inherited marker-end/-start) until the dash has landed; the attribute snapshot restores it.
          ["marker-end", "marker-start"].forEach(function (attr) {
            var has = false; for (var p = el; p && p.tagName.toLowerCase() !== "svg"; p = p.parentElement) { if (p.getAttribute && p.getAttribute(attr)) { has = true; break; } }
            if (!has) return;
            var ownVal = el.getAttribute(attr);
            tl.call(function () { el.setAttribute(attr, "none"); }, null, t);
            tl.call(function () { if (ownVal) el.setAttribute(attr, ownVal); else el.removeAttribute(attr); }, null, t + dur * 0.92);
          });
        });
        break;
      case "count-up": // the number counts AND grows: two tweens, same position, same ease (1.2–1.6 s reads as a number, not a flash)
        els.forEach(function (el, i) {
          var text = el.textContent, m = NUM_RE.exec(text), t = when(i);
          var cdur = Math.max(0.9, dur);   // 1.2–1.6 s reads as a number; 0.9 when three or more counters run one after another
          // Only a QUANTITY counts. An ordinal label ("01", "06", a bare "3" step number) is not a
          // statistic: it springs in like a mark instead, and never loses its zero padding.
          var isLabel = !m || /^0\d/.test(m[0]) || (text.trim() === m[0] && Math.abs(parseFloat(m[0])) <= 20 && m[0].indexOf(".") < 0);
          if (isLabel) { var b0 = base(gsap, el); tl.fromTo(el, { opacity: 0, scale: cfg.textScale ? 0.2 : 1, y: b0.y + (cfg.textScale ? 0 : 10), x: b0.x, transformOrigin: "50% 50%" }, { opacity: own(el), scale: 1, duration: Math.min(0.6, dur), ease: cfg.ease, immediateRender: true }, t); return; }
          var raw = m[0], target = parseFloat(raw.replace(/,/g, ""));
          var decimals = (raw.split(".")[1] || "").length, grouped = raw.indexOf(",") >= 0, width = raw.replace(/,/g, "").split(".")[0].length;
          var prefix = text.slice(0, m.index), suffix = text.slice(m.index + raw.length);
          var proxy = { v: 0 };
          function fmt(v) { var s2 = v.toFixed(decimals); var ip = s2.split(".")[0]; while (ip.length < width) ip = "0" + ip; s2 = ip + (decimals ? "." + s2.split(".")[1] : "");
            if (grouped) { var pp = s2.split("."); pp[0] = pp[0].replace(/\B(?=(\d{3})+(?!\d))/g, ","); s2 = pp.join("."); } return s2; }
          tl.set(el, { fontVariantNumeric: "tabular-nums" }, t);
          tl.fromTo(proxy, { v: 0 }, { v: target, duration: cdur, ease: cfg.ease, immediateRender: true,
            onUpdate: function () { el.textContent = prefix + fmt(proxy.v) + suffix; }, onComplete: function () { el.textContent = text; } }, t);
          if (cfg.textScale) tl.fromTo(el, { opacity: 0, scale: 0.55, transformOrigin: "0% 100%" }, { opacity: own(el), scale: 1, duration: cdur, ease: cfg.ease, immediateRender: true }, t);
          else tl.fromTo(el, { opacity: 0, y: 10 }, { opacity: own(el), y: 0, duration: Math.min(0.5, cdur), ease: cfg.ease, immediateRender: true }, t);
        });
        break;

      // ── scene primitives (director-authored stories) ──
      case "enter-from": {   // arrive from off-canvas: the whole group travels together and settles
        var root = document.getElementById("slide"), rb = root.getBoundingClientRect(), sc = rb.width / 1920 || 1;
        // one distance for the whole beat: the group travels together (an icon <g> measured in its own
        // local units would otherwise move a fraction of the distance and arrive out of step)
        var froms = els.map(function (el) {
          // measured on screen against the SLIDE edge (an SVG may sit inside padding), then
          // converted to the element's own units (SVG user units or slide CSS px)
          var r = el.getBoundingClientRect(), k = sc;
          if (el.ownerSVGElement) { var vb = el.ownerSVGElement.viewBox.baseVal, sr = el.ownerSVGElement.getBoundingClientRect();
            k = vb && vb.width ? sr.width / vb.width : sc; }
          var px = beat.dir === "right" ? (rb.right - r.left) : beat.dir === "down" ? -(r.bottom - rb.top) : beat.dir === "up" ? (rb.bottom - r.top) : -(r.right - rb.left);
          return (px + (px < 0 ? -40 : 40) * sc) / (k || 1);
        });
        var farthest = froms.reduce(function (m, f) { return Math.abs(f) > Math.abs(m) ? f : m; }, 0);
        els.forEach(function (el, i) {
          var from = farthest;
          var vert = beat.dir === "up" || beat.dir === "down", b0 = base(gsap, el);
          var fromV = vert ? { x: b0.x, y: b0.y + from } : { x: b0.x + from, y: b0.y };
          var toV = vert ? { x: b0.x, y: b0.y } : { x: b0.x, y: b0.y };
          tl.fromTo(el, Object.assign({ opacity: own(el) }, fromV), Object.assign({ duration: dur, ease: beat.ease || cfg.ease, immediateRender: true }, toV), at + i * stagger);
        });
        break;
      }
      case "pulse":   // a visited node acknowledges: a scale pulse on a shape, a nudge on anything carrying text (no scale on text)
        if (!cfg.textScale) break;   // corporate / premium: a landed element never moves or blinks — the story reads through order
        els.forEach(function (el, i) {
          tl.to(el, { scale: +beat.scale || 1.1, transformOrigin: "50% 50%", duration: dur / 2, ease: cfg.ease }, when(i));
          tl.to(el, { scale: 1, duration: dur / 2, ease: cfg.move }, when(i) + dur / 2); }); break;
      case "travel": {  // a token born behind `sel` travels to each waypoint (curved legs), visits it, may leave a trace, then fades
        // Options: `visitEffect: "spring"` (onVisit elements spring into existence instead of fading);
        // `via` (waypoint indices the token passes THROUGH without stopping: no dwell, no
        // pulse, no trace); `curve: "ring"` (legs run round a hub in polar coordinates, so a tour of
        // a circular arrangement reads as going round the circle instead of bowing alternately);
        // `center` ([x, y] in SVG units; default: centroid of the stopping waypoints); `orbit`
        // ("inner" | "outer" | "through": the token touches each stop on its edge facing / away from
        // the hub instead of covering its centre and label).
        var src = els[0]; if (!src || !src.ownerSVGElement) break;
        var svg = src.ownerSVGElement;
        // `along`: ride an EXISTING path/line element from its start to its end (a drawn spoke, a
        // pipeline connector) instead of hopping between waypoints; `onVisit[0]` reveals at the end.
        if (beat.along) {
          var road = beat._along || resolve(beat.along)[0];
          if (road && road.getTotalLength && window.MotionPathPlugin) {
            var p0 = road.getPointAtLength(0);
            var tk = document.createElementNS("http://www.w3.org/2000/svg", "circle");
            tk.setAttribute("cx", p0.x); tk.setAttribute("cy", p0.y); tk.setAttribute("r", +beat.r || 10);
            tk.setAttribute("fill", beat.fill || src.getAttribute("fill") || "currentColor"); tk.setAttribute("data-motion-token", "");
            if (beat.stroke) { tk.setAttribute("stroke", beat.stroke); tk.setAttribute("stroke-width", "3"); }
            road.parentNode.insertBefore(tk, road.nextSibling); created.push(tk);
            var ta = at, ride = Math.max(0.3, +beat.dur || 0.8);
            tl.fromTo(tk, { scale: 0, opacity: 0, transformOrigin: "50% 50%" }, { scale: 1, opacity: 1, duration: 0.25, ease: cfg.ease, immediateRender: true }, ta);
            tl.to(tk, { motionPath: { path: road, align: road, alignOrigin: [0.5, 0.5] }, duration: ride, ease: beat.ease || cfg.move }, ta + 0.25);
            ta += 0.25 + ride;
            (beat._visits || (Array.isArray(beat.onVisit) ? beat.onVisit.map(function (v) { return v ? resolve(v) : null; }) : [])).forEach(function (v) {
              (v || []).forEach(function (el) { remember(el);
                if (beat.visitEffect === "spring" && cfg.textScale) tl.fromTo(el, { opacity: 0, scale: 0.3, transformOrigin: "50% 50%" }, { opacity: own(el), scale: 1, duration: 0.4, ease: cfg.ease, immediateRender: true }, ta - 0.05);
                else if (beat.visitEffect === "spring") tl.fromTo(el, { opacity: 0, y: "+=10" }, { opacity: own(el), y: "-=10", duration: 0.4, ease: cfg.ease, immediateRender: true }, ta - 0.05);
                else tl.fromTo(el, { opacity: 0 }, { opacity: own(el), duration: 0.35, ease: cfg.ease, immediateRender: true }, ta); }); });
            if (beat.end !== "stay") tl.to(tk, { opacity: 0, scale: 0.6, duration: 0.3, ease: "power2.in" }, ta + 0.1);
            return n;
          }
        }
        var centerOf = function (el) { if (el.tagName.toLowerCase() === "circle") return { x: +el.getAttribute("cx"), y: +el.getAttribute("cy") };
          var bb = el.getBBox(); return { x: bb.x + bb.width / 2, y: bb.y + bb.height / 2 }; };
        var radiusOf = function (el) { if (el.tagName.toLowerCase() === "circle") return +el.getAttribute("r") || 0;
          var bb = el.getBBox(); return Math.min(bb.width, bb.height) / 2; };
        var start = centerOf(src);
        var via = Array.isArray(beat.via) ? beat.via.map(Number) : [];
        var wps = [];
        (beat._wps || (beat.waypoints || []).map(function (w) { return w ? resolve(w)[0] : null; })).forEach(function (el, k) { if (el) wps.push({ el: el, k: k, via: via.indexOf(k) >= 0 }); });
        if (!wps.length) break;
        var ring = beat.curve === "ring", hub = null;
        if (ring || (beat.orbit && beat.orbit !== "through")) {
          if (Array.isArray(beat.center) && beat.center.length === 2) hub = { x: +beat.center[0], y: +beat.center[1] };
          else { var real = wps.filter(function (w) { return !w.via; }); if (!real.length) real = wps;
            var sx = 0, sy = 0; real.forEach(function (w) { var c0 = centerOf(w.el); sx += c0.x; sy += c0.y; });
            hub = { x: sx / real.length, y: sy / real.length }; }
        }
        var pointOf = function (w) { var c0 = centerOf(w.el);
          if (!hub || w.via || !beat.orbit || beat.orbit === "through") return c0;
          var ux = c0.x - hub.x, uy = c0.y - hub.y, U = Math.hypot(ux, uy) || 1, rr = radiusOf(w.el) * (beat.orbit === "inner" ? -1 : 1);
          return { x: c0.x + ux / U * rr, y: c0.y + uy / U * rr }; };
        // the points of one leg, a (excluded) → b (included)
        var segment = function (a, b2, legNo) {
          if (ring) {
            var a0 = Math.atan2(a.y - hub.y, a.x - hub.x), a1 = Math.atan2(b2.y - hub.y, b2.x - hub.x);
            var r0 = Math.hypot(a.x - hub.x, a.y - hub.y), r1 = Math.hypot(b2.x - hub.x, b2.y - hub.y), da = a1 - a0;
            while (da > Math.PI) da -= 2 * Math.PI; while (da < -Math.PI) da += 2 * Math.PI;
            var ns = Math.max(2, Math.ceil(Math.abs(da) / (Math.PI / 18))), pts = [];
            for (var q = 1; q <= ns; q++) { var f = q / ns, an = a0 + da * f, rq = r0 + (r1 - r0) * f; pts.push({ x: hub.x + Math.cos(an) * rq, y: hub.y + Math.sin(an) * rq }); }
            return pts;
          }
          // an arc, not a straight line: bow the leg perpendicular to its direction (Disney: arcs)
          var vx = b2.x - a.x, vy = b2.y - a.y, L = Math.hypot(vx, vy) || 1, bow = Math.min(60, L * 0.18) * (legNo % 2 ? -1 : 1);
          return [{ x: (a.x + b2.x) / 2 - vy / L * bow, y: (a.y + b2.y) / 2 + vx / L * bow }, b2];
        };
        var token = document.createElementNS("http://www.w3.org/2000/svg", "circle");
        token.setAttribute("cx", start.x); token.setAttribute("cy", start.y); token.setAttribute("r", +beat.r || Math.max(8, (+src.getAttribute("r") || 40) * 0.4));
        var fill = beat.fill || src.getAttribute("fill") || "currentColor";
        token.setAttribute("fill", fill); token.setAttribute("data-motion-token", "");
        if (beat.stroke) { token.setAttribute("stroke", beat.stroke); token.setAttribute("stroke-width", "3"); }
        src.parentNode.insertBefore(token, src);          // born BEHIND the source
        created.push(token);
        var t = at, leg = Math.max(0.25, +beat.leg || 0.55), dwell = Math.max(0, +beat.dwell || 0.3);
        tl.fromTo(token, { scale: 0, opacity: 0, transformOrigin: "50% 50%" }, { scale: 1, opacity: 1, duration: 0.35, ease: cfg.ease, immediateRender: true }, t);
        t += 0.4;
        var from = start, cur = start, pts = [], segs = 0, legNo = 0;
        wps.forEach(function (w, idx) {
          var c = pointOf(w);
          pts = pts.concat(segment(cur, c, legNo)); segs += 1; cur = c;
          if (w.via && idx < wps.length - 1) return;      // pass through: the next stop continues the same motion
          var rel = [{ x: from.x - start.x, y: from.y - start.y }].concat(pts.map(function (p) { return { x: p.x - start.x, y: p.y - start.y }; }));
          var d = leg * (1 + 0.6 * (segs - 1));
          if (window.MotionPathPlugin) {
            tl.to(token, { motionPath: { path: rel, curviness: ring ? 1 : 1.25 }, duration: d, ease: cfg.move }, t);
          } else if (rel.length === 3) {
            tl.to(token, { keyframes: [{ x: rel[1].x, y: rel[1].y, duration: d / 2, ease: "power1.in" }, { x: rel[2].x, y: rel[2].y, duration: d / 2, ease: "power1.out" }] }, t);
          } else {
            tl.to(token, { keyframes: rel.slice(1).map(function (p) { return { x: p.x, y: p.y, duration: d / (rel.length - 1), ease: "none" }; }) }, t);
          }
          t += d; legNo += 1; pts = []; segs = 0; from = c;
          if (w.via) return;
          // the visit: the island acknowledges, a trace stays behind
          var stop = w.el, springIn = beat.visitEffect === "spring";
          remember(stop);
          if (!springIn) {   // with visitEffect "spring" the reveal itself is the acknowledgement
            if (cfg.textScale) { tl.to(stop, { scale: 1.08, transformOrigin: "50% 50%", duration: 0.16, ease: cfg.ease }, t - 0.05); tl.to(stop, { scale: 1, duration: 0.22, ease: cfg.move }, t + 0.11); }
            // (where nothing may scale, the visit is acknowledged by the trace it leaves, nothing more)
          }
          if (beat.trail !== false) {
            var mark = document.createElementNS("http://www.w3.org/2000/svg", "circle");
            mark.setAttribute("cx", c.x); mark.setAttribute("cy", c.y); mark.setAttribute("r", Math.max(4, (+token.getAttribute("r")) * 0.45));
            mark.setAttribute("fill", fill); mark.setAttribute("data-motion-token", "");
            if (beat.stroke) { mark.setAttribute("stroke", beat.stroke); mark.setAttribute("stroke-width", "2"); }
            svg.appendChild(mark); created.push(mark);
            tl.fromTo(mark, { opacity: 0, scale: 0.4, transformOrigin: "50% 50%" }, { opacity: +beat.trailOpacity || 0.55, scale: 1, duration: 0.3, ease: cfg.ease, immediateRender: true }, t);
          }
          var visits = beat._visits || (Array.isArray(beat.onVisit) ? beat.onVisit.map(function (v) { return v ? resolve(v) : null; }) : []);
          if (visits[w.k] && visits[w.k].length) {
            // what the visit brings into existence; hidden from build (immediateRender) until the token reaches it.
            // visitEffect "spring": scale 0.3 → 1 with the fade, power3.out — the token leaves the node behind.
            visits[w.k].forEach(function (el) { remember(el); var o = own(el);
              if (springIn) { var b1 = base(gsap, el);
                if (cfg.textScale) tl.fromTo(el, { opacity: 0, scale: 0.3, x: b1.x, y: b1.y, transformOrigin: "50% 50%" }, { opacity: o, scale: 1, x: b1.x, y: b1.y, duration: 0.4, ease: cfg.ease, immediateRender: true }, t - 0.05);
                else tl.fromTo(el, { opacity: 0, x: b1.x, y: b1.y + 10 }, { opacity: o, x: b1.x, y: b1.y, duration: 0.4, ease: cfg.ease, immediateRender: true }, t - 0.05);
              } else tl.fromTo(el, { opacity: 0 }, { opacity: o, duration: 0.35, ease: cfg.ease, immediateRender: true }, t + 0.05); });
          }
          t += dwell;
        });
        if (beat.end !== "stay") tl.to(token, { opacity: 0, scale: 0.6, duration: 0.4, ease: "power2.in" }, t);
        break;
      }

      // ── emphasis (the last beat) ──
      // The point is made FROM THE LANDED STATE: two `to` tweens (out, then back to rest). A fromTo
      // here re-applied its from-state to an element that had already landed and animated it back —
      // the "jumps up / shakes / zooms at the end" Roman saw on nine slides (2026-10-10). Never a
      // from-state on an emphasis.
      case "lift": case "settle": case "pop":
        // corporate / premium (textScale off): NO gesture — the point is made by order and stillness
        // (the choreographer lands the focal element last, after a hold). Any movement of a landed
        // element reads as a shake (Roman, 2026-10-10, nine slides). The nudge stays for personalities
        // that allow text to scale.
        if (cfg.textScale) els.forEach(function (el, i) { nudge(gsap, tl, el, when(i), dur, cfg, beat.effect === "settle" ? 4 : 6); }); break;
      case "focus-pull": { // depth of field: everything already on stage blurs and dims for a beat while the focal element(s) stay sharp, then refocuses
        if (!els.length) break;
        var isFocal = function (e) { return els.some(function (f) { return e === f || e.contains(f) || f.contains(e); }); };
        var ctx = [];
        originals.forEach(function (o) { var e = o.el; if (isFocal(e) || e.tagName === "SPAN" && e.style.display === "inline-block") return; if (ctx.indexOf(e) < 0) ctx.push(e); });
        ctx = ctx.filter(function (e) { return !ctx.some(function (o) { return o !== e && o.contains(e); }); });   // outermost only
        if (!cfg.blur || spec.focusPull === "off") {   // no defocus allowed: the point is made by order and stillness (a nudge only where text may scale)
          if (cfg.textScale) els.forEach(function (el, i) { nudge(gsap, tl, el, when(i), dur, cfg, 6); });
          break;
        }
        var hold = Math.max(0.5, dur), fpBlur = Math.min(BLUR_MAX, Math.max(1.5, (+beat.blur || 5) * cfg.blur)), dim = 1 - (1 - (+beat.dim || 0.55)) * cfg.blur;
        // dim through the filter, not the opacity property: an element still in an earlier beat's
        // from-state at build time (opacity 0) would otherwise "refocus" to invisible
        ctx.forEach(function (e) {
          tl.fromTo(e, { filter: "blur(0px) opacity(1)" }, { filter: "blur(" + fpBlur + "px) opacity(" + dim + ")", duration: 0.45, ease: cfg.move, immediateRender: false }, at);
          tl.to(e, { filter: "blur(0px) opacity(1)", duration: 0.6, ease: cfg.ease }, at + 0.45 + hold); });
        // scene scaffolding (tokens, trail marks) is not part of the resting slide: it dissolves with the pull
        created.forEach(function (n) { tl.to(n, { opacity: 0, duration: 0.45, ease: cfg.move }, at); });
        break;
      }
      default:
        els.forEach(function (el, i) { tl.fromTo(el, { opacity: 0 }, { opacity: own(el), duration: dur, ease: ease, immediateRender: true }, when(i)); });
    }
    return n;
  }

  // ── build ─────────────────────────────────────────────────────────────────
  var building = null;
  function build(opts) {
    opts = opts || {};
    if (api.built) return Promise.resolve(api.info);
    if (building) return building;
    if (isStatic && !opts.force) return Promise.resolve(null);
    var needsPath = spec.beats.some(function (b) { return b.effect === "travel"; });
    building = domReady().then(stylesReady).then(loadGsap).then(function (gsap) {
      return needsPath ? loadMotionPath().then(function () { return gsap; }) : gsap;
    }).then(function (gsap) {
      var k = typeof spec.intensity === "number" ? spec.intensity : 1;   // dark slides: 0.85 — travel and defocus read brighter on a projector
      var cfg = {
        // blur dial: how much defocus the pack allows — "none" 0 · "subtle" 0.4 · "full" 1 (Roman, 2026-10-04: "too much blur")
        blur: (spec.blur === "none" ? 0 : spec.blur === "full" ? 1 : 0.4) * k,
        // ONE motion language per deck (1.6.0): the arrival ease, the hero ease (title-card gestures,
        // kinetic text) and the move ease (on-screen travel). Variety is in the gesture, never the curve.
        ease: (spec.easing && spec.easing["in"]) || "power3.out",
        hero: (spec.easing && spec.easing.hero) || "power4.out",
        move: (spec.easing && spec.easing.move) || "power2.inOut",
        distancePx: (typeof spec.distancePx === "number" ? spec.distancePx : 24) * k,
        // scale budget: a scaled TEXT element re-rasterises every frame and snaps to crisp pixels when
        // the scale ends — the "flicker at the end of the motion" (Roman, 2026-10-10). textScale false
        // (corporate, premium): no transform-scale ever touches text; shapes settle from scaleIn.
        scaleIn: (spec.scale && typeof spec.scale["in"] === "number") ? spec.scale["in"] : 0.94,
        heroScale: (spec.scale && typeof spec.scale.hero === "number") ? spec.scale.hero : 1.12,
        textScale: !!(spec.scale && spec.scale.textScale),
      };
      cfg.easeIn = cfg.ease;
      // Idle motion lives in its own paused timeline: camera push toward the emphasis, drift on
      // the washes, a breath on the hero. It starts when the entrance completes and is killed +
      // restored by toEnd(), so the slide at rest (export, QA, going back) is the static slide.
      preResolve(spec);
      var idleTl = gsap.timeline({ paused: true });
      (spec.idle || []).forEach(function (b) { addIdle(gsap, idleTl, b, cfg); (b._els || []).forEach(function (e) { idleEls.push(e); }); });
      // the camera wrapper is an idle target too
      (spec.idle || []).forEach(function (b) { if (b.effect === "camera") { var tg = (b._els || [])[0], w = tg && cameraRootFor(tg); if (w) idleEls.push(w); } });
      api.idle = idleTl;
      var tl = gsap.timeline({ paused: true, onComplete: function () {
        // the entrance is over: everything goes back to the static DOM now (the split markup, the
        // transforms), except what the idle timeline keeps driving until the slide is left
        if (idleTl.getChildren().length && !isStatic) { restoreAll({ exceptIdle: true }); idleTl.play(0); } else restoreAll();
        post({ type: "complete" });
      } });
      var resolved = [], steps = 0;
      var stepBefore = {};
      (spec.steps || []).forEach(function (st) { (st.beats || []).forEach(function (id, i) { if (i === 0) stepBefore[id] = true; }); });
      spec.beats.forEach(function (beat) {
        if (stepBefore[beat.id]) {
          // Hold here until the presenter asks for the next step. addPause fires only during
          // playback, so progress(1)/toEnd() still jumps straight to the end state.
          tl.addPause(Math.max(0, +beat.at || 0), function () { api.stepsDone += 1; post({ type: "step", remaining: api.stepsRemaining() }); });
          steps += 1;
        }
        var n = addBeat(gsap, tl, beat, cfg);
        resolved.push({ id: beat.id, role: beat.role, effect: beat.effect, n: n });
      });
      api.tl = tl; api.steps = steps; api.built = true;
      window.__timelines[spec.file || location.pathname.split("/").pop()] = tl;
      tl.progress(0);           // from-states applied → safe to show
      if (seekT !== null) { tl.pause(); tl.time(Math.min(seekT, tl.duration()), true); }   // ?t= — a frozen frame, no autoplay
      unveil();
      api.info = { total_ms: Math.round(tl.duration() * 1000), steps: steps, resolved: resolved, static: isStatic };
      post({ type: "ready", total_ms: api.info.total_ms, steps: steps, static: isStatic });
      return api.info;
    }).catch(function (err) {
      // No GSAP (offline) or a broken spec: the slide must still be readable.
      unveil(); restoreAll();
      api.info = { error: String(err && err.message || err), total_ms: 0, steps: 0, resolved: [], static: isStatic };
      post({ type: "ready", total_ms: 0, steps: 0, static: isStatic, error: api.info.error });
      return api.info;
    });
    return building;
  }
  // Idle effects. `sel` names the focal element; the camera moves the slide's content wrapper
  // (the #slide child that contains it), never #slide itself (its transform is the scaler's).
  function cameraRootFor(el) {
    var root = document.getElementById("slide"); if (!root) return null;
    var node = el;
    while (node && node.parentElement !== root) node = node.parentElement;
    return node && node !== root ? node : null;
  }
  function addIdle(gsap, tl, b, cfg) {
    var dur = Math.max(1, (+b.dur || 7000) / 1000);
    switch (b.effect) {
      case "camera": {
        var target = (b._els || resolve(b.sel))[0]; if (!target) return;
        var wrap = cameraRootFor(target); if (!wrap) return;
        remember(wrap);
        var wb = wrap.getBoundingClientRect(), tb = target.getBoundingClientRect();
        var ox = ((tb.left + tb.width / 2 - wb.left) / Math.max(1, wb.width)) * 100;
        var oy = ((tb.top + tb.height / 2 - wb.top) / Math.max(1, wb.height)) * 100;
        ox = Math.max(15, Math.min(85, ox)); oy = Math.max(15, Math.min(85, oy));
        tl.fromTo(wrap, { scale: 1, transformOrigin: ox.toFixed(1) + "% " + oy.toFixed(1) + "%" },
                        { scale: +b.scale || 1.035, duration: dur, ease: "sine.inOut", immediateRender: false }, 0);
        break;
      }
      case "drift":
        (b._els || resolve(b.sel)).forEach(function (el, i) {
          remember(el);
          // layered floating: each wash on its own period and phase so nothing moves in lockstep;
          // the layer is promoted just in time (the attribute snapshot drops the hint on restore)
          var px = +b.px || 18, sgn = i % 2 ? -1 : 1, period = dur * [1, 1.35, 0.8][i % 3];
          tl.set(el, { willChange: "transform" }, 0);
          tl.to(el, { x: "+=" + (sgn * px), y: "+=" + (-sgn * px * 0.6), rotation: "+=" + (sgn * (+b.rot || 1.5)),
                      duration: period, ease: "sine.inOut", yoyo: true, repeat: 3, immediateRender: false }, i * 0.6);
        });
        break;
      case "breathe":
        (b._els || resolve(b.sel)).forEach(function (el) {
          remember(el);
          tl.fromTo(el, { scale: 1 }, { scale: +b.scale || 1.015, duration: dur, ease: "sine.inOut", yoyo: true, repeat: 3, immediateRender: false }, 0);
        });
        break;
    }
  }
  function stopIdle() { if (api.idle) { api.idle.pause(); api.idle.progress(0); } }
  function play() { if (api.tl && seekT === null) api.tl.play(); }
  function nextStep() { if (api.tl && api.tl.paused()) api.tl.play(); }
  function toEnd() {
    stopIdle();
    if (api.tl) { api.tl.pause(); api.tl.progress(1, true); }
    restoreAll(); api.stepsDone = api.steps;
  }
  function restart() { if (api.tl) { stopIdle(); restoreAll(); api.stepsDone = 0; api.tl.pause(); api.tl.progress(0); api.tl.play(); } }

  // ── wiring ────────────────────────────────────────────────────────────────
  if (isStatic) return;   // nothing else happens: no veil was added, DOM untouched

  window.addEventListener("message", function (e) {
    var m = e.data;
    if (!m || m.ns !== NS) return;
    switch (m.type) {
      case "play": build().then(play); break;
      case "next-step": nextStep(); break;
      case "to-end": build().then(toEnd); break;
      case "restart": build().then(restart); break;
      case "set-static":
        try {
          var u = new URL(location.href);
          if (m.value) u.searchParams.set("static", "1"); else u.searchParams.delete("static");
          location.replace(u.toString());
        } catch (err) {}
        break;
    }
  });
  if (embedded) {
    document.addEventListener("keydown", function (e) {
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      post({ type: "key", key: e.key, shiftKey: e.shiftKey });
      if (/^(Arrow|Page|Home|End| |Spacebar|Enter|Backspace)/.test(e.key) || e.key === " ") e.preventDefault();
    });
  }
  build().then(function () { if (!embedded) play(); });
})();
