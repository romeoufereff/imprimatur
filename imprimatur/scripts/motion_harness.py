#!/usr/bin/env python3
"""
Motion harness — every element, every frame, measured against the resting slide.

What a filmstrip cannot do: it shows eight moments and a human guesses. This drives each slide's
timeline deterministically (seek, never play), screenshots EVERY step (default 50 ms) through the
entrance, fires the completion (the restore), and compares the box of every animated element —
each beat's targets, each group member, the emphasis — against the slide at rest (`?static=1`).
From the per-element distance series it reports, per slide, the findings a viewer notices:

  MOVES AFTER LANDING   the element reached its resting pixels, then changed again (the jump up,
                        the shake, the zoom-out at the end: an emphasis re-applying a from-state,
                        two tweens on one element, a scale settle)
  LANDS AT THE END      first reaches rest only in the last 10 % of the entrance or at the restore
                        (hidden by a stray from-state until then: icons that "appear at the end")
  NEVER LANDS           still differs from rest after the restore (a restore miss — qa.py's MAE row
                        would also fail)
  SNAP AT RESTORE       the completion changes the element (a transform removed from a layer)
  BEFORE ITS CONNECTOR  a node visible before the `draw` beat that leads to it has finished
  VISIBLE FROM FRAME 0  an element some beat targets that is already at rest at t = 0 (never
                        animated: the highlighted card nobody grouped)

Each finding names the element (role, effect, text snippet), the time, and the frames; a contact
sheet of the offending frames is written next to the report so the eye confirms what the number
says. Exit 1 when any finding is raised — the §7b gate after choreography.

Usage:
    motion_harness.py <deck-dir> [NN-slug.html …] [--step 0.05] [--out DIR] [--json]
"""
import argparse
import io
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

FLAGS = ["--disable-blink-features=AutomationControlled", "--deterministic-mode",
         "--run-all-compositor-stages-before-draw", "--disable-threaded-animation",
         "--font-render-hinting=none", "--force-color-profile=srgb"]
LAND = 0.6      # MAE below which an element is "at rest"
MOVE = 2.0      # MAE above which, after landing, it has visibly changed (a real jump measured 11–38; a token crossing a landed spoke 1.8)
MIN_PX = 12     # ignore boxes thinner than this (hairlines measure nothing)

TARGETS_JS = r"""
() => {
  const m = window.__imprimaturMotion; if (!m || !m.spec) return {error: 'no runtime'};
  const isPath = p => Array.isArray(p) && p.length && p.every(x => typeof x === 'number');
  const out = []; const seen = new Set(); const outEls = [];
  const add = (beat, sel, k) => { let el = null; try { el = document.querySelector(m.toSelector(sel)); } catch (e) {}
    if (!el || seen.has(el)) return; seen.add(el); outEls.push(el);
    const r = el.getBoundingClientRect();
    out.push({id: beat.id + (k === null ? '' : '#' + (k + 1)), role: beat.role, effect: beat.effect, at: beat.at, dur: beat.dur, stagger: beat.stagger || 0, n: beat.n || 1,
              text: (el.textContent || '').replace(/\s+/g, ' ').trim().slice(0, 40), tag: el.tagName.toLowerCase(),
              x: r.left, y: r.top, w: r.width, h: r.height, draws: beat.effect === 'draw',
              arrow: beat.effect === 'draw' && !!(el.closest('[marker-end]') || el.getAttribute('marker-end'))}); };
  (m.spec.beats || []).forEach(b => {
    const sels = (Array.isArray(b.sel) && !isPath(b.sel)) ? b.sel : [b.sel];
    sels.forEach((s, k) => add(b, s, sels.length > 1 ? k : null));
    (b.onVisit || []).forEach((v, k) => { if (!v) return; const vs = (Array.isArray(v) && !isPath(v)) ? v : [v]; vs.forEach((s, j) => add({id: b.id + '.visit' + (k + 1), role: 'visit', effect: b.visitEffect || 'fade', at: b.at, dur: b.dur}, s, vs.length > 1 ? j : null)); });
  });
  // everything with ink that is not chrome: a leaf no beat covers sits on stage from frame one
  const never = new Set();
  (m.spec.never || []).forEach(s => { try { document.querySelectorAll(s).forEach(e => { never.add(e); e.querySelectorAll('*').forEach(d => never.add(d)); }); } catch (e) {} });
  const leaves = [];
  document.querySelectorAll('#slide *').forEach(e => {
    if (never.has(e)) return;
    const t = e.tagName.toLowerCase();
    const shape = e.ownerSVGElement && /^(rect|circle|ellipse|path|line|polyline|polygon|text|image)$/.test(t);
    const ink = shape || t === 'img' || (!e.ownerSVGElement && Array.from(e.childNodes).some(n => n.nodeType === 3 && n.textContent.trim().length > 1))
      || (!e.ownerSVGElement && !e.children.length && /^(div|span)$/.test(t) && (getComputedStyle(e).backgroundColor !== 'rgba(0, 0, 0, 0)' || getComputedStyle(e).borderTopWidth !== '0px'));
    if (!ink) return;
    const r = e.getBoundingClientRect();
    if (r.width < 6 || r.height < 6 || r.bottom > 980 || r.width * r.height > 0.5 * 1920 * 1080 || r.right <= 0 || r.left >= 1920) return;
    if (e.closest('defs, marker, clipPath, mask')) return;
    if (outEls.some(te => te === e || te.contains(e))) return;   // inside an animated element: it rides with it
    leaves.push({tag: t, x: r.left, y: r.top, w: r.width, h: r.height, text: (e.textContent || '').replace(/\s+/g, ' ').trim().slice(0, 30)});
  });
  const inside = (o, l) => l.x >= o.x - 8 && l.y >= o.y - 8 && l.x + l.w <= o.x + o.w + 8 && l.y + l.h <= o.y + o.h + 8;   // a title may overhang its card by a few px
  const orphans = leaves.filter(l => !out.some(o => inside(o, l)));
  return {targets: out, duration: m.tl ? m.tl.duration() : null, file: m.spec.file, orphans};
}
"""


def mae(a, b):
    from PIL import ImageChops, ImageStat
    if a.size != b.size:
        return 255.0
    st = ImageStat.Stat(ImageChops.difference(a, b))
    return sum(st.mean) / 3.0


def crop(im, t, inner=()):
    x0, y0 = max(0, int(t["x"]) - 1), max(0, int(t["y"]) - 1)
    x1, y1 = min(im.width, int(t["x"] + t["w"]) + 1), min(im.height, int(t["y"] + t["h"]) + 1)   # 1 px: a neighbour rising into a wider margin read as motion
    c = im.crop((x0, y0, x1, y1))
    if inner:
        from PIL import ImageDraw
        dr = ImageDraw.Draw(c)
        for o in inner:
            dr.rectangle((int(o["x"]) - x0 - 1, int(o["y"]) - y0 - 1, int(o["x"] + o["w"]) - x0 + 1, int(o["y"] + o["h"]) - y0 + 1), fill=(0, 0, 0))
    return c


def contained(outer, inner):
    return (inner is not outer and inner["x"] >= outer["x"] - 1 and inner["y"] >= outer["y"] - 1
            and inner["x"] + inner["w"] <= outer["x"] + outer["w"] + 1 and inner["y"] + inner["h"] <= outer["y"] + outer["h"] + 1
            and inner["w"] * inner["h"] < 0.8 * outer["w"] * outer["h"])


def analyze(page, path, step, trace=False):
    from PIL import Image
    url = "file://" + os.path.abspath(path)
    page.goto(url + "?static=1", wait_until="networkidle")
    page.wait_for_timeout(350)
    rest = Image.open(io.BytesIO(page.screenshot())).convert("RGB")
    tg = page.evaluate(TARGETS_JS)          # boxes measured on the RESTING slide (at t = 0 an enter-from sits off-canvas)
    if tg.get("error"):
        return {"file": os.path.basename(path), "error": tg["error"], "findings": []}
    page.goto(url + "?t=0", wait_until="networkidle")
    page.wait_for_function("window.__imprimaturMotion && window.__imprimaturMotion.info", timeout=15000)
    info = page.evaluate("window.__imprimaturMotion.info")
    if info.get("error"):
        return {"file": os.path.basename(path), "error": info["error"], "findings": []}
    targets = [t for t in tg["targets"] if t["w"] >= MIN_PX and t["h"] >= MIN_PX and t["x"] < 1920 and t["y"] < 1080 and t["x"] + t["w"] > 0 and t["y"] + t["h"] > 0]
    duration = float(page.evaluate("window.__imprimaturMotion.tl.duration()"))
    times, frames = [], []
    t = 0.0
    while t <= duration + 1e-6:
        page.evaluate("t => { const m = window.__imprimaturMotion; m.tl.pause(); if (m.idle) m.idle.pause(0); m.tl.time(Math.min(t, m.tl.duration()), true); }", t)
        page.wait_for_timeout(25)
        frames.append(Image.open(io.BytesIO(page.screenshot())).convert("RGB")); times.append(round(t, 3))
        t += step
    # completion: the restore (keepSplits) fires through onComplete; then the full restore (leaving the slide)
    page.evaluate("() => { const m = window.__imprimaturMotion; m.tl.progress(1); }")
    page.wait_for_timeout(60)
    frames.append(Image.open(io.BytesIO(page.screenshot())).convert("RGB")); times.append("complete")
    page.evaluate("() => window.__imprimaturMotion.toEnd()")
    page.wait_for_timeout(60)
    frames.append(Image.open(io.BytesIO(page.screenshot())).convert("RGB")); times.append("left")

    findings, rows = [], []
    for o in (tg.get("orphans") or [])[:8]:
        findings.append({"kind": "NEVER ANIMATED", "el": f"<{o['tag']}> at {int(o['x'])},{int(o['y'])} {int(o['w'])}×{int(o['h'])}" + (f" “{o['text']}”" if o["text"] else ""), "t": 0.0,
                         "detail": "visible from frame 0 — no beat covers it (a marker, a line, an unclassified block)"})
    draws = [tt for tt in targets if tt["draws"] and tt.get("arrow")]   # only an arrowed connector "leads to" a node; an axis line does not
    for tt in targets:
        inner = [o for o in targets if contained(tt, o)]
        ref = crop(rest, tt, inner)
        d = [mae(crop(f, tt, inner), ref) for f in frames]
        n_ent = len(d) - 2                       # entrance frames; d[-2] = complete, d[-1] = left
        landed = next((i for i in range(n_ent) if d[i] < LAND), None)
        label = f"{tt['id']} {tt['role']}:{tt['effect']} <{tt['tag']}> “{tt['text']}”" if tt["text"] else f"{tt['id']} {tt['role']}:{tt['effect']} <{tt['tag']}>"
        row = {"id": tt["id"], "role": tt["role"], "effect": tt["effect"], "text": tt["text"], "planned_at": tt["at"],
               "landed_at": times[landed] if landed is not None else None, "d_complete": round(d[-2], 3), "d_left": round(d[-1], 3)}
        rows.append(row)
        if trace:
            every = max(1, int(round(0.1 / step)))
            print(f"   trace {label[:70]:70s} at={tt['at']} " + " ".join(f"{d[i]:.1f}" for i in range(0, n_ent, every)) + f" | complete {d[-2]:.1f} left {d[-1]:.1f}")
        if landed == 0 and tt["role"] not in ("emphasis",) and d[0] < LAND:
            findings.append({"kind": "VISIBLE FROM FRAME 0", "el": label, "t": 0.0})
            continue
        if landed is None:
            if d[-2] < LAND:
                findings.append({"kind": "LANDS AT THE END", "el": label, "t": "complete", "detail": f"only at the restore (min during entrance {min(d[:n_ent]):.2f})"})
            else:
                findings.append({"kind": "NEVER LANDS", "el": label, "t": "left", "detail": f"after restore {d[-2]:.2f}, after leaving {d[-1]:.2f}"})
            continue
        planned_end = float(tt["at"] or 0) + float(tt["dur"] or 0) + float(tt.get("stagger") or 0) * max(0, int(tt.get("n") or 1) - 1)
        if landed >= int(0.9 * n_ent) and tt["role"] != "emphasis" and times[landed] > planned_end + 0.35:
            findings.append({"kind": "LANDS AT THE END", "el": label, "t": times[landed], "detail": f"planned to land by {planned_end:.2f} s; entrance ends at {duration:.2f} s"})
        thr = MOVE * 2 if tt["draws"] else MOVE     # a drawn stroke's box overlaps its sibling rays; a real jump of a line reads far above 4
        later = [(times[i], round(d[i], 2)) for i in range(landed + 1, n_ent) if d[i] > thr and (d[i - 1] > thr or (i + 1 < n_ent and d[i + 1] > thr))]
        if later:
            # the largest excursion and its span
            peak = max(later, key=lambda x: x[1])
            findings.append({"kind": "MOVES AFTER LANDING", "el": label, "t": later[0][0], "detail": f"landed {times[landed]} s, then {len(later)} frame(s) differ, peak {peak[1]} at {peak[0]} s", "frames": [later[0][0], peak[0], later[-1][0]]})
        if d[-2] > MOVE and d[n_ent - 1] < LAND:
            findings.append({"kind": "SNAP AT RESTORE", "el": label, "t": "complete", "detail": f"last frame {d[n_ent - 1]:.2f} → after restore {d[-2]:.2f}"})
        # a node that appears before the draw leading to it: the draw whose end sits inside this box
        for dr in draws:
            ex, ey = dr["x"] + dr["w"], dr["y"] + dr["h"] / 2
            inside = tt["x"] - 8 <= ex <= tt["x"] + tt["w"] + 8 and tt["y"] - 8 <= ey <= tt["y"] + tt["h"] + 8
            if inside and dr["id"] != tt["id"] and not tt["draws"] and tt["tag"] in ("rect", "circle", "g", "text", "div") and times[landed] < dr["at"] + dr["dur"] - 0.05 and tt["role"] in ("scene", "svg-card", "card"):
                findings.append({"kind": "BEFORE ITS CONNECTOR", "el": label, "t": times[landed], "detail": f"{dr['id']} draws until {dr['at'] + dr['dur']:.2f} s"})
    return {"file": os.path.basename(path), "duration": round(duration, 3), "step": step, "targets": len(targets),
            "findings": findings, "rows": rows, "_frames": frames, "_times": times, "_targets": targets}


def sheet(result, out_dir):
    """Contact sheet of the frames around each finding (crop of the element, 3 frames), labelled."""
    from PIL import Image, ImageDraw
    fr, times, targets = result["_frames"], result["_times"], {t["id"]: t for t in result["_targets"]}
    tiles = []
    for f in result["findings"]:
        tid = f["el"].split(" ")[0]
        tt = targets.get(tid)
        if not tt:
            continue
        picks = f.get("frames") or [f["t"]]
        idx = [times.index(p) for p in picks if p in times]
        if not idx:
            continue
        idx = sorted(set([max(0, idx[0] - 1)] + idx))[:4]
        crops = [crop(fr[i], tt) for i in idx]
        w = sum(c.width for c in crops) + 8 * (len(crops) + 1); h = max(c.height for c in crops) + 36
        tile = Image.new("RGB", (max(w, 600), h), (28, 28, 28)); dr = ImageDraw.Draw(tile)
        dr.text((6, 4), f"{f['kind']} — {f['el'][:90]} — frames {[times[i] for i in idx]}", fill=(240, 240, 240))
        x = 8
        for c in crops:
            tile.paste(c, (x, 30)); x += c.width + 8
        tiles.append(tile)
    if not tiles:
        return None
    W = max(t.width for t in tiles); H = sum(t.height + 6 for t in tiles)
    page = Image.new("RGB", (W, H), (20, 20, 20)); y = 0
    for t in tiles:
        page.paste(t, (0, y)); y += t.height + 6
    p = os.path.join(out_dir, result["file"].replace(".html", ".harness.png"))
    page.save(p)
    return p


def main():
    ap = argparse.ArgumentParser(description=__doc__.strip().split("\n")[0])
    ap.add_argument("deck_dir")
    ap.add_argument("slides", nargs="*")
    ap.add_argument("--step", type=float, default=0.05)
    ap.add_argument("--out", default=None, help="Directory for contact sheets (default: <deck>/motion/harness)")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--trace", action="store_true", help="Print every element's distance-to-rest series (one value per 100 ms)")
    args = ap.parse_args()
    deck = os.path.abspath(args.deck_dir)
    files = [os.path.join(deck, s) for s in args.slides] if args.slides else sorted(
        os.path.join(deck, f) for f in os.listdir(deck) if f.endswith(".html") and f[:2].isdigit() and 'id="imprimatur-motion"' in open(os.path.join(deck, f), encoding="utf-8").read())
    out_dir = args.out or os.path.join(deck, "motion", "harness")
    os.makedirs(out_dir, exist_ok=True)
    from playwright.sync_api import sync_playwright
    results, total = [], 0
    with sync_playwright() as pw:
        b = pw.chromium.launch(args=FLAGS)
        page = b.new_page(viewport={"width": 1920, "height": 1080})
        for f in files:
            r = analyze(page, f, args.step, trace=args.trace)
            png = sheet(r, out_dir) if r.get("findings") else None
            r["sheet"] = png
            total += len(r.get("findings") or [])
            results.append(r)
            if not args.json:
                print(f"== {r['file']}  {r.get('duration', 0)} s · {r.get('targets', 0)} elements · {len(r.get('findings') or [])} finding(s)" + (f"  [{r['error']}]" if r.get("error") else ""))
                for fd in r.get("findings") or []:
                    print(f"   {fd['kind']:22s} t={fd['t']:<9} {fd['el']}" + (f"  — {fd['detail']}" if fd.get("detail") else ""))
                if png:
                    print(f"   sheet → {png}")
        b.close()
    if args.json:
        print(json.dumps([{k: v for k, v in r.items() if not k.startswith("_")} for r in results], indent=1, ensure_ascii=False))
    else:
        print(f"{total} finding(s) on {len(results)} slide(s)")
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main())
