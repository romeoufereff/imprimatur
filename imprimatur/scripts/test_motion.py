#!/usr/bin/env python3
"""deck-motion gate — run from validate_all.sh (browser stage; skipped with --fast).

M1 (viewer):
  assemble_deck   a deck WITHOUT the §1 opt-in gets today's plain viewer byte-for-byte and
                  no motion/ folder; a deck WITH it gets the two-stage viewer + motion/viewer.js,
                  the pack's transition (deck override honoured), and deck-metadata records it.
  brief fallback  no deck-state `motion` field + a `- **Motion:** yes · zoom-through · steps`
                  line in deck-brief.md → motion viewer with those settings.
  viewer (browser) ArrowRight/ArrowLeft/Home/End move the counter and the active stage;
                  the next slide is preloaded in the idle stage; ?static=1 reaches the frames.

M2 (choreography + static equivalence) extends this file.

Usage:  python3 scripts/test_motion.py [--no-browser]
"""
import glob
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from ds_config import load  # noqa: E402
import assemble_deck  # noqa: E402

SLIDE = """<!DOCTYPE html><html><head><meta charset="utf-8"><title>s</title></head>
<body style="margin:0;background:#fff"><div id="slide" style="width:1920px;height:1080px;font:64px sans-serif">Slide {n}</div></body></html>
"""


def run(args, **kw):
    return subprocess.run([sys.executable] + args, capture_output=True, text=True, timeout=300, **kw)


def make_deck(root, ds, motion=None, brief_motion=None):
    deck = os.path.join(root, "deck")
    os.makedirs(deck)
    files = ["01-one.html", "02-two.html", "03-three.html"]
    for n, f in enumerate(files, 1):
        open(os.path.join(deck, f), "w", encoding="utf-8").write(SLIDE.format(n=n))
    state = {"deck": "Motion Test", "design_system": ds.root,
             "slides": [{"n": n, "file": f, "title": f, "status": "written", "template": "01-cover",
                         "visual": "none"} for n, f in enumerate(files, 1)]}
    if motion is not None:
        state["motion"] = motion
    json.dump(state, open(os.path.join(deck, "deck-state.json"), "w"), indent=2)
    brief = ["# Deck Brief — Motion Test", "", "## Intake", "- **Audience:** executive",
             "- **Outcome:** pitch", "- **Length:** 3 slides", "- **Context:** test"]
    if brief_motion:
        brief.append(f"- **Motion:** {brief_motion}")
    open(os.path.join(deck, "deck-brief.md"), "w", encoding="utf-8").write("\n".join(brief) + "\n")
    return deck, files


def main():
    no_browser = "--no-browser" in sys.argv
    results = []

    def check(name, ok, detail=""):
        results.append(bool(ok))
        print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  {str(detail)[:400]}" if detail and not ok else ""))

    ds = load()
    check("pack declares a motion block (motion_enabled)", ds.motion_enabled(),
          "this pack has no `motion` block — the M1 tests need one")
    pack_t = ds.motion()["transition"]["type"]

    with tempfile.TemporaryDirectory() as tmp:
        # ── disabled deck: plain viewer, byte-identical to build_index_html ──
        deck, files = make_deck(os.path.join(tmp, "off"), ds, motion={"enabled": False})
        p = run([os.path.join(HERE, "assemble_deck.py"), "--deck-dir", deck])
        html = open(os.path.join(deck, "index.html"), encoding="utf-8").read()
        check("disabled deck: assemble_deck exits 0 and reports the plain viewer",
              p.returncode == 0 and "plain viewer" in p.stdout, p.stdout + p.stderr)
        check("disabled deck: index.html is the plain template byte-for-byte",
              html == assemble_deck.build_index_html("Motion Test", files))
        check("disabled deck: no motion/ folder, metadata motion.enabled=false",
              not os.path.isdir(os.path.join(deck, "motion"))
              and json.load(open(os.path.join(deck, "deck-metadata.json")))["motion"] == {"enabled": False})

        # ── no field, no brief line → still plain (default = no) ──
        deck0, _ = make_deck(os.path.join(tmp, "unset"), ds)
        run([os.path.join(HERE, "assemble_deck.py"), "--deck-dir", deck0])
        check("unanswered deck: default is the plain viewer",
              "viewer.js" not in open(os.path.join(deck0, "index.html"), encoding="utf-8").read())

        # ── brief fallback ──
        deck1, _ = make_deck(os.path.join(tmp, "brief"), ds, brief_motion="yes · zoom-through · steps")
        p = run([os.path.join(HERE, "assemble_deck.py"), "--deck-dir", deck1])
        cfg = open(os.path.join(deck1, "index.html"), encoding="utf-8").read()
        check("brief fallback: `Motion: yes · zoom-through · steps` selects the motion viewer with those settings",
              '"type": "zoom-through"' in cfg and '"steps": true' in cfg and "motion/viewer.js" in cfg,
              p.stdout + p.stderr)

        # ── enabled deck with a transition override ──
        deck, files = make_deck(os.path.join(tmp, "on"), ds, motion={"enabled": True, "transition": "push"})
        p = run([os.path.join(HERE, "assemble_deck.py"), "--deck-dir", deck])
        html = open(os.path.join(deck, "index.html"), encoding="utf-8").read()
        meta = json.load(open(os.path.join(deck, "deck-metadata.json")))
        check("enabled deck: assemble_deck reports the motion viewer", p.returncode == 0 and "motion viewer: push" in p.stdout,
              p.stdout + p.stderr)
        check("enabled deck: two stages + motion/viewer.js referenced, deck override wins over pack default",
              'id="stage-a"' in html and 'id="stage-b"' in html and 'src="motion/viewer.js"' in html
              and '"type": "push"' in html, f"pack default was {pack_t}")
        check("enabled deck: motion/viewer.js copied; metadata records motion",
              os.path.isfile(os.path.join(deck, "motion", "viewer.js"))
              and meta.get("motion", {}).get("enabled") is True and meta["motion"]["transition"] == "push")
        check("enabled deck: no new NN-*.html or *.html beside the slides (export globs untouched)",
              sorted(f for f in os.listdir(deck) if f.endswith(".html")) == sorted(files + ["index.html"]))

        if no_browser:
            print("(browser checks skipped)")
        else:
            try:
                from playwright.sync_api import sync_playwright
            except ImportError:
                check("playwright importable", False, "pip install playwright && python3 -m playwright install chromium")
                sync_playwright = None
            if sync_playwright:
                with sync_playwright() as pw:
                    browser = pw.chromium.launch()
                    page = browser.new_page(viewport={"width": 1280, "height": 720})
                    url = "file://" + os.path.join(deck, "index.html")
                    page.goto(url)
                    page.wait_for_function("document.getElementById('counter').textContent.trim() === '1 / 3'", timeout=5000)

                    def active_src():
                        return page.evaluate("""() => {
                            const st = [...document.querySelectorAll('.stage')]
                              .sort((a,b) => (parseInt(b.style.zIndex)||0) - (parseInt(a.style.zIndex)||0))[0];
                            return st.querySelector('iframe').getAttribute('src') || '';
                        }""")

                    def idle_src():
                        return page.evaluate("""() => {
                            const st = [...document.querySelectorAll('.stage')]
                              .sort((a,b) => (parseInt(a.style.zIndex)||0) - (parseInt(b.style.zIndex)||0))[0];
                            return st.querySelector('iframe').getAttribute('src') || '';
                        }""")
                    page.wait_for_function("document.querySelectorAll('.stage iframe')[1].getAttribute('src')", timeout=5000)
                    check("viewer: slide 1 active, slide 2 preloaded in the idle stage",
                          active_src().endswith("01-one.html") and idle_src().endswith("02-two.html"),
                          f"active={active_src()} idle={idle_src()}")
                    page.keyboard.press("ArrowRight")
                    page.wait_for_function("document.getElementById('counter').textContent.trim() === '2 / 3'", timeout=5000)
                    check("viewer: ArrowRight → 2 / 3 with slide 2 on the active stage", active_src().endswith("02-two.html"), active_src())
                    page.keyboard.press("ArrowRight")
                    page.wait_for_function("document.getElementById('counter').textContent.trim() === '3 / 3'", timeout=5000)
                    page.keyboard.press("ArrowRight")  # past the end: stays
                    page.wait_for_timeout(300)
                    check("viewer: ArrowRight at the last slide stays on 3 / 3",
                          page.inner_text("#counter").strip() == "3 / 3" and active_src().endswith("03-three.html"))
                    page.keyboard.press("ArrowLeft")
                    page.wait_for_function("document.getElementById('counter').textContent.trim() === '2 / 3'", timeout=5000)
                    check("viewer: ArrowLeft → 2 / 3", active_src().endswith("02-two.html"), active_src())
                    page.keyboard.press("Home")
                    page.wait_for_function("document.getElementById('counter').textContent.trim() === '1 / 3'", timeout=5000)
                    page.keyboard.press("End")
                    page.wait_for_function("document.getElementById('counter').textContent.trim() === '3 / 3'", timeout=5000)
                    check("viewer: Home / End jump to the first / last slide", active_src().endswith("03-three.html"))
                    page.keyboard.type("2")
                    page.keyboard.press("Enter")
                    page.wait_for_function("document.getElementById('counter').textContent.trim() === '2 / 3'", timeout=5000)
                    check("viewer: digits + Enter go to that slide", active_src().endswith("02-two.html"))
                    visible = page.evaluate("""() => [...document.querySelectorAll('.stage')]
                        .filter(s => getComputedStyle(s).visibility === 'visible' && parseFloat(getComputedStyle(s).opacity) > 0.99).length""")
                    check("viewer: exactly one stage visible after a transition", visible == 1, f"visible stages: {visible}")
                    page.goto(url + "?static=1")
                    page.wait_for_function("document.querySelectorAll('.stage iframe')[0].getAttribute('src')", timeout=5000)
                    check("viewer: ?static=1 propagates to the slide frames", "static=1" in active_src(), active_src())
                    errors = []
                    page.on("pageerror", lambda e: errors.append(str(e)))
                    page.keyboard.press("ArrowRight")
                    page.wait_for_function("document.getElementById('counter').textContent.trim() === '2 / 3'", timeout=5000)
                    check("viewer: no page errors in static mode", not errors, errors)
                    browser.close()

    # ══ M2 · choreography on a real deck ═══════════════════════════════════════
    import hashlib
    import choreograph
    with tempfile.TemporaryDirectory() as tmp:
        deck = os.path.join(tmp, "deck")
        os.makedirs(deck)
        plan = [(1, "01-cover", "cover"), (2, "08-product-cards", "cards"), (3, "12-process-flow-diagram", "flow")]
        files = []
        for n, tpl, slug in plan:
            p = run([os.path.join(HERE, "new_slide.py"), "--deck-dir", deck, "--template", tpl, "--n", str(n), "--slug", slug])
            if p.returncode != 0:
                check(f"new_slide {tpl}", False, p.stderr[-300:])
            files.append(f"{n:02d}-{slug}.html")
        state = {"deck": "Motion M2", "design_system": ds.root, "motion": {"enabled": True, "transition": "crossfade"},
                 "slides": [{"n": n, "file": f, "title": f, "status": "written", "template": tpl, "visual": "none"}
                            for (n, tpl, _), f in zip(plan, files)]}
        json.dump(state, open(os.path.join(deck, "deck-state.json"), "w"), indent=2)
        open(os.path.join(deck, "narrative-outline.md"), "w", encoding="utf-8").write("\n".join([
            "# Narrative Outline — Motion M2", "Framework: SCQA", "",
            "## SLIDE 1: Cover", "Message: cover", "Emphasis: the title", "",
            "## SLIDE 2: Toolsets", "Message: automation end to end",
            "Emphasis: the efficiency gain for assessment — up to 75%", "",
            "## SLIDE 3: Flow", "Message: extraction to results", "Emphasis: the structured results box", ""]))
        originals = {f: open(os.path.join(deck, f), "rb").read() for f in files}
        base = {}
        if not no_browser:
            q0 = run([os.path.join(HERE, "qa.py"), "--deck-dir", deck, "--json", "--no-cache"])
            try:
                base = {f: (json.loads(q0.stdout).get("render_checks") or {}).get(f, {}).get("failures", 0) for f in files}
            except ValueError:
                base = {}

        p = run([os.path.join(HERE, "choreograph.py"), "--deck-dir", deck, "--stats"])
        check("choreograph: exits 0 and injects into every slide",
              p.returncode == 0 and p.stdout.count("inserted") == 3 and "browser_launches=1" in p.stderr,
              p.stdout[-600:] + p.stderr[-300:])
        check("choreograph: writes motion/motion.json and copies motion.js",
              os.path.isfile(os.path.join(deck, "motion", "motion.json")) and os.path.isfile(os.path.join(deck, "motion", "motion.js")))
        manifest = json.load(open(os.path.join(deck, "motion", "motion.json")))
        by_file = {s_["file"]: s_ for s_ in manifest["slides"]}
        s2 = by_file.get(files[1]) or {}
        check("choreograph: slide 2 (product cards) → cards stagger + count-ups, emphasis matched from the brief",
              any(b["role"] == "card" and b.get("n", 1) >= 3 for b in s2.get("beats", []))
              and any(b["effect"] == "count-up" for b in s2.get("beats", []))
              and (s2.get("emphasis") or {}).get("from") == "brief",
              json.dumps({"emphasis": s2.get("emphasis"), "roles": [b["role"] for b in s2.get("beats", [])]}))
        mo = ds.motion()
        cover_budget = int(2200 * (float(mo.get("cinematicBudgetFactor", 1.4)) if mo.get("level") == "cinematic" else 1))
        check("choreograph: every slide within its entrance budget, cover uses its template override",
              all(s_["total_ms"] <= s_["budget_ms"] for s_ in manifest["slides"])
              and (by_file.get(files[0]) or {}).get("budget_ms") == cover_budget and by_file[files[0]].get("transition_in") == "none",
              json.dumps([(s_["file"], s_["total_ms"], s_["budget_ms"]) for s_ in manifest["slides"]]))
        for f in files:
            html = open(os.path.join(deck, f), encoding="utf-8").read()
            spec_len = len(html.split('id="imprimatur-motion-spec"', 1)[1].split("</script>", 1)[0].encode())
            inline = html.split('id="imprimatur-motion-spec"')[1].split("</script>")[0]
            check(f"choreograph: {f} inline spec ≤ 4 KB, compact child-index paths, no class/hex/text payload",
                  spec_len <= 4096 and '"sel":[' in inline and '"text":' not in inline and not any(
                      c in inline for c in (".text-", "#epam", "class=", "#slide >")),
                  f"{spec_len} B")
            v = run([os.path.join(HERE, "validate.py"), os.path.join(deck, f)])
            check(f"validate.py: {f} still passes with the injected block", v.returncode == 0, (v.stdout + v.stderr)[-500:])
        p = run([os.path.join(HERE, "choreograph.py"), "--deck-dir", deck, "--summary"])
        check("choreograph: --summary prints the language line + one line per slide, ≤ 3 KB",
              p.returncode == 0 and p.stdout.startswith("language:") and p.stdout.count("\n") == 4 and len(p.stdout) <= 3072, p.stdout[:300])

        # QA: static == end state, pixel for pixel; nothing else regresses
        if not no_browser:
            q = run([os.path.join(HERE, "qa.py"), "--deck-dir", deck, "--json", "--no-cache"])
            try:
                qd = json.loads(q.stdout)
            except ValueError:
                qd = {}
                check("qa.py --json parses", False, (q.stdout + q.stderr)[-600:])
            rc = (qd.get("render_checks") or {})
            maes = {f: (rc.get(f) or {}).get("motion", {}) or {} for f in files}
            check("qa.py: motion check ran on every slide with MAE 0 (end state == static)",
                  all((maes[f].get("mae") == 0.0) for f in files) and all(not (rc.get(f) or {}).get("motion_fails") for f in files),
                  json.dumps({f: {"mae": maes[f].get("mae"), "fails": (rc.get(f) or {}).get("motion_fails")} for f in files}))
            after = {f: (rc.get(f) or {}).get("failures", 0) for f in files}
            check("qa.py: no regression from the block (failures per slide == pre-choreography baseline)",
                  bool(base) and all(after[f] == base.get(f, 0) for f in files),
                  json.dumps({"baseline": base, "after": after, "validate": {k: v["fails"] for k, v in (qd.get("validate") or {}).items() if v.get("fails")}})[:700])
            # the static predicate itself: under Playwright the runtime touches nothing
            from playwright.sync_api import sync_playwright
            with sync_playwright() as pw:
                browser = pw.chromium.launch()
                page = browser.new_page(viewport={"width": 1920, "height": 1080})
                page.goto("file://" + os.path.join(deck, files[1]), wait_until="networkidle")
                page.wait_for_timeout(300)
                st = page.evaluate("() => ({static: window.__imprimaturMotion && window.__imprimaturMotion.static, built: window.__imprimaturMotion && window.__imprimaturMotion.built, veil: !!document.getElementById('imprimatur-motion-veil'), gsap: !!window.gsap})")
                check("runtime: under Playwright (webdriver) it is static, unbuilt, no veil, GSAP never fetched",
                      st.get("static") is True and st.get("built") is False and st.get("veil") is False and st.get("gsap") is False, json.dumps(st))
                static_html = page.evaluate("document.getElementById('slide').outerHTML")
                browser.close()
                # the live path: a browser that does not announce automation
                browser = pw.chromium.launch(args=["--disable-blink-features=AutomationControlled"])
                for fi, f in enumerate(files):
                    page = browser.new_page(viewport={"width": 1920, "height": 1080})
                    page.goto("file://" + os.path.join(deck, f) + "?static=1", wait_until="networkidle")
                    page.wait_for_timeout(300)
                    static_f = page.evaluate("document.getElementById('slide').outerHTML")
                    page.goto("file://" + os.path.join(deck, f), wait_until="networkidle")
                    try:
                        page.wait_for_function("window.__imprimaturMotion && window.__imprimaturMotion.info", timeout=15000)
                        info = page.evaluate("window.__imprimaturMotion.info")
                    except Exception as e:
                        info = {"error": f"timeout: {e}"}
                    if info.get("error") and "gsap" in str(info["error"]).lower():
                        print(f"(live-path check skipped: {info['error']} — offline?)"); page.close(); break
                    live = page.evaluate("() => ({static: window.__imprimaturMotion.static, built: window.__imprimaturMotion.built, tl: !!(window.__timelines && Object.keys(window.__timelines).length), veil: !!document.getElementById('imprimatur-motion-veil'), dur: window.__imprimaturMotion.tl ? window.__imprimaturMotion.tl.duration() : 0})")
                    check(f"runtime: live path on {f} builds a paused timeline, lifts the veil, autoplays standalone",
                          live.get("static") is False and live.get("built") is True and live.get("tl") and live.get("veil") is False and live.get("dur", 0) > 0.3,
                          json.dumps({"info": info, "live": live}))
                    page.wait_for_timeout(int(info.get("total_ms", 1600)) + 700)
                    page.evaluate("window.__imprimaturMotion.toEnd()")   # leave the slide: idle camera/drift stop and restore
                    after = page.evaluate("document.getElementById('slide').outerHTML")
                    first = next((i for i in range(min(len(static_f), len(after))) if static_f[i] != after[i]), min(len(static_f), len(after)))
                    check(f"runtime: after the entrance {f} is byte-identical to the static slide (attributes, word splits, count-up text restored)",
                          after == static_f, f"len static={len(static_f)} after={len(after)}; first diff @{first}: "
                          f"static={static_f[max(0, first - 40):first + 80]!r} after={after[max(0, first - 40):first + 80]!r}")
                    page.close()
                browser.close()

        # ── director scene: a travelling token on the process-flow slide; the resting slide must still be static ──
        import choreograph as _ch
        flow = files[2]
        scene = {"v": 1, "slides": {flow: {"name": "test-journey", "keep": ["eyebrow", "title"], "beats": [
            {"id": "boxes", "effect": "spring", "sel": "#slide svg rect[rx]", "at": 0.0, "dur": 0.4, "stagger": 0.05},
            {"id": "journey", "effect": "travel", "sel": "#slide svg rect[rx]:nth-of-type(1)", "r": 10, "leg": 0.3, "dwell": 0.1, "trail": True,
             "waypoints": ["#slide svg rect[rx]:nth-of-type(2)", "#slide svg rect[rx]:nth-of-type(3)", "#slide svg rect[rx]:nth-of-type(4)"], "at": 0.5}],
            "emphasis": {"sel": "#slide h1", "effect": "focus-pull", "dur": 0.6}}}}
        os.makedirs(os.path.join(deck, "motion"), exist_ok=True)
        json.dump(scene, open(os.path.join(deck, "motion", "director.json"), "w"))
        p = run([os.path.join(HERE, "choreograph.py"), "--deck-dir", deck, "--files", os.path.join(deck, flow)])
        man = json.load(open(os.path.join(deck, "motion", "motion.json")))
        sflow = next(s_ for s_ in man["slides"] if s_["file"] == flow)
        check("director: scene merged — travel beat with resolved waypoints, kept opening beats, scene clock",
              p.returncode == 0 and sflow.get("scene") == "test-journey" and any(b["effect"] == "travel" and len(b.get("waypoints", [])) == 3 for b in sflow["beats"])
              and "resolve to nothing" not in p.stdout and any(b["role"] == "title" for b in sflow["beats"]), p.stdout[-400:])
        if not no_browser:
            q = run([os.path.join(HERE, "qa.py"), "--deck-dir", deck, "--files", os.path.join(deck, flow), "--json", "--no-cache"])
            try:
                e = json.loads(q.stdout)["render_checks"][flow]
            except Exception:
                e = {"motion": {}, "motion_fails": ["qa output unreadable"]}
            check("director: QA — resting slide identical (MAE 0), tokens and traces removed, no motion fails",
                  (e.get("motion") or {}).get("mae") == 0.0 and not e.get("motion_fails"), json.dumps({"mae": (e.get("motion") or {}).get("mae"), "fails": e.get("motion_fails")}))
            with sync_playwright() as pw:
                browser = pw.chromium.launch(args=["--disable-blink-features=AutomationControlled"])
                page = browser.new_page(viewport={"width": 1920, "height": 1080})
                page.goto("file://" + os.path.join(deck, flow) + "?static=1", wait_until="networkidle"); page.wait_for_timeout(300)
                static_f = page.evaluate("document.getElementById('slide').outerHTML")
                page.goto("file://" + os.path.join(deck, flow), wait_until="networkidle")
                try:
                    page.wait_for_function("window.__imprimaturMotion && window.__imprimaturMotion.info", timeout=15000)
                    info = page.evaluate("window.__imprimaturMotion.info")
                except Exception as ex:
                    info = {"error": str(ex)}
                if not (info.get("error") and "gsap" in str(info["error"]).lower()):
                    page.wait_for_timeout(900)
                    mid = page.evaluate("() => ({tokens: document.querySelectorAll('[data-motion-token]').length, path: !!window.MotionPathPlugin, progress: window.__imprimaturMotion.tl.progress()})")
                    check("director: live path — the token exists mid-scene and the MotionPath plugin loaded", mid.get("tokens", 0) >= 1 and mid.get("path") is True, json.dumps(mid))
                    page.wait_for_timeout(int(info.get("total_ms", 3000)) + 800)
                    page.evaluate("window.__imprimaturMotion.toEnd()")
                    after = page.evaluate("document.getElementById('slide').outerHTML")
                    left = page.evaluate("document.querySelectorAll('[data-motion-token]').length")
                    check("director: after the scene the DOM is byte-identical (tokens/traces gone, SVG transforms restored)", after == static_f,
                          f"tokens left: {left}; len static={len(static_f)} after={len(after)}")
                browser.close()
            s_p = run([os.path.join(HERE, "motion_strip.py"), os.path.join(deck, flow), "--out", os.path.join(tmp, "strip.png"), "--frames", "4"])
            check("motion_strip: writes a filmstrip PNG", s_p.returncode == 0 and os.path.isfile(os.path.join(tmp, "strip.png")), s_p.stdout + s_p.stderr)
            g_p = run([os.path.join(HERE, "scene_graph.py"), os.path.join(deck, flow), "--deck-dir", deck, "--json"])
            try:
                g = json.loads(g_p.stdout)
            except ValueError:
                g = {}
            dg = (g.get("diagrams") or [{}])[0]
            check("scene_graph: the process-flow slide yields a diagram with labelled nodes and arrowed edges + the brief's Emphasis",
                  len(dg.get("nodes") or []) >= 3 and any(e.get("arrow") for e in dg.get("edges") or []) and any(n.get("label") for n in dg.get("nodes") or [])
                  and (g.get("brief") or {}).get("Emphasis"), (g_p.stdout + g_p.stderr)[-500:])
        os.remove(os.path.join(deck, "motion", "director.json"))
        run([os.path.join(HERE, "choreograph.py"), "--deck-dir", deck, "--files", os.path.join(deck, flow)])

        # --check / edit / re-run / --strip
        p = run([os.path.join(HERE, "choreograph.py"), "--deck-dir", deck, "--check"])
        check("choreograph --check: fresh specs are current", p.returncode == 0, p.stdout)
        target = os.path.join(deck, files[2])
        html = open(target, encoding="utf-8").read()
        open(target, "w", encoding="utf-8").write(html.replace("</body>", "<!-- body edit -->\n</body>", 1))
        p = run([os.path.join(HERE, "choreograph.py"), "--deck-dir", deck, "--check"])
        check("choreograph --check: a body edit makes that slide's spec STALE (exit 1, names the file)",
              p.returncode == 1 and files[2] in p.stdout and files[1] not in p.stdout.split("re-run")[0].split("STALE")[-1], p.stdout)
        p = run([os.path.join(HERE, "choreograph.py"), "--deck-dir", deck, "--files", target])
        p2 = run([os.path.join(HERE, "choreograph.py"), "--deck-dir", deck, "--check"])
        manifest2 = json.load(open(os.path.join(deck, "motion", "motion.json")))
        check("choreograph --files: re-choreographs only the touched slide, manifest keeps the others, --check clean again",
              p.returncode == 0 and "replaced" in p.stdout and p2.returncode == 0 and len(manifest2["slides"]) == 3, p.stdout + p2.stdout)
        p = run([os.path.join(HERE, "choreograph.py"), "--deck-dir", deck, "--strip"])
        restored = {f: open(os.path.join(deck, f), "rb").read() for f in files}
        check("choreograph --strip: untouched slides return byte-identical to their pre-choreography bytes",
              p.returncode == 0 and all(restored[f] == originals[f] for f in files[:2])
              and restored[files[2]] == originals[files[2]].replace(b"</body>", b"<!-- body edit -->\n</body>", 1)
              and not os.path.isfile(os.path.join(deck, "motion", "motion.json")), p.stdout)
        # disabled deck: choreograph is a no-op without a browser
        state["motion"] = {"enabled": False}
        json.dump(state, open(os.path.join(deck, "deck-state.json"), "w"), indent=2)
        p = run([os.path.join(HERE, "choreograph.py"), "--deck-dir", deck, "--stats"])
        check("choreograph: disabled deck → exit 0, 'disabled', no browser launch, no bytes written",
              p.returncode == 0 and "disabled" in p.stdout and "browser_launches" not in p.stderr
              and all(open(os.path.join(deck, f), "rb").read() == restored[f] for f in files), p.stdout + p.stderr)

    # ══ M3 · 1.6.0: one motion language, the reading beat, Link cuts, counters in sequence, ?t= ══
    with tempfile.TemporaryDirectory() as tmp:
        deck = os.path.join(tmp, "deck")
        os.makedirs(deck)
        plan = [(1, "01-cover", "cover"), (2, "08-product-cards", "cards"), (3, "26-key-differentiators-grid", "grid")]
        files = []
        for n, tpl, slug in plan:
            p = run([os.path.join(HERE, "new_slide.py"), "--deck-dir", deck, "--template", tpl, "--n", str(n), "--slug", slug])
            if p.returncode != 0:
                check(f"M3 new_slide {tpl}", False, p.stderr[-300:])
            files.append(f"{n:02d}-{slug}.html")
        state = {"deck": "Motion M3", "design_system": ds.root, "motion": {"enabled": True, "transition": "crossfade"},
                 "slides": [{"n": n, "file": f, "title": f, "status": "written", "template": tpl, "visual": "none"}
                            for (n, tpl, _), f in zip(plan, files)]}
        json.dump(state, open(os.path.join(deck, "deck-state.json"), "w"), indent=2)
        open(os.path.join(deck, "narrative-outline.md"), "w", encoding="utf-8").write("\n".join([
            "# Narrative Outline — Motion M3", "Framework: SCQA", "",
            "## SLIDE 1: Cover", "Message: cover", "Emphasis: the title", "Link: therefore", "",
            "## SLIDE 2: Toolsets", "Message: automation end to end", "Emphasis: the efficiency gain for assessment — up to 75%", "Link: therefore", "",
            "## SLIDE 3: Grid", "Message: six principles", "Emphasis: the first principle", "Link: but — the other side", ""]))
        p = run([os.path.join(HERE, "choreograph.py"), "--deck-dir", deck])
        man = json.load(open(os.path.join(deck, "motion", "motion.json"))) if p.returncode == 0 else {"slides": []}
        by = {s_["file"]: s_ for s_ in man["slides"]}
        lang = man.get("language") or {}
        eases = {b.get("ease") for s_ in man["slides"] for b in s_["beats"] if b.get("ease")}
        check("1.6.0 language: the manifest names the personality and every beat ease is the deck's arrival or hero ease",
              bool(lang.get("name")) and eases <= {lang.get("ease"), lang.get("hero")} and all(s_.get("easing", {}).get("hero") for s_ in man["slides"]),
              json.dumps({"lang": lang, "eases": sorted(e for e in eases if e)}))
        check("1.6.0 link: the brief's Link picks the cut (therefore → push, but → whip-pan); slide 1 ignores it and keeps none",
              len(by) == 3 and by[files[1]].get("transition_in") == "push" and by[files[1]].get("link") == "therefore"
              and by[files[2]].get("transition_in") == "whip-pan" and by[files[0]].get("transition_in") == "none" and not by[files[0]].get("link"),
              json.dumps({f: (s_.get("transition_in"), s_.get("link")) for f, s_ in by.items()}))
        held = []
        for f, s_ in by.items():
            em = [b for b in s_["beats"] if b["role"] == "emphasis"]
            rest = [b for b in s_["beats"] if b["role"] != "emphasis"]
            if em and rest:
                held.append((f, em[0]["at"] >= max(b["at"] + choreograph._span(b) for b in rest) - 0.001))
            elif (s_.get("effects") or {}).get("emphasis") == "last" and len(s_["beats"]) > 1:
                # no gesture: the focal element's own arrival is last, after a hold
                last, others = s_["beats"][-1], s_["beats"][:-1]
                held.append((f, last["sel"] == (s_.get("emphasis") or {}).get("sel") and last["at"] >= max(b["at"] + choreograph._span(b) for b in others) - 0.001))
            elif (s_.get("effects") or {}).get("emphasis") == "hold":
                held.append((f, True))
        check("1.6.0 hold: the point comes after the last landing — an emphasis beat after a hold, or (no gesture) the focal element arriving last",
              held and all(ok for _, ok in held), json.dumps(held))
        kp = [b for b in by.get(files[1], {}).get("beats", []) if b["effect"] == "count-up"]
        check("1.6.0 counters: consecutive count-ups start ≥ 0.5 × duration apart (one moving number at a time)",
              len(kp) >= 2 and all(kp[i + 1]["at"] - kp[i]["at"] >= 0.5 * kp[i]["dur"] - 0.01 for i in range(len(kp) - 1)),
              json.dumps([(b["at"], b["dur"]) for b in kp]))
        auto = [s_ for s_ in man["slides"] if not s_.get("scene")]
        check("1.6.0 1/3 rule: peak moving ≤ max(4, ⌈total/3⌉) on every auto slide (reported as moving=peak/total)",
              auto and all(s_.get("peak_moving", 99) <= max(4, -(-s_.get("moving", 0) // 3)) for s_ in auto),
              json.dumps([(s_["file"], s_.get("peak_moving"), s_.get("moving")) for s_ in man["slides"]]))
        if ds.motion().get("level") == "cinematic":
            cards = [b for s_ in man["slides"] for b in s_["beats"] if b["role"] == "card"]
            check("1.6.0 cinematic: card beats carry followThrough (content settles after its container)",
                  cards and all(b.get("followThrough") for b in cards), json.dumps([(b.get("n"), b.get("followThrough")) for b in cards]))
        # grid / distance cascade (pure Python: a 2×3 grid of boxes, then nine boxes by distance)
        grid = {"sel": [f"s{i}" for i in range(6)], "boxes": [{"x": 100 + (i % 3) * 300, "y": 200 + (i // 3) * 250, "w": 260, "h": 200} for i in range(6)]}
        order = choreograph.member_order(grid)
        nine = {"sel": [f"s{i}" for i in range(9)], "boxes": [{"x": 100 + (i % 3) * 300, "y": 200 + (i // 3) * 250, "w": 260, "h": 200} for i in range(9)]}
        far = choreograph.member_order(nine)
        check("1.6.0 cascade: a 2×3 grid staggers in reading order with a third of a step added per row; nine boxes stagger by distance from the origin",
              order == [0.0, 1.0, 2.0, 3.33, 4.33, 5.33] and far and far[0] == 0.0 and far[8] == 8.0 and far[3] < far[1] < far[4],
              json.dumps({"grid": order, "nine": far}))
        if not no_browser:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as pw:
                browser = pw.chromium.launch(args=["--disable-blink-features=AutomationControlled"])
                page = browser.new_page(viewport={"width": 1920, "height": 1080})
                page.goto("file://" + os.path.join(deck, files[1]) + "?t=0.5", wait_until="networkidle")
                try:
                    page.wait_for_function("window.__imprimaturMotion && window.__imprimaturMotion.info", timeout=15000)
                    page.wait_for_timeout(400)
                    st = page.evaluate("() => { const m = window.__imprimaturMotion; return {err: m.info && m.info.error, paused: m.tl && m.tl.paused(), t: m.tl && m.tl.time(), veil: !!document.getElementById('imprimatur-motion-veil'), seekT: m.seekT, aria: document.querySelectorAll('#slide [aria-hidden=\"true\"]').length, label: !!document.querySelector('#slide [aria-label]')}; }")
                except Exception as ex:
                    st = {"err": str(ex)}
                if st.get("err") and "gsap" in str(st["err"]).lower():
                    print(f"(?t= check skipped: {st['err']} — offline?)")
                else:
                    check("1.6.0 ?t= harness: the slide builds, holds at 0.5 s, does not autoplay, no veil",
                          st.get("paused") is True and abs((st.get("t") or 0) - 0.5) < 0.03 and st.get("veil") is False and st.get("seekT") == 0.5, json.dumps(st))
                browser.close()
            q = run([os.path.join(HERE, "qa.py"), "--deck-dir", deck, "--json", "--no-cache"])
            try:
                rc = json.loads(q.stdout).get("render_checks") or {}
            except ValueError:
                rc = {}
            mo_ = {f: (rc.get(f) or {}).get("motion") or {} for f in files}
            check("1.6.0 QA: MAE 0 on every slide with follow-through / lines-mask / aria in play, and the cost row is reported",
                  all(mo_[f].get("mae") == 0.0 for f in files) and all(isinstance(mo_[f].get("cost"), dict) for f in files)
                  and all(not (rc.get(f) or {}).get("motion_fails") for f in files),
                  json.dumps({f: {"mae": mo_[f].get("mae"), "cost": mo_[f].get("cost"), "fails": (rc.get(f) or {}).get("motion_fails")} for f in files})[:900])

    # ══ M2 · every template gets a sane plan (dry run, one browser) ════════════
    if not no_browser:
        tpls = sorted(glob.glob(os.path.join(ds.templates_dir, "*.html")))
        p = run([os.path.join(HERE, "choreograph.py"), "--dry-run", "--json", "--stats", "--files"] + tpls,
                env={**os.environ, "DECK_DESIGN_SYSTEM": ds.root})
        try:
            raw = p.stdout
            plans = json.loads(raw[raw.index("{"):raw.rindex("}") + 1])["slides"]
        except Exception as e:
            plans = []
            check("templates sweep: JSON parses", False, f"{e}: {(p.stdout + p.stderr)[-500:]}")
        empty = [s_["file"] for s_ in plans if not s_["beats"]]
        over = [(s_["file"], s_["total_ms"], s_["budget_ms"]) for s_ in plans if s_["total_ms"] > s_["budget_ms"]]
        inline_len = lambda s_: len(json.dumps(choreograph.compact_spec(s_), separators=(",", ":")))
        big = [(s_["file"], inline_len(s_)) for s_ in plans if inline_len(s_) > 4096]
        many = [(s_["file"], len(s_["beats"])) for s_ in plans if len(s_["beats"]) > 14]
        check(f"templates sweep: {len(plans)}/{len(tpls)} templates planned in one browser launch",
              len(plans) == len(tpls) and "browser_launches=1" in p.stderr, p.stderr[-200:])
        check("templates sweep: every template gets ≥ 1 beat", not empty, ", ".join(empty))
        check("templates sweep: every plan within its budget", not over, str(over))
        check("templates sweep: every inline spec ≤ 4 KB and ≤ 14 beats", not big and not many, str(big + many))
        byfile = {s_["file"]: s_ for s_ in plans}
        pipe = byfile.get("41-pipeline-cards.html", {}); tbl = byfile.get("38-table.html", {})
        check("templates sweep: bespoke SVG diagram → svg-card groups + connectors (41-pipeline-cards)",
              any(b["role"] == "svg-card" and b.get("n", 1) >= 2 for b in pipe.get("beats", []))
              and any(b["role"] == "connector" for b in pipe.get("beats", [])),
              str([(b["role"], b.get("n", 1)) for b in pipe.get("beats", [])]))
        check("templates sweep: table → header beat + staggered row group (38-table)",
              any(b["role"] == "row" and b.get("n", 1) >= 2 for b in tbl.get("beats", [])),
              str([(b["role"], b.get("n", 1)) for b in tbl.get("beats", [])]))
        title_fx = {b["effect"] for s_ in plans for b in s_["beats"] if b["role"] == "title"}
        emph_fx = {b["effect"] for s_ in plans for b in s_["beats"] if b["role"] == "emphasis"}
        # a personality that never scales text makes its point by order ("last") or stillness ("hold") — no gesture to vary
        emph_fx |= {v for s_ in plans for k, v in (s_.get("effects") or {}).items() if k == "emphasis" and v in ("last", "hold")}
        check("templates sweep: effect rotation gives variety (≥ 3 title effects, ≥ 2 emphasis effects across the pack)",
              len(title_fx) >= 3 and len(emph_fx) >= 2, f"title={sorted(title_fx)} emphasis={sorted(emph_fx)}")

    failed = results.count(False)
    print(f"\n{results.count(True)}/{len(results)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
