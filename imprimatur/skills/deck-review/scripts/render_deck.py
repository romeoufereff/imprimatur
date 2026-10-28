#!/usr/bin/env python3
"""
Render every slide of a FOREIGN deck (one HTML file holding all slides), fully revealed,
to PNG — the input for a design critique of a deck that is not an imprimatur folder.

Each slide is shown through the deck's own navigation (--hash, else the active class),
then frozen by qa_deck.js: build steps revealed, <details> open, transitions and CSS
animations at their end (the freeze outranks a deck's own `!important` transition rules).
The capture waits two animation frames and --capture-delay ms after that: a screenshot
taken right after a style change can still show the previous frame.

With --chunk N it also writes chunks.txt — the PNGs in groups of at most N, one line per
group — so critique passes can run in parallel (deck-review §6, foreign decks: ≤ 14).

Usage:
    render_deck.py DECK.html OUT_DIR [--prefix s] [--slide .slide] [--hash '#slide={n}']
                   [--reveal '.reveal:shown'] [--viewport 1600x1000] [--slides 2,5-9]
                   [--chunk 14]
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from qa_deck import add_common, configure, open_deck, slide_list  # noqa: E402


def main():
    from playwright.sync_api import sync_playwright
    ap = argparse.ArgumentParser(description=__doc__.strip().split("\n")[0])
    add_common(ap)
    ap.add_argument("out", help="output folder for the PNGs")
    ap.add_argument("--prefix", default="s", help="file prefix: <prefix>NN.png (default s)")
    ap.add_argument("--capture-delay", type=int, default=150, help="ms after the freeze before capture (default 150)")
    ap.add_argument("--scale", type=float, default=1, help="device scale factor (default 1)")
    ap.add_argument("--chunk", type=int, default=0, help="also write chunks.txt with groups of at most N PNGs")
    args = ap.parse_args()
    if not os.path.isfile(args.deck):
        sys.exit(f"error: no such file: {args.deck}")
    os.makedirs(args.out, exist_ok=True)

    written = []
    with sync_playwright() as p:
        browser, page = open_deck(p, args, args.scale)
        configure(page, args)
        n = page.evaluate("__qa.slides().length")
        if not n:
            sys.exit(f"error: no slides match {args.slide!r}")
        for i in slide_list(args.slides, n) or range(1, n + 1):
            page.evaluate("async n => { await __qa.goto(n); await __qa.freeze(__qa.current()); }", i)
            page.wait_for_timeout(args.capture_delay)
            page.evaluate("__qa.frames()")
            path = os.path.join(args.out, f"{args.prefix}{i:02d}.png")
            page.evaluate("() => { const s = __qa.current(); s.setAttribute('data-qa-shot', '1'); }")
            page.locator("[data-qa-shot='1']").screenshot(path=path)
            page.evaluate("() => document.querySelectorAll('[data-qa-shot]').forEach(e => e.removeAttribute('data-qa-shot'))")
            written.append(path)
        browser.close()

    if args.chunk:
        groups = [written[k:k + args.chunk] for k in range(0, len(written), args.chunk)]
        with open(os.path.join(args.out, "chunks.txt"), "w", encoding="utf-8") as f:
            for g in groups:
                f.write(" ".join(os.path.basename(x) for x in g) + "\n")
        print(f"chunks: {len(groups)} group(s) of ≤ {args.chunk} → {os.path.join(args.out, 'chunks.txt')}")
    print(f"rendered {len(written)} slide(s) → {args.out}")


if __name__ == "__main__":
    main()
