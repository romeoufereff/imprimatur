/* imprimatur deck-motion — viewer runtime (copied into <deck>/motion/ by assemble_deck.py).
 *
 * Two stacked iframes (stage-a / stage-b). The active stage shows the current slide; the
 * other one preloads the next slide, hidden. Navigating runs a transition between the two
 * stage wrappers (WAAPI, no library) and swaps roles. Slides built with motion.js hold
 * their entrance until this viewer sends `play`, so a preloaded slide never animates
 * unseen; slides without motion.js simply appear.
 *
 * Parent ↔ slide protocol (postMessage, {ns:"imprimatur-motion", type, ...}, origin "*" —
 * local files, nothing secret):
 *   slide → viewer : ready{total_ms, steps, static} · key{key, shiftKey} · step{remaining} · complete
 *   viewer → slide : play · next-step · to-end · restart · set-static{value}
 *
 * Keys: → ↓ Space PageDown = next step if the slide has one left, else next slide ·
 *       ← ↑ PageUp = previous slide (shown in its end state) · Home / End ·
 *       digits + Enter = go to slide · F = fullscreen · S = toggle motion (persisted) ·
 *       ?static=1 on index.html forces the static deck.
 *
 * Config comes from window.__DECK written by assemble_deck.py:
 *   { slides: ["01-cover.html", …], transition: {type, durationMs}, easing: "cubic-bezier(…)|ease" }
 */
(function () {
  "use strict";
  var NS = "imprimatur-motion";
  var cfg = window.__DECK || {};
  var slides = cfg.slides || [];
  var transition = cfg.transition || { type: "crossfade", durationMs: 450 };
  var perSlide = cfg.transitions || {};        // {file: type} written by choreograph.py (template overrides)
  var DEFAULT_MS = { crossfade: 450, push: 500, "zoom-through": 550, "zoom-blur": 650, "whip-pan": 420, "light-leak": 700, "push-depth": 560, none: 0 };
  var leak = document.getElementById("leak");
  var BLUR = cfg.blur === "none" ? 0 : cfg.blur === "full" ? 1 : 0.4;
  // a whole-stage blur is the most expensive filter a page can run (1920×1080 layer): capped at 4 px whatever the dial
  var bl = function (px) { return "blur(" + Math.min(4, Math.round(px * BLUR)) + "px)"; };
  var easing = cfg.easing || "cubic-bezier(0.45, 0, 0.55, 1)";
  if (!slides.length) return;

  var params = new URLSearchParams(location.search);
  var staticMode = params.get("static") === "1";
  try { if (localStorage.getItem("imprimatur.motion") === "off") staticMode = true; } catch (e) { /* private window */ }

  var stages = [document.getElementById("stage-a"), document.getElementById("stage-b")];
  var frames = stages.map(function (s) { return s.querySelector("iframe"); });
  var counter = document.getElementById("counter");
  var motionBtn = document.getElementById("motion-toggle");
  var active = 0;       // index into stages/frames
  var current = 0;      // slide index
  var busy = false;
  var digits = "";
  var state = [newState(), newState()];   // per frame: what the slide reported

  function newState() { return { file: null, ready: false, steps: 0, remaining: 0, totalMs: 0, complete: false, loaded: false }; }
  function slideUrl(n) { return slides[n] + (staticMode ? "?static=1" : ""); }
  function post(frame, msg) {
    try { frame.contentWindow.postMessage(Object.assign({ ns: NS }, msg), "*"); } catch (e) { /* not loaded yet */ }
  }
  function setCounter() { if (counter) counter.textContent = (current + 1) + " / " + slides.length; }

  // ── loading ────────────────────────────────────────────────────────────────
  function load(idx, n) {
    var f = frames[idx];
    var st = state[idx] = newState();
    st.file = slides[n];
    return new Promise(function (resolve) {
      var done = false;
      function finish() { if (!done) { done = true; st.loaded = true; resolve(); } }
      f.addEventListener("load", finish, { once: true });
      setTimeout(finish, 2500);            // a frame that never fires load must not wedge the deck
      f.src = slideUrl(n);
    });
  }
  function preload(n) {
    if (n < 0 || n >= slides.length) return;
    var idle = 1 - active;
    if (state[idle].file === slides[n] && state[idle].loaded) return;
    load(idle, n);
  }

  // ── transitions (on the stage wrappers, never inside the slide) ───────────
  function animate(el, keyframes, ms) {
    if (!el.animate || ms <= 0) { Object.assign(el.style, keyframes[keyframes.length - 1]); return Promise.resolve(); }
    var a = el.animate(keyframes, { duration: ms, easing: easing, fill: "forwards" });
    return a.finished.catch(function () {}).then(function () { try { a.commitStyles(); a.cancel(); } catch (e) {} });
  }
  function transitionFor(inFile) {
    var type = staticMode ? "none" : (perSlide[inFile] || transition.type || "crossfade");
    var ms = staticMode ? 0 : (type === (transition.type || "crossfade") && transition.durationMs ? transition.durationMs : (DEFAULT_MS[type] || 500));
    return { type: type, ms: ms };
  }
  function runTransition(outStage, inStage, dir, inFile) {
    var tf = transitionFor(inFile), type = tf.type, ms = tf.ms;
    inStage.style.zIndex = 2; outStage.style.zIndex = 1;
    inStage.style.visibility = "visible";
    var sign = dir < 0 ? -1 : 1;
    switch (type) {
      case "zoom-blur":
        return Promise.all([
          animate(inStage, [{ transform: "scale(1.08)", opacity: 0, filter: bl(10) }, { transform: "scale(1)", opacity: 1, filter: "blur(0px)" }], ms),
          animate(outStage, [{ transform: "scale(1)", opacity: 1, filter: "blur(0px)" }, { transform: "scale(0.96)", opacity: 0, filter: bl(6) }], ms * 0.85),
        ]);
      case "whip-pan":
        return Promise.all([
          animate(inStage, [{ transform: "translateX(" + (sign * 45) + "%)", opacity: 0.4, filter: bl(12) }, { transform: "translateX(0)", opacity: 1, filter: "blur(0px)" }], ms),
          animate(outStage, [{ transform: "translateX(0)", opacity: 1, filter: "blur(0px)" }, { transform: "translateX(" + (-sign * 45) + "%)", opacity: 0, filter: bl(12) }], ms),
        ]);
      case "push-depth":
        return Promise.all([
          animate(inStage, [{ transform: "translateX(" + (sign * 100) + "%)", opacity: 1 }, { transform: "translateX(0)", opacity: 1 }], ms),
          animate(outStage, [{ transform: "scale(1)", opacity: 1, filter: "brightness(1)" }, { transform: "scale(0.94)", opacity: 0.6, filter: "brightness(0.7)" }], ms),
        ]);
      case "light-leak":
        if (leak) animate(leak, [{ opacity: 0 }, { opacity: 0.95, offset: 0.45 }, { opacity: 0 }], ms * 1.1);
        return Promise.all([
          animate(inStage, [{ opacity: 0, transform: "scale(1.02)" }, { opacity: 1, transform: "scale(1)" }], ms),
          animate(outStage, [{ opacity: 1 }, { opacity: 0 }], ms * 0.6),
        ]);
      case "push":
        return Promise.all([
          animate(inStage, [{ transform: "translateX(" + (sign * 100) + "%)", opacity: 1 }, { transform: "translateX(0)", opacity: 1 }], ms),
          animate(outStage, [{ transform: "translateX(0)", opacity: 1 }, { transform: "translateX(" + (-sign * 100) + "%)", opacity: 1 }], ms),
        ]);
      case "zoom-through":
        return Promise.all([
          animate(inStage, [{ transform: "scale(1.06)", opacity: 0 }, { transform: "scale(1)", opacity: 1 }], ms),
          animate(outStage, [{ transform: "scale(1)", opacity: 1 }, { transform: "scale(0.96)", opacity: 0 }], ms),
        ]);
      case "none":
        inStage.style.opacity = 1; inStage.style.transform = "none";
        return Promise.resolve();
      case "crossfade":
      default:
        return animate(inStage, [{ opacity: 0, transform: "none" }, { opacity: 1, transform: "none" }], ms);
    }
  }
  function hide(stage) {
    stage.style.opacity = 0; stage.style.visibility = "hidden"; stage.style.transform = "none"; stage.style.filter = "none"; stage.style.zIndex = 0;
  }

  // ── navigation ────────────────────────────────────────────────────────────
  function go(n, dir) {
    n = Math.max(0, Math.min(slides.length - 1, n));
    if (busy || n === current) return;
    busy = true;
    var dirSign = dir || (n > current ? 1 : -1);
    var idle = 1 - active;
    var ready = (state[idle].file === slides[n] && state[idle].loaded) ? Promise.resolve() : load(idle, n);
    ready.then(function () {
      var inF = frames[idle];
      // Forward: the slide constructs itself as it arrives — but not UNDER the cut. `play` goes out
      // when the transition is ~70 % done, so the hero lands as the stage settles (1.5.x sent it at
      // 0 and the first half second of the entrance played behind a zoom-blur; entrance–exit
      // continuity wants a 100–150 ms overlap, no more). Backward: shown finished.
      if (dirSign > 0) {
        var wait = Math.round(transitionFor(slides[n]).ms * 0.7);
        if (wait > 0) setTimeout(function () { post(inF, { type: "play" }); }, wait); else post(inF, { type: "play" });
      } else post(inF, { type: "to-end" });
      return runTransition(stages[active], stages[idle], dirSign, slides[n]);
    }).then(function () {
      hide(stages[active]);
      active = idle; current = n;
      setCounter();
      busy = false;
      preload(current + 1);
      try { window.focus(); } catch (e) {}
    });
  }
  function forward() {
    var st = state[active];
    if (!staticMode && st.remaining > 0) { post(frames[active], { type: "next-step" }); st.remaining -= 1; return; }
    go(current + 1, 1);
  }
  function back() { go(current - 1, -1); }

  function toggleMotion() {
    staticMode = !staticMode;
    try { localStorage.setItem("imprimatur.motion", staticMode ? "off" : "on"); } catch (e) {}
    if (motionBtn) motionBtn.textContent = staticMode ? "Motion: off" : "Motion: on";
    // Reload both frames in the new mode; the active one lands in its end state.
    state = [newState(), newState()];
    load(active, current).then(function () { post(frames[active], { type: "to-end" }); });
    preload(current + 1);
  }
  function fullscreen() {
    var el = document.documentElement;
    if (document.fullscreenElement) { document.exitFullscreen && document.exitFullscreen(); }
    else if (el.requestFullscreen) { el.requestFullscreen(); }
  }

  function onKey(key, shift) {
    if (/^[0-9]$/.test(key)) { digits = (digits + key).slice(-3); return; }
    if (key === "Enter" && digits) { var n = parseInt(digits, 10) - 1; digits = ""; go(n); return; }
    digits = "";
    switch (key) {
      case "ArrowRight": case "ArrowDown": case "PageDown": case " ": case "Spacebar":
        if (shift) back(); else forward(); break;
      case "ArrowLeft": case "ArrowUp": case "PageUp": case "Backspace": back(); break;
      case "Home": go(0, -1); break;
      case "End": go(slides.length - 1, 1); break;
      case "f": case "F": fullscreen(); break;
      case "s": case "S": toggleMotion(); break;
      case "r": case "R": post(frames[active], { type: "restart" }); state[active].remaining = state[active].steps; break;
    }
  }

  document.addEventListener("keydown", function (e) {
    if (e.metaKey || e.ctrlKey || e.altKey) return;
    var handled = ["ArrowRight", "ArrowDown", "PageDown", " ", "Spacebar", "ArrowLeft", "ArrowUp", "PageUp",
                   "Backspace", "Home", "End", "Enter", "f", "F", "s", "S", "r", "R"];
    if (handled.indexOf(e.key) >= 0 || /^[0-9]$/.test(e.key)) e.preventDefault();
    onKey(e.key, e.shiftKey);
  });

  window.addEventListener("message", function (e) {
    var m = e.data;
    if (!m || m.ns !== NS) return;
    var idx = frames.indexOf(frames.filter(function (f) { return f.contentWindow === e.source; })[0]);
    if (idx < 0) return;
    var st = state[idx];
    switch (m.type) {
      case "ready":
        st.ready = true; st.steps = m.steps || 0; st.remaining = m.steps || 0; st.totalMs = m.total_ms || 0;
        if (idx === active) post(frames[idx], { type: "play" });   // a slide that became ready after we arrived
        break;
      case "step": st.remaining = typeof m.remaining === "number" ? m.remaining : st.remaining; break;
      case "complete": st.complete = true; break;
      case "key": if (idx === active) onKey(m.key, !!m.shiftKey); break;
    }
  });

  // ── buttons ───────────────────────────────────────────────────────────────
  window.deckNext = forward; window.deckPrev = back; window.deckGo = go;
  if (motionBtn) {
    motionBtn.textContent = staticMode ? "Motion: off" : "Motion: on";
    motionBtn.addEventListener("click", toggleMotion);
  }

  // ── boot ──────────────────────────────────────────────────────────────────
  hide(stages[1]);
  stages[0].style.visibility = "visible"; stages[0].style.opacity = 1; stages[0].style.zIndex = 2;
  setCounter();
  load(0, 0).then(function () { post(frames[0], { type: "play" }); preload(1); });
})();
