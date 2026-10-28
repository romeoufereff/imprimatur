#!/usr/bin/env python3
"""
deck-motion QA — proves a choreographed slide ends exactly where the static slide is.

Runs inside render_checks' shared page (no extra browser launch) for every slide that
carries the injected block (`id="imprimatur-motion"`); slides without it cost nothing.

  1. The page is already loaded static (Playwright → navigator.webdriver → the runtime did
     nothing). Screenshot #slide → A.
  2. `__imprimaturMotion.build({force:true}); toEnd()` → the timeline runs to its end and
     every animated element's inline style / text is restored. Screenshot → B.
  3. MAE(A, B) must be ≤ motion.qa.maxMae (pack; default 0.0 — pixel-identical).
     Plus: every selector resolves (groups: all members), no target inside a `never`
     region, total ≤ budget, inline spec ≤ maxInlineBytes, the runtime loaded (GSAP
     reachable), and `body_hash` equals the current body — a stale spec is a FAIL that
     names the fix (`choreograph.py --files …`).

Standalone:  check_motion.py FILE... [--json]
"""
import argparse
import io
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import choreograph  # noqa: E402

MARK = 'id="imprimatur-motion"'


def applies(path):
    try:
        with open(path, encoding="utf-8") as f:
            return MARK in f.read()
    except OSError:
        return False


def _mae(a_png, b_png):
    from PIL import Image, ImageChops, ImageStat
    a = Image.open(io.BytesIO(a_png)).convert("RGB")
    b = Image.open(io.BytesIO(b_png)).convert("RGB")
    if a.size != b.size:
        return 255.0
    diff = ImageChops.difference(a, b)
    stat = ImageStat.Stat(diff)
    return sum(stat.mean) / 3.0


END_STATE_JS = r"""
async () => {
  const m = window.__imprimaturMotion;
  if (!m) return {error: 'runtime not present (motion.js missing beside the slide?)'};
  // snapshot the static computed style of every target BEFORE the timeline exists
  const isPath0 = p => Array.isArray(p) && p.length && p.every(x => typeof x === 'number');
  const before = new Map();
  (m.spec.beats || []).forEach(b => {
    const sels = (Array.isArray(b.sel) && !isPath0(b.sel)) ? b.sel : [b.sel];
    sels.forEach(p => { const s = m.toSelector(p); let el = null; try { el = document.querySelector(s); } catch (e) {}
      if (el) { const cs = getComputedStyle(el); before.set(s, {opacity: cs.opacity, transform: cs.transform, filter: cs.filter, clip: cs.clipPath, text: el.textContent, html: el.innerHTML}); } });
  });
  const info = await m.build({force: true});
  if (!info) return {error: 'build returned nothing'};
  if (info.error) return {error: info.error};
  m.toEnd();
  await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));
  const spec = m.spec; const root = document.getElementById('slide');
  const problems = [];
  const never = new Set();
  (spec.neverSelectors || []).forEach(s => { try { root.querySelectorAll(s).forEach(el => { never.add(el); el.querySelectorAll('*').forEach(d => never.add(d)); }); } catch (e) {} });
  const seen = new Set();
  const isPath = p => Array.isArray(p) && p.length && p.every(x => typeof x === 'number');
  spec.beats.forEach(b => {
    const sels = (Array.isArray(b.sel) && !isPath(b.sel)) ? b.sel : [b.sel];
    sels.forEach(p => { const s = m.toSelector(p); let el = null; try { el = document.querySelector(s); } catch (e) {}
      if (!el) { problems.push(`${b.id} (${b.role}): selector resolves to nothing — ${s}`); return; }
      if (never.has(el)) problems.push(`${b.id} (${b.role}): targets a never-animate region — ${s}`);
      if (!root.contains(el)) problems.push(`${b.id} (${b.role}): target outside #slide — ${s}`);
      const cs = getComputedStyle(el); const was = before.get(s);
      if (was) {
        if (cs.opacity !== was.opacity) problems.push(`${b.id} (${b.role}): end-state opacity ${cs.opacity} ≠ static ${was.opacity} — ${s}`);
        if (cs.transform !== was.transform) problems.push(`${b.id} (${b.role}): end-state transform ${cs.transform} ≠ static ${was.transform} — ${s}`);
        if (el.textContent !== was.text) problems.push(`${b.id} (${b.role}): end-state text differs from static — ${s}`);
        if (el.innerHTML !== was.html) problems.push(`${b.id} (${b.role}): end-state markup differs from static (word split not restored?) — ${s}`);
        if (cs.filter !== was.filter) problems.push(`${b.id} (${b.role}): end-state filter ${cs.filter} ≠ static ${was.filter} — ${s}`);
        if (cs.clipPath !== was.clip) problems.push(`${b.id} (${b.role}): end-state clip-path ${cs.clipPath} ≠ static ${was.clip} — ${s}`);
      }
      seen.add(s); });
  });
  const veil = document.getElementById('imprimatur-motion-veil');
  if (veil) problems.push('veil still present after toEnd()');
  return {problems, total_ms: info.total_ms, steps: info.steps, beats: spec.beats.length,
          resolved: info.resolved, budget_ms: spec.budget_ms};
}
"""


def analyze_page(page, ds, path):
    """Returns (findings: list[str] | None on error, info: dict). Call AFTER every other check:
    it drives the page's timeline (and restores the DOM) — and it starts by RELOADING the
    slide, so the static reference is the pristine render, not whatever an earlier analyzer
    left behind (2026-10-04: check_gradient's probe left a 0.016 MAE residue on the
    process-flow diagram's filtered shapes, which read as a motion failure)."""
    name = os.path.basename(path)
    try:
        page.goto("file://" + os.path.abspath(path), wait_until="networkidle")
        page.evaluate("document.fonts.ready || Promise.resolve()")
        page.wait_for_timeout(400)
    except Exception as e:
        return [f"{name}: reload for the motion check failed: {e}"], {"file": name}
    html = open(path, encoding="utf-8").read()
    spec = choreograph.read_spec(html)
    m = ds.motion() if hasattr(ds, "motion") else {}
    qa = m.get("qa") or {}
    max_mae = float(qa.get("maxMae", 0.0))
    max_inline = int(qa.get("maxInlineBytes", 4096))
    findings, info = [], {"file": name}
    if not spec:
        return [f"{name}: motion block present but the spec is not valid JSON"], info

    # static facts first
    sm = re.search(r'<script id="' + choreograph.SPEC_ID + r'"[^>]*>(.*?)</script>', html, re.DOTALL)
    inline_bytes = len(sm.group(1).encode("utf-8")) if sm else 0
    info["inline_bytes"] = inline_bytes
    if inline_bytes > max_inline:
        findings.append(f"motion spec is {inline_bytes} B inline (pack cap {max_inline} B) — too many beats; let choreograph.py merge text blocks")
    current = choreograph.body_hash(choreograph.strip_block(html))
    info["spec_hash"] = spec.get("body_hash")
    if spec.get("body_hash") != current:
        findings.append(f"motion spec is STALE — the body changed after choreography; re-run choreograph.py --deck-dir D --files {name}")
    if spec.get("total_ms", 0) > spec.get("budget_ms", 10 ** 9):
        findings.append(f"entrance {spec['total_ms']} ms exceeds the budget {spec['budget_ms']} ms")
    # motion cost (1.6.0, after Motion's performance tier list): defocus is accelerated but its cost
    # grows with radius × layer area; clip-paths paint; a count-up writes text every frame. The
    # numbers are reported for the motion critic; only an extreme entrance is a finding.
    beats = spec.get("beats") or []
    blur_k = {"none": 0.0, "subtle": 0.4, "full": 1.0}.get(str(spec.get("blur", "subtle")), 0.4) * float(spec.get("intensity") or 1)
    radius = {"blur-in": 10, "slam": 16, "snap": 14, "focus-pull": 5}
    filt = [b for b in beats if b.get("effect") in radius]
    clips = [b for b in beats if str(b.get("effect", "")).startswith("wipe") or b.get("effect") in ("words-mask", "lines-mask")]
    count_ups = sum(b.get("n", 1) for b in beats if b.get("effect") == "count-up")
    info["cost"] = {"filter_beats": len(filt), "max_blur_px": round(min(10.0, max([radius[b["effect"]] for b in filt] + [0]) * blur_k), 1),
                    "clip_beats": len(clips), "count_ups": count_ups,
                    "peak_moving": spec.get("peak_moving"), "moving": spec.get("moving"), "language": spec.get("language")}
    if len(filt) > 6 or count_ups > 6:
        findings.append(f"motion cost: {len(filt)} defocus beats and {count_ups} counters in one entrance — too much churn; "
                        f"mark the busiest block data-motion=\"none\" or let choreograph.py merge it")

    slide = page.query_selector("#slide")
    if slide is None:
        return [f"{name}: no #slide element"], info
    try:
        a = slide.screenshot()
    except Exception as e:
        return [f"{name}: static screenshot failed: {e}"], info

    try:
        res = page.evaluate(END_STATE_JS)
    except Exception as e:
        return [f"{name}: running the motion timeline failed: {e}"], info
    if res.get("error"):
        # The runtime is responsible for leaving the slide readable; a missing GSAP (offline)
        # is reported but is not a slide defect.
        if "gsap" in str(res["error"]).lower():
            info["note"] = res["error"]
            return findings, info
        return findings + [f"{name}: {res['error']}"], info

    try:
        b = slide.screenshot()
        mae = _mae(a, b)
    except Exception as e:
        return findings + [f"{name}: end-state screenshot failed: {e}"], info
    info.update({"mae": round(mae, 4), "total_ms": res.get("total_ms"), "steps": res.get("steps"),
                 "beats": res.get("beats"), "budget_ms": res.get("budget_ms")})
    if mae > max_mae:
        findings.append(f"end state differs from the static slide: MAE {mae:.3f} > {max_mae} — motion must never change the final picture")
    for p in res.get("problems") or []:
        findings.append(p)
    unresolved = [r for r in res.get("resolved") or [] if not r.get("n")]
    if unresolved:
        findings.append("beats with no resolved target: " + ", ".join(f"{r['id']}/{r['role']}" for r in unresolved))
    return findings, info


def main():
    ap = argparse.ArgumentParser(description=__doc__.strip().split("\n")[0])
    ap.add_argument("files", nargs="+")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--design-system", default=None)
    args = ap.parse_args()
    from ds_config import load
    from playwright.sync_api import sync_playwright
    ds = load(args.design_system, deck_dir=os.path.dirname(os.path.abspath(args.files[0])))
    out, total = {}, 0
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": ds.canvas[0], "height": ds.canvas[1]})
        for f in args.files:
            if not applies(f):
                out[os.path.basename(f)] = {"skipped": "no motion block"}
                continue
            page.goto("file://" + os.path.abspath(f), wait_until="networkidle")
            page.evaluate("document.fonts.ready || Promise.resolve()")
            page.wait_for_timeout(400)
            findings, info = analyze_page(page, ds, f)
            info["findings"] = findings or []
            out[os.path.basename(f)] = info
            total += len(findings or [])
        browser.close()
    if args.json:
        print(json.dumps({"files": out, "total_failures": total}, indent=2, ensure_ascii=False))
    else:
        for name, info in out.items():
            if info.get("skipped"):
                print(f"{name}: skipped ({info['skipped']})"); continue
            status = "PASS" if not info["findings"] else "FAIL"
            print(f"{name}: {status}  mae={info.get('mae')} total={info.get('total_ms')} ms beats={info.get('beats')} steps={info.get('steps')}")
            for x in info["findings"]:
                print(f"  FAIL  {x}")
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main())
