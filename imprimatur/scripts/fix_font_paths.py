#!/usr/bin/env python3
"""
Deck-local font setup — design-system agnostic.

Kills the fragile "count the ../ levels back to the design system" font-path arithmetic
(the root cause of the blue-rectangle gradient artifact when the depth guess is wrong):
fonts are copied INTO the deck folder once, and every slide references them as
`fonts/<file>` — one level, no arithmetic. That relative form resolves identically in
every context the pipeline touches:

  - file:// (double-clicking a slide)
  - deck-render / deck-review servers rooted at the deck dir
  - pdf-export's server rooted at the filesystem root

What it does, per run (idempotent):
  1. Scans the deck's NN-*.html slides for @font-face url(...) references.
  2. Copies each referenced font file (matched by basename against the ACTIVE design
     system's fonts/ dir) into <deck-dir>/fonts/.
  3. Rewrites the url(...) to 'fonts/<basename>'.

Usage:
    python3 scripts/fix_font_paths.py --deck-dir /path/to/deck [--dry-run]
"""

import argparse
import glob
import os
import re
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ds_config import load  # noqa: E402

URL_RE = re.compile(r"url\(\s*['\"]?([^'\")]+\.(?:ttf|woff2?|otf))['\"]?\s*\)")


def main():
    ap = argparse.ArgumentParser(description="Copy fonts into the deck folder and localize @font-face URLs.")
    ap.add_argument("--deck-dir", required=True)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    ds = load()
    deck = os.path.abspath(args.deck_dir)
    if not os.path.isdir(deck):
        sys.exit(f"deck dir not found: {deck}")
    ds_files = {os.path.basename(p): p for p in glob.glob(os.path.join(ds.fonts_dir, '*'))}
    fonts_dir = os.path.join(deck, 'fonts')

    slides = sorted(glob.glob(os.path.join(deck, '[0-9]*.html')))
    if not slides:
        sys.exit(f"no NN-*.html slides in {deck}")

    copied, rewritten, unknown = set(), 0, set()
    for path in slides:
        s = open(path, encoding='utf-8').read()
        changed = False

        def repl(m):
            nonlocal changed
            url = m.group(1)
            base = os.path.basename(url)
            if base not in ds_files:
                unknown.add(url)
                return m.group(0)
            copied.add(base)
            local = f"fonts/{base}"
            if url == local:
                return m.group(0)  # already deck-local
            changed = True
            return f"url('{local}')"

        s2 = URL_RE.sub(repl, s)
        if changed and not args.dry_run:
            open(path, 'w', encoding='utf-8').write(s2)
        if changed:
            rewritten += 1
            print(f"rewrote font URLs: {os.path.basename(path)}")

    if copied and not args.dry_run:
        os.makedirs(fonts_dir, exist_ok=True)
        for base in sorted(copied):
            dst = os.path.join(fonts_dir, base)
            if not os.path.isfile(dst):
                shutil.copy2(ds_files[base], dst)
                print(f"copied: fonts/{base}")

    for u in sorted(unknown):
        print(f"warn: unknown font reference left untouched: {u}")
    print(f"{len(slides)} slide(s) scanned, {rewritten} rewritten, "
          f"{len(copied)} font file(s) ensured in {fonts_dir}"
          + (" [dry-run]" if args.dry_run else ""))


if __name__ == '__main__':
    main()
