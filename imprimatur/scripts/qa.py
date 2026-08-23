#!/usr/bin/env python3
"""
One-call slide QA wrapper — design-system agnostic.

Runs the full mechanical audit on one or more slide files in a single command,
replacing the validate + overflow (+ render) triple that otherwise gets retyped
on every revision loop:

    1. validate.py        — grep-level brand rules (tokens, font floors, scaler)
    2. check_contrast.py  — render-level WCAG AA contrast (Playwright/Chromium)
    3. check_overflow.py  — render-level canvas bounds (Playwright/Chromium)
    4. check_paint.py     — render-level "did it actually paint" (Playwright/Chromium)
    5. optional WebKit render via deck-review/scripts/render.py (--render)

Usage:
    qa.py <slide.html> [<slide2.html> ...]
    qa.py <slide.html> --render /tmp/slide.png      # also save a WebKit screenshot

Exit code 0 only if every step passes.
"""

import argparse
import os
import subprocess
import sys

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
RENDER = os.path.normpath(os.path.join(
    SCRIPTS_DIR, "..", "skills", "deck-review", "scripts", "render.py"))


def run(label, cmd):
    print(f"== {label} ==")
    r = subprocess.run(cmd)
    if r.returncode != 0:
        print(f"FAIL: {label}")
    return r.returncode


def main():
    ap = argparse.ArgumentParser(description="Run validate + overflow (+ render) on slides.")
    ap.add_argument("slides", nargs="+", help="Slide .html files")
    ap.add_argument("--render", metavar="OUT_PNG",
                    help="Also render the FIRST slide to this PNG via WebKit (render.py)")
    args = ap.parse_args()

    py = sys.executable
    rc = 0
    rc |= run("validate.py", [py, os.path.join(SCRIPTS_DIR, "validate.py"), *args.slides])
    rc |= run("check_contrast.py", [py, os.path.join(SCRIPTS_DIR, "check_contrast.py"), *args.slides])
    rc |= run("check_overflow.py", [py, os.path.join(SCRIPTS_DIR, "check_overflow.py"), *args.slides])
    rc |= run("check_paint.py", [py, os.path.join(SCRIPTS_DIR, "check_paint.py"), *args.slides])

    if args.render:
        if os.path.isfile(RENDER):
            rc |= run("render.py (WebKit)", [py, RENDER, args.slides[0], "--out", args.render])
        else:
            print(f"warn: render.py not found at {RENDER}; skipping render step")

    sys.exit(1 if rc else 0)


if __name__ == "__main__":
    main()
