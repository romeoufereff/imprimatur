#!/usr/bin/env python3
"""
One-call slide QA wrapper — design-system agnostic (WP1).

Runs the full mechanical audit on one or more slide files in a single command:

    1. validate.py         — grep-level brand rules (tokens, font floors, scaler,
                              head-identity — imported directly, no subprocess)
    2. render_checks.py    — ONE Chromium launch for every file: overflow +
                              collisions (every file), paint (bespoke/chart/pipeline
                              visuals, or unconditionally with no deck-state.json),
                              contrast (always computed; only GATES pass/fail on a
                              whole-deck run — --deck-dir without --files — or with
                              --contrast; a --files chunk run reports it but never
                              fails on it, since it's brand-audit's call, once per
                              deck, not once per chunk — see --contrast below)
    3. optional WebKit render via deck-review/scripts/render.py (--render)

This replaces the old validate+contrast+overflow+paint quadruple-subprocess (four
Chromium launches per invocation) that made a "manual qa.py re-run" cost 15-30s.

Usage:
    qa.py <slide.html> [<slide2.html> ...]        # explicit files (legacy form)
    qa.py --files a.html b.html ...
    qa.py --deck-dir /path/to/deck                # every NN-*.html in the deck
                                                    # (deck-state.json's slide list,
                                                    # when present, filters out
                                                    # orphan/archived files)
    qa.py <slide.html> --render /tmp/slide.png [--scale 0.5]
    qa.py --deck-dir D --json

Exit code 0 only if every step passes.
"""

import argparse
import glob
import json as jsonlib
import os
import re
import sys

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPTS_DIR)
RENDER = os.path.normpath(os.path.join(
    SCRIPTS_DIR, "..", "skills", "deck-review", "scripts", "render.py"))

import validate  # noqa: E402
import render_checks  # noqa: E402
from ds_config import load  # noqa: E402

SLIDE_RE = re.compile(r"^\d{2}-.*\.html$")


def resolve_targets(args):
    """Returns (targets: list[str], deck_dir: str|None)."""
    if args.deck_dir:
        deck_dir = os.path.abspath(args.deck_dir)
        if not os.path.isdir(deck_dir):
            sys.exit(f"error: no such deck dir: {deck_dir}")
        on_disk = sorted(f for f in os.listdir(deck_dir) if SLIDE_RE.match(f))
        state_path = os.path.join(deck_dir, "deck-state.json")
        known = None
        if os.path.isfile(state_path):
            try:
                with open(state_path, encoding="utf-8") as f:
                    data = jsonlib.load(f)
                known = {s["file"] for s in data.get("slides", []) or [] if s.get("file")}
            except Exception:
                known = None
        # deck-state.json's slide list, when present, is the source of truth for
        # WHICH files are live slides — orphan/archived NN-*.html on disk that
        # deck-state.json doesn't know about are silently skipped (WP8).
        # An empty or absent slide list (deck-state.json written at intake, before
        # any slide exists) means "no opinion yet" — fall back to what is on disk.
        names = sorted(known & set(on_disk)) if known else on_disk
        targets = [os.path.join(deck_dir, n) for n in names]
        if args.files:
            wanted = set(args.files)
            targets = [t for t in targets if os.path.basename(t) in wanted or t in wanted]
        return targets, deck_dir

    if args.files:
        targets = args.files
    elif args.slides:
        targets = args.slides
    else:
        sys.exit("error: nothing to check — pass FILE(s), --files, or --deck-dir")

    missing = [t for t in targets if not os.path.isfile(t)]
    if missing:
        for m in missing:
            print(f"error: no such file: {m}", file=sys.stderr)
        sys.exit(2)
    deck_dir = os.path.dirname(os.path.abspath(targets[0])) if targets else None
    return [os.path.abspath(t) for t in targets], deck_dir


def run_validate(targets, ds):
    """Returns ({filename: {"fails": [...], "warns": [...]}}, total_fail_count)."""
    tokens, gradients = validate.canonical_tokens(ds)
    palette = validate.allowed_hexes(ds)
    template_stems = {os.path.splitext(os.path.basename(p))[0]
                      for p in glob.glob(os.path.join(ds.templates_dir, "*.html"))}
    out, total = {}, 0
    for path in targets:
        fails, warns = validate.check_file(path, ds, tokens, gradients, palette, template_stems)
        out[os.path.basename(path)] = {"fails": fails, "warns": warns}
        total += len(fails)
    return out, total


def print_human(validate_results, render_results, verbose):
    for name, v in validate_results.items():
        if v["fails"] or v["warns"]:
            print(name)
            for f in v["fails"]:
                print(f"  FAIL  {f}")
            for w in v["warns"]:
                print(f"  warn  {w}")
    render_checks.print_report(render_results, verbose=verbose)


def main():
    ap = argparse.ArgumentParser(description="Run validate.py + render_checks.py (+ optional render) on slides.")
    ap.add_argument("slides", nargs="*", help="Slide .html files (legacy positional form)")
    ap.add_argument("--files", nargs="+", metavar="FILE", help="Explicit slide files")
    ap.add_argument("--deck-dir", metavar="D", help="Check every NN-*.html slide in this deck folder")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--verbose", action="store_true",
                    help="Include contrast 'verify manually' notes")
    ap.add_argument("--contrast", action="store_true",
                    help="Force contrast hard-FAILs to count toward pass/fail even in a "
                         "--files chunk run (default: they always count for --deck-dir "
                         "without --files — the orchestrator's whole-deck run — and are "
                         "computed-but-non-gating everywhere else, since contrast is "
                         "reported once per deck, not once per chunk)")
    ap.add_argument("--render", metavar="OUT_PNG",
                    help="Also render the FIRST target to this PNG via WebKit (render.py)")
    ap.add_argument("--scale", type=float, default=0.5,
                    help="Downscale the --render PNG by this factor (default 0.5 -> 960x540; "
                         "pass 1.0 for full 1920x1080). The designer only needs a render to "
                         "eyeball, not a full-resolution export (WP7).")
    args = ap.parse_args()

    targets, deck_dir = resolve_targets(args)
    if not targets:
        print("nothing to check.")
        sys.exit(0)

    # Contrast scoping: hard-FAILs count in a whole-deck run (--deck-dir without
    # --files — the orchestrator's pass) or whenever --contrast is passed
    # explicitly; a --files chunk run (designer_stop_gate.py, a designer's own
    # fix-and-recheck loop) computes contrast but does not gate on it — that is
    # brand-audit's judgment call to make once for the whole deck, not a reason
    # to bounce a chunk back and forth.
    whole_deck_run = bool(args.deck_dir) and not args.files
    count_contrast = args.contrast or whole_deck_run

    ds = load()
    validate_results, validate_fails = run_validate(targets, ds)
    render_results, render_fails = render_checks.run(
        targets, ds, deck_dir=deck_dir, verbose=args.verbose, count_contrast=count_contrast)
    total_fails = validate_fails + render_fails

    if args.json:
        out = {
            "validate": validate_results,
            "render_checks": render_checks.to_jsonable(render_results),
            "total_failures": total_fails,
            "pass": total_fails == 0,
        }
        print(jsonlib.dumps(out, indent=2, ensure_ascii=False))
    else:
        print_human(validate_results, render_results, args.verbose)
        n = len(targets)
        if total_fails:
            print(f"\n{total_fails} failure(s) across {n} file(s). [{ds.name}]")
        else:
            print(f"All {n} file(s) pass. [{ds.name}]")

    if args.render:
        if os.path.isfile(RENDER):
            import subprocess
            raw = args.render
            need_scale = args.scale and args.scale != 1.0
            tmp_out = raw + ".full.png" if need_scale else raw
            r = subprocess.run([sys.executable, RENDER, targets[0], "--out", tmp_out])
            if r.returncode == 0 and need_scale:
                try:
                    from PIL import Image
                    img = Image.open(tmp_out)
                    img = img.resize((max(1, int(img.width * args.scale)),
                                      max(1, int(img.height * args.scale))), Image.LANCZOS)
                    img.save(raw)
                    os.remove(tmp_out)
                    print(f"saved {raw} ({img.width}x{img.height}, scale={args.scale})")
                except Exception as e:
                    print(f"warn: scale post-process failed ({e}); kept full-res at {tmp_out}")
        else:
            print(f"warn: render.py not found at {RENDER}; skipping render step")

    sys.exit(1 if total_fails else 0)


if __name__ == "__main__":
    main()
