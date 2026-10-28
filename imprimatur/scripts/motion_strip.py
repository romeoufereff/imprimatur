#!/usr/bin/env python3
"""
Filmstrip of a choreographed slide's entrance — the way to LOOK at motion without watching it.

Opens the slide in a browser that does not announce automation (so the runtime plays), waits
for the timeline to build, then captures N frames spread across the entrance (plus one at the
end) and tiles them into one PNG with the time stamp on each frame. The motion director and
the orchestrator read this once instead of narrating the animation to themselves.

Usage:
    motion_strip.py <slide.html> [--out strip.png] [--frames 8] [--scale 0.35] [--until SEC]
"""
import argparse
import io
import os
import sys


def main():
    ap = argparse.ArgumentParser(description=__doc__.strip().split("\n")[0])
    ap.add_argument("slide")
    ap.add_argument("--out", default=None)
    ap.add_argument("--frames", type=int, default=8)
    ap.add_argument("--scale", type=float, default=0.35, help="Frame scale (0.35 → 672×378 per frame)")
    ap.add_argument("--until", type=float, default=None, help="Seconds to cover (default: the entrance + 0.4 s)")
    args = ap.parse_args()
    path = os.path.abspath(args.slide)
    if not os.path.isfile(path):
        sys.exit(f"error: no such file: {path}")
    out = args.out or os.path.splitext(path)[0] + ".strip.png"

    from playwright.sync_api import sync_playwright
    from PIL import Image, ImageDraw
    frames = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--disable-blink-features=AutomationControlled", "--deterministic-mode",
                                       "--run-all-compositor-stages-before-draw", "--disable-threaded-animation",
                                       "--font-render-hinting=none", "--force-color-profile=srgb"])   # reproducible pixels (1.6.0)
        page = browser.new_page(viewport={"width": 1920, "height": 1080})
        page.goto("file://" + path, wait_until="networkidle")
        try:
            page.wait_for_function("window.__imprimaturMotion && window.__imprimaturMotion.info", timeout=15000)
        except Exception:
            sys.exit("error: the slide has no motion runtime (not choreographed?) or GSAP did not load")
        info = page.evaluate("window.__imprimaturMotion.info")
        if info.get("error"):
            sys.exit(f"error: runtime reported {info['error']}")
        # drive the timeline deterministically: pause it and seek to each sample time
        total = (args.until if args.until else info.get("total_ms", 1600) / 1000.0 + 0.4)
        # Freeze everything the runtime drives (entrance + idle), then seek frame by frame. The
        # screenshot is a page clip of #slide's box: an element screenshot would wait for the
        # element to be "stable", which an animating child defeats (it hung for 300 s in CI).
        page.evaluate("() => { const m = window.__imprimaturMotion; m.tl.pause(0); if (m.idle) m.idle.pause(0); }")
        box = page.evaluate("() => { const r = document.getElementById('slide').getBoundingClientRect(); return {x: r.left, y: r.top, width: r.width, height: r.height}; }")
        clip = {"x": max(0, box["x"]), "y": max(0, box["y"]), "width": max(1, min(1920, box["width"])), "height": max(1, min(1080, box["height"]))}
        n = max(2, args.frames)
        times = [round(total * i / (n - 1), 2) for i in range(n)]
        for t in times:
            page.evaluate("t => { const m = window.__imprimaturMotion; m.tl.pause(); m.tl.time(Math.min(t, m.tl.duration()), true); if (m.idle) m.idle.pause(0); }", t)
            page.wait_for_timeout(60)
            png = page.screenshot(clip=clip, timeout=10000)
            frames.append((t, Image.open(io.BytesIO(png)).convert("RGB")))
        browser.close()

    w, h = frames[0][1].size
    fw, fh = int(w * args.scale), int(h * args.scale)
    cols = 4 if n > 4 else n
    rows = (n + cols - 1) // cols
    pad = 8
    strip = Image.new("RGB", (cols * (fw + pad) + pad, rows * (fh + pad + 18) + pad), (24, 24, 24))
    draw = ImageDraw.Draw(strip)
    for i, (t, im) in enumerate(frames):
        x = pad + (i % cols) * (fw + pad)
        y = pad + (i // cols) * (fh + pad + 18)
        strip.paste(im.resize((fw, fh), Image.LANCZOS), (x, y + 18))
        draw.text((x + 2, y + 2), f"t = {t:.2f} s", fill=(230, 230, 230))
    strip.save(out)
    print(f"wrote {out} ({n} frames over {total:.1f} s; entrance {info.get('total_ms')} ms, {len(info.get('resolved', []))} beats)")


if __name__ == "__main__":
    main()
