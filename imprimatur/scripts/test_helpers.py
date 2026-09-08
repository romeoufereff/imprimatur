#!/usr/bin/env python3
"""Smoke tests for the 1.3.0 engine helpers — run from validate_all.sh.

  new_slide.py     prints the slot list + body range (not the body), injects
                   deck-overrides.html into <head>, and the result still passes
                   validate.py's head-identity check.
  narrative_brief  returns only the requested SLIDE BRIEFs; exit 2 on a missing one.
  recipe_brief     prints a recipe's doc, example config and build command; --list works.
  render_checks    second run on an unchanged file comes from the cache (no browser).

Usage:  python3 scripts/test_helpers.py
"""
import json
import os
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

    failed = results.count(False)
    print(f"\n{results.count(True)}/{len(results)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
