#!/usr/bin/env python3
"""
deck-review — slide render + measurement helper (the "measure, don't eyeball" tool).

Renders a slide HTML file in headless WebKit (Safari's engine — the strictest
renderer; it catches SVG/gradient bugs Chromium silently tolerates) at the
native 1920x1080 viewport and optionally crops/zooms or pixel-samples the
result. Replaces the inline Playwright snippets previously retyped every
review iteration.

Usage:
    render.py <slide.html> --out /tmp/slide.png
    render.py <slide.html> --out /tmp/zoom.png --crop 680,280,580,340 --zoom 3
    render.py <slide.html> --sample-column 960 --sample-range 500,620 [--step 4]
    render.py <slide.html> --out /tmp/s.png --engine chromium   # if ever needed

Flags:
    --crop x,y,w,h       Crop the screenshot to this pixel box before saving.
    --zoom N             Upscale the (cropped) image N× with Lanczos for close
                         inspection of connector/arrowhead geometry.
    --sample-column X    Print pixel RGBA values down column X (screen coords)
                         instead of / in addition to saving an image. Use to
                         PROVE a stroke or gap exists rather than squinting.
    --sample-range A,B   Row range for --sample-column (default 0,1080).
    --step N             Row step for sampling (default 4).
    --engine             webkit (default) | chromium | firefox.

Exit code 0 on success. Prints the saved path(s).
"""

import argparse
import os
import sys

from playwright.sync_api import sync_playwright


def main():
    ap = argparse.ArgumentParser(description="Render a slide in WebKit; crop/zoom/pixel-sample.")
    ap.add_argument("slide", help="Path to the slide .html file")
    ap.add_argument("--out", help="Output PNG path (omit if only sampling)")
    ap.add_argument("--crop", help="x,y,w,h crop box in screen pixels")
    ap.add_argument("--zoom", type=int, default=1, help="Integer upscale factor after crop")
    ap.add_argument("--sample-column", type=int, help="Sample pixel colors down this x column")
    ap.add_argument("--sample-range", default="0,1080", help="y0,y1 row range for sampling")
    ap.add_argument("--step", type=int, default=4, help="Row step for sampling")
    ap.add_argument("--engine", default="webkit", choices=["webkit", "chromium", "firefox"])
    args = ap.parse_args()

    if not args.out and args.sample_column is None:
        sys.exit("error: nothing to do — pass --out and/or --sample-column")

    slide = os.path.abspath(args.slide)
    if not os.path.isfile(slide):
        sys.exit(f"error: no such file: {slide}")

    raw_png = args.out or "/tmp/_render_sample.png"

    with sync_playwright() as p:
        browser = getattr(p, args.engine).launch()
        page = browser.new_page(viewport={"width": 1920, "height": 1080})
        page.goto("file://" + slide, wait_until="networkidle")
        page.evaluate("document.fonts.ready || Promise.resolve()")
        page.wait_for_timeout(400)
        page.screenshot(path=raw_png)
        browser.close()

    from PIL import Image  # deferred: not needed until post-processing

    img = Image.open(raw_png)

    if args.sample_column is not None:
        y0, y1 = (int(v) for v in args.sample_range.split(","))
        x = args.sample_column
        print(f"-- pixel sample: x={x}, y {y0}..{y1} step {args.step} ({args.engine})")
        for y in range(y0, min(y1, img.height), args.step):
            print(y, img.getpixel((x, y)))

    if args.out:
        if args.crop:
            x, y, w, h = (int(v) for v in args.crop.split(","))
            img = img.crop((x, y, x + w, y + h))
        if args.zoom > 1:
            img = img.resize((img.width * args.zoom, img.height * args.zoom), Image.LANCZOS)
        img.save(args.out)
        print(f"saved {args.out} ({img.width}x{img.height})")


if __name__ == "__main__":
    main()
