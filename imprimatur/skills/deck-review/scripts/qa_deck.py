#!/usr/bin/env python3
"""
QA for a FOREIGN deck — one HTML file holding every slide (an interactive presentation
someone else built), not an imprimatur NN-*.html folder.

Loads the deck in headless Chromium, injects qa_deck.js, walks every slide, freezes it
fully revealed (build steps shown, <details> open, transitions and animations at their end)
and runs the checks: text leaving its box, the footer row or the slide; text on text;
connectors through text; arrow tips buried or short; connector stroke contrast; SVG label
overlaps; accent stripes (left bars, top-stripe cards); cards in one row that end at
different heights; text cramped against a rounded card's edge; the smallest rendered text. The rules behind each are
listed at the top of qa_deck.js. Nothing in either file knows a deck's class names: the
slide selector, navigation, build-step classes and footer row come from the flags.

The text floor defaults to the active pack's typography.minFontSizePx scaled from the
pack canvas to the deck's own stage width (18 px on 1920 → 13.5 px on a 1440 stage).

Usage:
    qa_deck.py DECK.html [--slide .slide] [--hash '#slide={n}'] [--reveal '.reveal:shown']
               [--footer SEL] [--chrome SEL] [--checks fit,svg,bars,rows,pad,minfont]
               [--slides 1,4-7] [--min-font PX] [--allow known.txt] [--json]

--allow FILE: one substring per line; a finding containing one is reported as accepted
(a verified false positive or a deliberate choice), not as a failure. Keep the reason on
the line after a '#'.

Exit 0 when every finding is accepted.
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
QA_JS = os.path.join(HERE, "qa_deck.js")


def slide_list(spec, n):
    if not spec:
        return None
    out = []
    for part in spec.split(","):
        a, _, b = part.partition("-")
        out += list(range(int(a), int(b or a) + 1))
    return [i for i in out if 1 <= i <= n]


def pack_floor():
    """(floor px, canvas width) from the active pack, or (None, None) without one."""
    sys.path.insert(0, os.path.join(HERE, "..", "..", "..", "scripts"))
    try:
        from ds_config import load
        ds = load()
        return float(ds.get("typography.minFontSizePx", 0) or 0) or None, ds.canvas[0]
    except Exception:
        return None, None


def add_common(ap):
    """Flags shared with render_deck.py: how to find, show and reveal a slide."""
    ap.add_argument("deck", help="the deck's .html file")
    ap.add_argument("--slide", default=".slide", help="selector matching every slide (default .slide)")
    ap.add_argument("--active", default=None, help="selector of the slide on show (default: <slide>.active, else the most visible)")
    ap.add_argument("--hash", default=None, help="navigation by URL hash, e.g. '#slide={n}' or '#/{i}'; default: toggle --active-class")
    ap.add_argument("--active-class", default="active")
    ap.add_argument("--reveal", action="append", default=[], metavar="SEL:CLASSES",
                    help="build steps to show at once, e.g. '.reveal:shown' or '.fragment:visible' (repeatable)")
    ap.add_argument("--viewport", default="1600x1000")
    ap.add_argument("--settle", type=int, default=250, help="ms to wait after navigating (default 250)")
    ap.add_argument("--slides", default=None, help="only these slides, e.g. 1,4-7")


def configure(page, args, extra=None):
    with open(QA_JS, encoding="utf-8") as f:
        page.evaluate(f.read())
    cfg = {"slide": args.slide, "active": args.active, "hash": args.hash, "activeClass": args.active_class,
           "reveal": [r.split(":", 1) for r in args.reveal], "settle": args.settle}
    cfg.update(extra or {})
    page.evaluate("c => __qa.configure(c)", cfg)


def open_deck(p, args, scale=1):
    w, h = (int(v) for v in args.viewport.lower().split("x"))
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": w, "height": h}, device_scale_factor=scale)
    page.goto("file://" + os.path.abspath(args.deck), wait_until="load")
    page.evaluate("document.fonts.ready.then(() => true)")
    page.wait_for_timeout(300)
    return browser, page


def main():
    from playwright.sync_api import sync_playwright
    ap = argparse.ArgumentParser(description=__doc__.strip().split("\n")[0])
    add_common(ap)
    ap.add_argument("--footer", default=None, help="selector(s) of the footer row text must stay clear of")
    ap.add_argument("--chrome", default=None, help="selector(s) skipped for box spills (page numbers, nav)")
    ap.add_argument("--checks", default="fit,svg,bars,rows,pad,minfont")
    ap.add_argument("--min-font", type=float, default=None, help="text floor in the deck's stage px")
    ap.add_argument("--allow", default=None, help="file of accepted-finding substrings")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    if not os.path.isfile(args.deck):
        sys.exit(f"error: no such file: {args.deck}")
    allow = []
    if args.allow:
        for ln in open(args.allow, encoding="utf-8"):
            s = ln.split("#", 1)[0].strip()
            if s:
                allow.append(s)
    checks = [c.strip() for c in args.checks.split(",") if c.strip()]

    with sync_playwright() as p:
        browser, page = open_deck(p, args)
        extra = {k: v for k, v in (("footer", args.footer), ("chrome", args.chrome)) if v}
        configure(page, args, extra)
        n = page.evaluate("__qa.slides().length")
        if not n:
            sys.exit(f"error: no slides match {args.slide!r}")
        floor = args.min_font
        if floor is None and "minfont" in checks:
            pf, cw = pack_floor()
            page.evaluate("n => __qa.goto(n)", 1)
            stage = page.evaluate("__qa.current().offsetWidth")
            floor = round(pf * stage / cw, 2) if pf and cw and stage else None
        page.evaluate("c => __qa.configure(c)", {"minFont": floor})
        which = slide_list(args.slides, n)
        res = page.evaluate("([c, w]) => __qa.runSlides(c, w)", [checks, which])
        browser.close()

    failing, accepted = {}, {}
    for k, rows in res.items():
        for r in rows:
            (accepted if any(a in r for a in allow) else failing).setdefault(int(k), []).append(r)
    if args.json:
        print(json.dumps({"slides": n, "min_font": floor, "failing": failing, "accepted": accepted},
                         indent=2, ensure_ascii=False))
    else:
        for i in sorted(failing):
            print(f"slide {i:02d}")
            for r in failing[i]:
                print("  FAIL  " + r)
        acc = sum(len(v) for v in accepted.values())
        total = sum(len(v) for v in failing.values())
        print(f"\n{n} slide(s) · floor {floor} px · {total} finding(s)"
              + (f" · {acc} accepted" if acc else ""))
    sys.exit(1 if failing else 0)


if __name__ == "__main__":
    main()
