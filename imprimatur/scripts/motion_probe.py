#!/usr/bin/env python3
"""
Flicker probe — measures what a slide's motion does to the picture, frame by frame.

Opens each slide live (runtime playing), screenshots it every ~80 ms through the entrance and
2.5 s of rest, and reports: the mean frame-to-frame change AT REST (anything above 0 means the
picture keeps changing when it should be still — a camera zoom re-rasterising text measured
0.4 per frame; still is 0.000), A→B→A snap-backs (a frame that differs and immediately
reverts), and jumps around the entrance end (the restore moment; a word-split title
re-flowing measured 2.3). Use it before and after a runtime change: numbers, not eyes.

Usage:  motion_probe.py <deck-dir> <slide file> [<slide file> …]
"""
import io
import os
import sys
import time

from playwright.sync_api import sync_playwright
from PIL import Image, ImageChops

# Deterministic Chromium (1.6.0): identical pixels on identical frames, so a MAE number means the
# same thing on every run (flags from the hyperframes/howseen render harnesses).
DETERMINISTIC = ["--disable-blink-features=AutomationControlled", "--deterministic-mode",
                 "--run-all-compositor-stages-before-draw", "--disable-threaded-animation",
                 "--font-render-hinting=none", "--force-color-profile=srgb"]
D = sys.argv[1]; slides = sys.argv[2:]
def mae(a, b):
    d = ImageChops.difference(a, b); data = d.getdata(); return sum(sum(p) for p in data) / (3 * a.width * a.height)
with sync_playwright() as pw:
    b = pw.chromium.launch(args=DETERMINISTIC)
    for sl in slides:
        page = b.new_page(viewport={"width": 1920, "height": 1080})
        page.goto("file://" + os.path.join(D, sl), wait_until="networkidle")
        page.wait_for_function("window.__imprimaturMotion && window.__imprimaturMotion.info", timeout=15000)
        info = page.evaluate("window.__imprimaturMotion.info"); total = info.get("total_ms", 2000)
        # the focal element (the emphasis target): a flicker on one title is invisible to a whole-frame
        # mean, so its box is measured at full resolution on its own
        focal = page.evaluate("""() => { const m = window.__imprimaturMotion; const e = m.spec && m.spec.emphasis; if (!e || !e.sel) return null;
            const el = document.querySelector(m.toSelector(e.sel)); if (!el) return null; const r = el.getBoundingClientRect();
            return {x: Math.max(0, r.left - 4), y: Math.max(0, r.top - 4), w: Math.min(1920, r.width + 8), h: Math.min(1080, r.height + 8)}; }""")
        frames = []; focals = []; t0 = time.time()
        while (time.time() - t0) * 1000 < total + 2500:
            png = page.screenshot(clip={"x": 0, "y": 0, "width": 1920, "height": 1080})
            im = Image.open(io.BytesIO(png)).convert("RGB"); ts = (time.time() - t0) * 1000
            frames.append((ts, im.resize((480, 270))))
            if focal: focals.append((ts, im.crop((int(focal["x"]), int(focal["y"]), int(focal["x"] + focal["w"]), int(focal["y"] + focal["h"])))))
        diffs = [(round(frames[i][0]), mae(frames[i-1][1], frames[i][1])) for i in range(1, len(frames))]
        after = [d for t, d in diffs if t > total + 300]
        reverts = [(t, round(d, 2)) for i, (t, d) in enumerate(diffs[1:-1], 1) if d > 1.5 and mae(frames[i-1][1], frames[i+1][1]) < 0.3]
        end_jump = [(t, round(d, 2)) for t, d in diffs if total - 150 < t < total + 400 and d > 0.6]
        end_win = [d for t, d in diffs if total - 400 < t < total + 400]
        end_max = max(end_win) if end_win else 0.0
        print(f"== {sl} entrance {total} ms, {len(frames)} frames (~{round((total+2500)/len(frames))} ms apart)")
        print(f"   idle (after entrance+300ms): mean diff {sum(after)/max(1,len(after)):.3f}, max {max(after) if after else 0:.3f}  ← >0 means the picture keeps changing at rest")
        print(f"   A→B→A reverts (a frame that differs then snaps back): {reverts[:6]}")
        print(f"   jumps around the entrance end (restore): {end_jump[:6]}  · max frame diff in the last 400 ms + 400 ms after: {end_max:.3f}")
        if focals:
            fd = [(round(focals[i][0]), mae(focals[i-1][1], focals[i][1])) for i in range(1, len(focals))]
            f_rest = [d for t, d in fd if t > total + 300]
            # a flicker is a frame that differs from BOTH its neighbours while they agree (A→B→A) — motion
            # that lands is monotonic; the snap when a transform is removed is not
            f_snaps = [(t, round(d, 2)) for i, (t, d) in enumerate(fd[1:-1], 1)
                       if total - 900 < t < total + 500 and d > 1.0 and mae(focals[i - 1][1], focals[i + 1][1]) < 0.35 * d]
            f_tail = [d for t, d in fd if total - 60 < t < total + 400]   # after the last tween has eased out: should be ~0
            print(f"   FOCAL element ({int(focal['w'])}×{int(focal['h'])} px): snaps (A→B→A) around the end {f_snaps[:4]}; "
                  f"max diff after the entrance end {max(f_tail) if f_tail else 0:.3f}; at rest mean {sum(f_rest)/max(1,len(f_rest)):.3f}")
        page.close()
    b.close()
