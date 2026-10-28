#!/usr/bin/env python3
"""Smoke tests for the 1.3.0 engine helpers — run from validate_all.sh.

  new_slide.py     prints the slot list + body range (not the body), injects
                   deck-overrides.html into <head>, and the result still passes
                   validate.py's head-identity check.
  narrative_brief  returns only the requested SLIDE BRIEFs; exit 2 on a missing one.
  recipe_brief     prints a recipe's doc, example config and build command; --list works.
  render_checks    second run on an unchanged file comes from the cache (no browser).
  pack_brief       --no-templates drops the template index and stays ≤ 3.5 KB (designer boot).
  log_slide        --summary --slides A-B returns only that chunk's rows + deviations;
                   --deviation replaces the slide's latest line (2026-10-06), --append folds
                   into it — never a second line (1.6.5).
  new_slide        sets the footer page number on EVERY pack template that carries a slot
                   (`id="page-number"` hook or footer-adjacent bold span, `N` placeholder) —
                   2026-10-06: 9 templates shipped with a literal N.
  validate         the prose font floor applies to SVG text as written — font-size="…"
                   attributes and inline font-size: styles (2026-10-06: 16px SVG labels
                   passed under the pack's old svg.minCaptionPx exemption).
  qa               sampled gradient-contrast FAILs count into the slide verdict and
                   total_failures on a whole-deck run, report-only in a --files chunk run
                   (2026-10-06: a slide carried fail:true rows and still reported pass:true).

Usage:  python3 scripts/test_helpers.py
"""
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from ds_config import load  # noqa: E402


def run(args, **kw):
    return subprocess.run([sys.executable] + args, capture_output=True, text=True, timeout=300, **kw)


def main():
    results = []

    def check(name, ok, detail=""):
        results.append(ok)
        print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  {detail[:300]}" if detail and not ok else ""))

    ds = load()
    with tempfile.TemporaryDirectory() as tmp:
        deck = os.path.join(tmp, "deck")
        os.makedirs(deck)
        open(os.path.join(deck, "deck-overrides.html"), "w").write(
            "<style>/* deck override */ .deck-test-marker{color:inherit}</style>")

        # ── new_slide.py ──
        p = run([os.path.join(HERE, "new_slide.py"), "--deck-dir", deck, "--template", "01-cover",
                 "--n", "1", "--slug", "cover"])
        out = p.stdout
        check("new_slide: exits 0", p.returncode == 0, p.stderr)
        check("new_slide: prints slot list and body range, not the body",
              "text slots" in out and "body is lines" in out and "<body" not in out)
        slide = os.path.join(deck, "01-cover.html")
        html = open(slide, encoding="utf-8").read()
        check("new_slide: injected deck-overrides.html into <head>",
              "deck-test-marker" in html and html.index("deck-test-marker") < html.index("<body"))
        v = run([os.path.join(HERE, "validate.py"), slide])
        check("new_slide: overridden slide still passes validate.py (head additions tolerated)",
              v.returncode == 0, v.stdout + v.stderr)
        p2 = run([os.path.join(HERE, "new_slide.py"), "--deck-dir", deck, "--template", "01-cover",
                  "--n", "1", "--slug", "cover", "--force", "--body"])
        check("new_slide: --body prints the body region", "<body" in p2.stdout)

        # ── new_slide.py: footer page number on every template that carries a slot ──
        # Exercised through the module (one new_slide.py invocation per turn is the hook's
        # rule for Bash loops; a test calling set_page_number on copies is not slide authoring).
        import new_slide  # noqa: E402
        footer = ds.get("footer.requiredText")
        with_slot, bad = [], []
        for tp in sorted(glob.glob(os.path.join(ds.templates_dir, "*.html"))):
            html = open(tp, encoding="utf-8").read()
            if new_slide.find_page_number_pattern(html, footer) is None:
                continue
            with_slot.append(os.path.basename(tp))
            dst = os.path.join(deck, "pn-" + os.path.basename(tp))
            shutil.copyfile(tp, dst)
            ok = new_slide.set_page_number(dst, ds, "7")
            out = open(dst, encoding="utf-8").read()
            m = new_slide.find_page_number_pattern(out, footer)
            m = m.search(out) if m else None
            if not ok or m is None or not re.sub(r"\s+", "", m.group(0)).endswith(">7</span>") \
                    or re.search(r'id="page-number"[^>]*>\s*N\s*<', out):
                bad.append(os.path.basename(tp))
            os.remove(dst)
        named = [n for n in with_slot if n.split("-")[0] in
                 {"03", "06", "07", "08", "09", "12", "28", "34", "49"}]
        check("new_slide: every template with a page-number slot gets it set (id hook or N placeholder)",
              len(with_slot) >= 40 and not bad and len(named) >= 9,
              f"with_slot={len(with_slot)} named={len(named)} bad={bad[:8]}")
        probe = "<div><span>" + (footer or "Confidential") + " &amp; Confidential.</span>" \
                "<span class=\"font-bold\" id=\"page-number\">N</span></div>"
        check("new_slide: the id hook with the literal N placeholder is detected",
              new_slide.find_page_number_pattern(probe, footer) is not None)
        probe2 = "<div><span>" + (footer or "Confidential") + " &amp; Confidential.</span>" \
                 "<span class=\"font-bold\">N</span></div>"
        check("new_slide: the footer-adjacent bold span with N (no id) is detected",
              not footer or new_slide.find_page_number_pattern(probe2, footer) is not None)

        # ── validate.py: the prose floor applies to SVG text as written ──
        floor = float(ds.get("typography.minFontSizePx", 14))
        probe = os.path.join(deck, "svg-floor-probe.html")
        svg = (f'<svg viewBox="0 0 400 100"><text x="1" y="20" font-size="{floor - 2:g}">a</text>'
               f'<text x="1" y="40" style="font-size:{floor - 2:g}px">b</text>'
               f'<text x="1" y="60" font-size="{floor - 0.5:g}px">c</text>'
               f'<text x="1" y="80" font-size="{floor:g}">ok</text></svg>')
        html = open(slide, encoding="utf-8").read()
        open(probe, "w", encoding="utf-8").write(
            re.sub(r'(<div\b[^>]*id="slide"[^>]*>)', lambda m: m.group(1) + svg, html, count=1))
        v = run([os.path.join(HERE, "validate.py"), probe])
        svg_fails = [l for l in v.stdout.splitlines() if "FAIL" in l and "SVG font-size" in l]
        check("validate: SVG font-size attr, inline style and a .5 decimal below the prose floor FAIL; "
              "the floor itself passes",
              v.returncode == 1 and len(svg_fails) == 3
              and all(f"{floor:g}px floor" in l for l in svg_fails)
              and not any(f'font-size="{floor:g}"' in l for l in svg_fails), v.stdout + v.stderr)
        os.remove(probe)

        # ── narrative_brief.py ──
        outline = "\n".join([
            "# Narrative Outline — Test", "Framework: SCQA — because", "Arc: a b c", "",
            "## SLIDE 1: One", "Message: m1", "Visual: none", "",
            "## SLIDE 2: Two", "Message: m2", "Visual: bespoke", "",
            "## SLIDE 3: Three", "Message: m3", "Visual: chart", ""])
        open(os.path.join(deck, "narrative-outline.md"), "w").write(outline)
        p = run([os.path.join(HERE, "narrative_brief.py"), "--deck-dir", deck, "--slides", "2-3"])
        check("narrative_brief: range returns only slides 2-3 plus the arc",
              p.returncode == 0 and "SLIDE 2" in p.stdout and "SLIDE 3" in p.stdout
              and "SLIDE 1" not in p.stdout and "Framework:" in p.stdout, p.stdout)
        p = run([os.path.join(HERE, "narrative_brief.py"), "--deck-dir", deck, "--slides", "9"])
        check("narrative_brief: missing brief exits 2", p.returncode == 2)
        p = run([os.path.join(HERE, "narrative_brief.py"), "--deck-dir", deck, "--list"])
        check("narrative_brief: --list prints numbers + messages", "01  One" in p.stdout)

        # ── pack_brief.py ──
        p = run([os.path.join(HERE, "pack_brief.py"), "--design-system", ds.root, "--no-templates"])
        check("pack_brief: --no-templates omits the template index and stays ≤ 3.5 KB",
              p.returncode == 0 and "## Templates" not in p.stdout and len(p.stdout) <= 3584
              and "## Type scale" in p.stdout, f"{len(p.stdout)} bytes; rc={p.returncode} {p.stderr[-200:]}")
        p_full = run([os.path.join(HERE, "pack_brief.py"), "--design-system", ds.root])
        check("pack_brief: default still prints the template index (planner form)",
              p_full.returncode == 0 and "## Templates" in p_full.stdout)

        # ── log_slide.py --summary --slides ──
        ls = os.path.join(HERE, "log_slide.py")
        for n in (1, 6, 7):
            open(os.path.join(deck, f"{n:02d}-t{n}.html"), "w").write("<html></html>")
            run([ls, "--deck-dir", deck, "--n", str(n), "--template", "01-cover", "--visual", "none",
                 "--focal", f"focal {n}", "--title", "T"])
        run([ls, "--deck-dir", deck, "--n", "6", "--template", "01-cover", "--visual", "none",
             "--focal", "focal 6", "--deviation", "dev six"])
        run([ls, "--deck-dir", deck, "--decision", "accent=primary"])
        p = run([ls, "--deck-dir", deck, "--summary", "--slides", "6-8"])
        check("log_slide: --summary --slides 6-8 keeps Locked + rows 06/07 + its deviation, drops 01",
              p.returncode == 0 and "accent: primary" in p.stdout and "| 06 |" in p.stdout
              and "| 07 |" in p.stdout and "| 01 |" not in p.stdout and "dev six" in p.stdout
              and "not yet logged: 08" in p.stdout, p.stdout + p.stderr)
        p = run([ls, "--deck-dir", deck, "--slides", "6-8"])
        check("log_slide: --slides without --summary is rejected", p.returncode != 0)

        # ── log_slide.py --deviation: replace-latest by default, --append on request ──
        def dev_lines():
            dd = open(os.path.join(deck, "design-decisions.md"), encoding="utf-8").read()
            return [l for l in dd.splitlines() if l.startswith("- 06:")]
        base = [ls, "--deck-dir", deck, "--n", "6", "--template", "01-cover", "--visual", "none",
                "--focal", "focal 6"]
        p = run(base + ["--deviation", "dev six rewritten"])
        check("log_slide: re-logging with --deviation replaces slide 06's latest line (still one line)",
              p.returncode == 0 and "replaced" in p.stdout and dev_lines() == ["- 06: dev six rewritten"],
              p.stdout + p.stderr + str(dev_lines()))
        p = run(base + ["--deviation", "dev six second", "--append"])
        check("log_slide: --deviation --append folds the note into the slide's one line",
              p.returncode == 0 and "merged" in p.stdout
              and dev_lines() == ["- 06: dev six rewritten; dev six second"], str(dev_lines()))
        run(base + ["--deviation", "dev six second", "--append"])
        check("log_slide: re-appending a note the line already carries leaves it alone",
              dev_lines() == ["- 06: dev six rewritten; dev six second"], str(dev_lines()))
        # a pre-2026-10-06 file with two lines for one slide: only the latest is touched
        dd_path = os.path.join(deck, "design-decisions.md")
        dd = open(dd_path, encoding="utf-8").read()
        open(dd_path, "w", encoding="utf-8").write(
            dd.replace("- 06: dev six rewritten; dev six second", "- 06: legacy one\n- 06: legacy two"))
        run(base + ["--deviation", "dev six second, revised"])
        check("log_slide: a further re-log replaces only the latest of two legacy lines",
              dev_lines() == ["- 06: legacy one", "- 06: dev six second, revised"], str(dev_lines()))
        p = run([ls, "--deck-dir", deck, "--append"])
        check("log_slide: --append without --deviation is rejected", p.returncode != 0)
        for n in (1, 6, 7):
            os.remove(os.path.join(deck, f"{n:02d}-t{n}.html"))

        # ── recipe_brief.py ──
        rb = os.path.join(PLUGIN, "skills", "svg-reconstruct", "scripts", "recipe_brief.py")
        p = run([rb, "process"])
        check("recipe_brief: process prints doc, example config and build command",
              p.returncode == 0 and "Config schema" in p.stdout and "example_process.json" in p.stdout
              and "get_builder" in p.stdout and len(p.stdout) < 4000, p.stdout[:200] + p.stderr[:200])
        p = run([rb, "--list"])
        check("recipe_brief: --list shows 20 types", p.returncode == 0 and p.stdout.count("\n") >= 20)

        # ── render_checks cache ──
        if os.path.isdir(ds.fonts_dir):
            shutil.copytree(ds.fonts_dir, os.path.join(deck, "fonts"), dirs_exist_ok=True)
        t0 = time.time()
        p = run([os.path.join(HERE, "render_checks.py"), slide, "--deck-dir", deck, "--json", "--no-cache"])
        cold = time.time() - t0
        ok_cold = p.returncode in (0, 1) and p.stdout.strip().startswith("{")
        check("render_checks: cold run produces JSON", ok_cold, p.stderr[-300:])
        run([os.path.join(HERE, "render_checks.py"), slide, "--deck-dir", deck, "--json"])  # populate
        t0 = time.time()
        p = run([os.path.join(HERE, "render_checks.py"), slide, "--deck-dir", deck, "--json"])
        warm = time.time() - t0
        data = json.loads(p.stdout) if p.stdout.strip().startswith("{") else {}
        entry = (data.get("files") or {}).get("01-cover.html") or {}
        check("render_checks: warm run served from cache", entry.get("cached") is True and warm < cold,
              f"warm={warm:.1f}s cold={cold:.1f}s cached={entry.get('cached')}")
        check("render_checks: JSON carries logo + gradient_contrast fields",
              "logo" in entry and "gradient_contrast" in entry)
        # editing the file invalidates its entry
        with open(slide, "a", encoding="utf-8") as f:
            f.write("\n<!-- touched -->\n")
        p = run([os.path.join(HERE, "render_checks.py"), slide, "--deck-dir", deck, "--json"])
        data = json.loads(p.stdout) if p.stdout.strip().startswith("{") else {}
        entry = (data.get("files") or {}).get("01-cover.html") or {}
        check("render_checks: edited file is re-rendered (cache miss)", entry.get("cached") is False)

        # ── qa.py: sampled gradient-contrast FAILs gate the whole-deck run, not a chunk run ──
        # A mid-grey label over a white→black gradient: worst-case ratio ~3.9:1 on the white
        # end, below 4.5:1, and the two ends differ so the row is NOT the flat-background
        # (uniform) case that already counted before 2026-10-06.
        qa = os.path.join(HERE, "qa.py")
        grad = os.path.join(deck, "02-grad.html")
        svg = ('<svg width="600" height="200" style="position:absolute;left:200px;top:300px">'
               '<defs><linearGradient id="tg" x1="0" x2="1"><stop offset="0" stop-color="#FFFFFF"/>'
               '<stop offset="1" stop-color="#000000"/></linearGradient></defs>'
               '<rect width="600" height="200" fill="url(#tg)"/>'
               '<text x="300" y="110" text-anchor="middle" font-size="20" fill="#808080">'
               'sampled label</text></svg>')
        html = open(slide, encoding="utf-8").read()
        open(grad, "w", encoding="utf-8").write(
            re.sub(r'(<div\b[^>]*id="slide"[^>]*>)', lambda m: m.group(1) + svg, html, count=1))
        # The log_slide tests above left a deck-state.json naming slides that no longer
        # exist on disk; qa.py --deck-dir treats that list as the set of live slides
        # (WP8 orphan filter) and would find nothing to check. Drop it: this deck is
        # whatever is on disk.
        state = os.path.join(deck, "deck-state.json")
        if os.path.isfile(state):
            os.remove(state)
        p = run([qa, "--deck-dir", deck, "--json", "--no-cache"])
        data = json.loads(p.stdout) if p.stdout.strip().startswith("{") else {}
        e = (data.get("render_checks") or {}).get("02-grad.html") or {}
        gc = int(e.get("gradient_contrast_fails") or 0)
        check("qa: whole-deck run counts gradient_contrast fails into the slide verdict and total_failures",
              gc >= 1 and e.get("contrast_counted") is True and e.get("failures", 0) >= gc
              and e.get("pass") is False and data.get("total_failures", 0) >= gc
              and data.get("pass") is False and data.get("gradient_contrast_fails", 0) >= gc,
              f"gc={gc} entry_failures={e.get('failures')} pass={e.get('pass')} "
              f"total={data.get('total_failures')} rc={p.returncode} {p.stderr[-200:]}")
        p2 = run([qa, "--deck-dir", deck, "--files", "02-grad.html", "--json", "--no-cache"])
        data2 = json.loads(p2.stdout) if p2.stdout.strip().startswith("{") else {}
        e2 = (data2.get("render_checks") or {}).get("02-grad.html") or {}
        check("qa: --files chunk run reports the same gradient fails but does not gate on them",
              int(e2.get("gradient_contrast_fails") or 0) >= 1 and e2.get("contrast_counted") is False
              and e2.get("failures", 0) < e.get("failures", 0),
              f"chunk gc={e2.get('gradient_contrast_fails')} failures={e2.get('failures')} "
              f"vs whole-deck failures={e.get('failures')}")
        os.remove(grad)

    # ── new_slide.py + cobrand: a bad declaration stops BEFORE the copy (no browser) ──
    # The applied-and-measured half is run_evals.py cobrand (validate_all.sh, browser stage).
    with tempfile.TemporaryDirectory() as tmp:
        cdeck = os.path.join(tmp, "cdeck")
        os.makedirs(os.path.join(cdeck, "assets"))
        state = os.path.join(cdeck, "deck-state.json")
        json.dump({"cobrand": {"logo": "assets/client.png", "position": "left"}, "slides": []},
                  open(state, "w"))
        p = run([os.path.join(HERE, "new_slide.py"), "--deck-dir", cdeck, "--template", "02-content-bullets",
                 "--n", "2", "--slug", "x"])
        check("cobrand: new_slide.py refuses a declared logo that is not on disk, and copies nothing",
              p.returncode != 0 and "cobrand.logo" in p.stderr and not glob.glob(os.path.join(cdeck, "02-*.html")),
              p.stdout + p.stderr)
        json.dump({"cobrand": {"logo": "assets/client.png", "position": "right"}, "slides": []},
                  open(state, "w"))
        p = run([os.path.join(HERE, "new_slide.py"), "--deck-dir", cdeck, "--template", "02-content-bullets",
                 "--n", "2", "--slug", "x"])
        check("cobrand: an unsupported position is rejected with a message", p.returncode != 0
              and "position" in p.stderr, p.stdout + p.stderr)

    failed = results.count(False)
    print(f"\n{results.count(True)}/{len(results)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
