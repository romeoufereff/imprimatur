#!/usr/bin/env python3
"""
Batch render-level QA — one Chromium launch for N files (WP1).

Before this script, `qa.py` ran check_contrast.py, check_overflow.py and
check_paint.py as three separate subprocesses, each opening its OWN headless
Chromium instance and reloading every file again — 3 browser launches x N page
loads per invocation, run on every single Write/Edit via the PostToolUse hook.
That is the "7 s of Playwright nobody reads" the optimization plan measured on
every slide.

This script loads each file ONCE in a single shared browser/page and runs
whichever checks apply to that file, using the `analyze_*`/`evaluate_*`
functions the three check_*.py modules now expose for exactly this purpose
(their own CLIs are unchanged and still work standalone — validate_all.sh
still calls them independently for a full pack sweep).

Scoping (plan §WP1 — "if templates are copied, why browser checks at all?"):
  - overflow + collisions: EVERY file (the one thing byte-copying cannot fix —
    layout after content edits, which only a layout engine can judge).
  - paint (silent-paint-reference check): only files whose `deck-state.json`
    entry has visual in {chart, pipeline, bespoke}. When no deck-state.json is
    present for a file (no --deck-dir, or the file isn't listed), paint runs
    anyway — the safe fallback when we cannot tell what the slide contains.
  - contrast: computed for every file (cheap — same page load), but does NOT
    gate pass/fail by default — pass `--contrast` to count hard FAILs (the
    orchestrator's whole-deck `qa.py --deck-dir` run does this; a chunk-level
    `qa.py --files` re-check does not, so a designer's fix-and-recheck loop
    isn't gated on a judgment call brand-audit already owns). The "N element(s)
    over gradient — verify manually" notes are additionally suppressed unless
    --verbose, contrast-counted or not.

Usage:
    render_checks.py FILE...       [--deck-dir D] [--json] [--verbose] [--contrast]

Exit code 0 = clean; 1 = at least one overflow/collision/paint FAIL, or a hard
contrast FAIL when --contrast was passed.
"""
import argparse
import json as jsonlib
import os
import sys

from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ds_config import load  # noqa: E402
import check_contrast  # noqa: E402
import check_overflow  # noqa: E402
import check_paint  # noqa: E402

PAINT_VISUALS = {"chart", "pipeline", "bespoke"}


def load_visuals(deck_dir):
    """{filename: visual} from <deck_dir>/deck-state.json, or {} if absent/unreadable."""
    if not deck_dir:
        return {}
    path = os.path.join(deck_dir, "deck-state.json")
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            data = jsonlib.load(f)
    except Exception:
        return {}
    out = {}
    for s in data.get("slides", []) or []:
        fn = s.get("file")
        if fn:
            out[fn] = s.get("visual")
    return out


def run(paths, ds, deck_dir=None, verbose=False, count_contrast=True):
    """Returns (per_file_results: dict, total_failures: int).

    `count_contrast` (WP1 scoping, tightened 2026-09 per the doctrine agent's
    handoff): whether contrast hard-FAILs count toward `total_failures` /
    `entry["pass"]`. Contrast is meant to be reported ONCE, in the
    orchestrator's whole-deck run — not per chunk, where it would gate a
    designer's `qa.py --files` re-check on a judgment call brand-audit already
    owns. Contrast is still COMPUTED and returned in every entry either way
    (cheap — same page load); only whether it GATES varies. Callers: qa.py sets
    this to True for `--deck-dir` without `--files` (or when `--contrast` is
    passed explicitly), False otherwise.
    """
    visuals = load_visuals(deck_dir)
    do_collisions = ds.rule("banElementCollisions")
    tol = float(ds.get("collisionTolerancePx", 4))
    cw, ch = ds.canvas

    results = {}
    total_failures = 0
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": cw, "height": ch})
        for path in paths:
            name = os.path.basename(path)
            page.goto("file://" + os.path.abspath(path), wait_until="networkidle")
            page.evaluate("document.fonts.ready || Promise.resolve()")
            page.wait_for_timeout(400)  # let the Tailwind CDN inject styles

            entry = {"file": name, "overflow": [], "collisions": [], "paint": [],
                     "contrast_fails": [], "contrast_manual": 0, "errors": []}

            # overflow — every file
            viol, err = check_overflow.analyze_overflow_page(page, ds, name)
            if viol is None:
                entry["errors"].append(err)
            else:
                entry["overflow"] = viol
                total_failures += len(viol)

            # collisions — every file, if the pack turns the rule on
            if do_collisions:
                cols, err = check_overflow.analyze_collisions_page(page, tol)
                if cols is None:
                    entry["errors"].append(err)
                else:
                    entry["collisions"] = cols
                    total_failures += len(cols)

            # contrast — computed for every file regardless (cheap, same page load);
            # whether it GATES (counts toward total_failures/pass) depends on scope.
            fails, manual = check_contrast.analyze_page(page)
            if fails is None:
                entry["errors"].append(manual)
            else:
                entry["contrast_fails"] = fails
                entry["contrast_manual"] = manual
                if count_contrast:
                    total_failures += len(fails)

            # paint — chart/pipeline/bespoke visuals, or unconditionally when we have
            # no deck-state.json to tell us otherwise (safe fallback).
            visual = visuals.get(name)
            run_paint = (visual in PAINT_VISUALS) or (not deck_dir) or (name not in visuals)
            if run_paint:
                pviol, err = check_paint.analyze_paint_page(page)
                if pviol is None:
                    entry["errors"].append(err)
                else:
                    entry["paint"] = pviol
                    total_failures += len(pviol)

            entry["visual"] = visual
            entry["contrast_counted"] = count_contrast
            entry["pass"] = not (entry["overflow"] or entry["collisions"] or
                                 entry["paint"] or entry["errors"] or
                                 (count_contrast and entry["contrast_fails"]))
            results[name] = entry
        browser.close()
    return results, total_failures


def print_report(results, verbose=False, show_contrast=None):
    """`show_contrast=None` (default) shows contrast FAILs only for entries where
    they were counted (`contrast_counted`) — i.e. matches whatever scope `run()`
    was called with. Pass True/False to force it either way."""
    for name, entry in results.items():
        lines = []
        for err in entry["errors"]:
            lines.append(f"  FAIL  {err}")
        lines += check_overflow.format_overflow_report(name, entry["overflow"])[1:] if entry["overflow"] else []
        if do_collisions_present(entry):
            lines += check_overflow.format_collisions_report(name, entry["collisions"])[1:]
        lines += check_paint.format_paint_report(name, entry["paint"])[1:] if entry["paint"] else []
        want_contrast = entry.get("contrast_counted", True) if show_contrast is None else show_contrast
        if want_contrast:
            lines += check_contrast.format_report(
                name, entry["contrast_fails"], entry["contrast_manual"], verbose=verbose)[1:]
        if lines:
            print(name)
            for line in lines:
                print(line)


def do_collisions_present(entry):
    return bool(entry.get("collisions"))


def to_jsonable(results):
    """Strip Playwright/DOM-shaped dicts down to plain JSON-safe structures."""
    out = {}
    for name, entry in results.items():
        out[name] = {
            "file": entry["file"],
            "visual": entry["visual"],
            "pass": entry["pass"],
            "overflow": entry["overflow"],
            "collisions": entry["collisions"],
            "paint": entry["paint"],
            "contrast_fails": [
                {"tag": it["tag"], "text": it["text"], "ratio": round(ratio, 2), "need": need}
                for it, ratio, need in entry["contrast_fails"]
            ],
            "contrast_manual": entry["contrast_manual"],
            "contrast_counted": entry.get("contrast_counted", True),
            "errors": entry["errors"],
        }
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.strip().split("\n")[0])
    ap.add_argument("files", nargs="+", metavar="FILE")
    ap.add_argument("--deck-dir", default=None,
                    help="Deck folder holding deck-state.json (scopes the paint check)")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--verbose", action="store_true",
                    help="Include 'verify manually' contrast notes")
    ap.add_argument("--contrast", action="store_true",
                    help="Count contrast hard-FAILs toward pass/fail (default: computed and "
                        "reported in --json, but does not gate — contrast is a whole-deck, "
                        "not a per-chunk, concern; see qa.py)")
    args = ap.parse_args()

    missing = [f for f in args.files if not os.path.isfile(f)]
    if missing:
        for m in missing:
            print(f"error: no such file: {m}", file=sys.stderr)
        sys.exit(2)

    ds = load()
    deck_dir = args.deck_dir or (os.path.dirname(os.path.abspath(args.files[0])) if args.files else None)
    results, total_failures = run(args.files, ds, deck_dir=deck_dir, verbose=args.verbose,
                                  count_contrast=args.contrast)

    if args.json:
        print(jsonlib.dumps({"files": to_jsonable(results),
                             "total_failures": total_failures}, indent=2, ensure_ascii=False))
    else:
        print_report(results, verbose=args.verbose)
        n = len(args.files)
        if total_failures:
            print(f"\n{total_failures} render-check failure(s) across {n} file(s).")
        else:
            print(f"All {n} file(s) pass overflow/collision/paint/contrast checks.")

    sys.exit(1 if total_failures else 0)


if __name__ == "__main__":
    main()
