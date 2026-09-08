#!/usr/bin/env python3
"""
Logo geometry check (render-level) — design-system agnostic.

Brand-audit's "logo placement and size" row was a judgment row only because
nobody had scripted it: on two real decks the auditor rendered slides, cropped
PNGs and eyeballed the logo's height and corner — 12–27 image reads and 70–90
turns per deck (2026-09-07 audit). The geometry is measurable in one page
evaluate, so it lives here and runs inside render_checks.py's single page load.

What "right" means comes from the TEMPLATE THE SLIDE WAS COPIED FROM
(`data-template`), not from a hand-typed spec: the template is the pack's own
statement of where the logo sits, how tall it is and what it is filled with on
that background. A light cover variant legitimately carries a dark logo where
the gradient cover carries a white one, and a per-template reference gets both
right without anyone maintaining a table. Template metrics are measured once
per process (second page in the same browser) and cached.

The pack declares only how to FIND the logo, in design-system.json:

    "logo": {
      "selector": "svg[viewBox=\\"0 0 590.1 207.7\\"], svg.logo, #logo, [data-logo]",
      "tolerancePx": 3
    }

No `logo` block → the check is skipped (None), never guessed. `data-logo="ok"`
on the element exempts it (a co-branded lockup, a deliberately larger mark) —
say why in the slide's log line.

Exposes analyze_page(page, ds, name) → (findings: list[str] | None, info: dict)
for render_checks.py; findings is None when skipped.

Standalone:
    python3 scripts/check_logo.py FILE...
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ds_config import load  # noqa: E402

DEFAULT_SELECTOR = "svg.logo, #logo, [data-logo]"
_TEMPLATE_CACHE = {}

MEASURE_JS = """
(selector) => {
  const slide = document.getElementById('slide');
  if (!slide) return { error: 'no #slide element' };
  const sb = slide.getBoundingClientRect();
  const el = slide.querySelector(selector);
  const template = slide.getAttribute('data-template') || '';
  if (!el) return { found: false, template };
  const r = el.getBoundingClientRect();
  let fill = el.getAttribute('fill') || '';
  if (!fill) {
    const g = el.querySelector('[fill]');
    if (g) fill = g.getAttribute('fill') || '';
  }
  if (!fill) fill = getComputedStyle(el).fill || '';
  const cs = getComputedStyle(el);
  return {
    found: true, template,
    exempt: (el.getAttribute('data-logo') || '').toLowerCase() === 'ok',
    x: r.left - sb.left, y: r.top - sb.top, w: r.width, h: r.height,
    sw: sb.width, sh: sb.height,
    fill: fill.trim(),
    visible: cs.display !== 'none' && cs.visibility !== 'hidden',
  };
}
"""


def _norm_hex(c):
    c = (c or "").strip().lower()
    if c.startswith("rgb"):
        try:
            nums = [int(float(x)) for x in c[c.find("(") + 1:c.find(")")].split(",")[:3]]
            return "#%02x%02x%02x" % tuple(nums)
        except Exception:
            return c
    if len(c) == 4 and c.startswith("#"):
        return "#" + "".join(ch * 2 for ch in c[1:])
    return c


def _corner(m):
    cx, cy = m["x"] + m["w"] / 2, m["y"] + m["h"] / 2
    v = "top" if cy < m["sh"] / 2 else "bottom"
    h = "left" if cx < m["sw"] / 2 else "right"
    return f"{v}-{h}"


def _template_metrics(page, ds, stem, selector):
    """Measure the logo in the pack template `stem`, once per process."""
    key = (ds.root, stem)
    if key in _TEMPLATE_CACHE:
        return _TEMPLATE_CACHE[key]
    path = os.path.join(ds.templates_dir, f"{stem}.html")
    ref = None
    if os.path.isfile(path):
        # A page opened with browser.new_page() lives in a default context that refuses
        # further pages, so open the template through the browser itself (own context).
        browser = page.context.browser
        if browser is None:
            return None
        tpage = None
        try:
            tpage = browser.new_page(viewport={"width": ds.canvas[0], "height": ds.canvas[1]})
            tpage.goto("file://" + os.path.abspath(path), wait_until="networkidle")
            tpage.wait_for_timeout(250)
            ref = tpage.evaluate(MEASURE_JS, selector)
        except Exception as e:
            ref = {"error": str(e)}
        finally:
            if tpage is not None:
                tpage.close()
    _TEMPLATE_CACHE[key] = ref
    return ref


def analyze_page(page, ds, name):
    spec = ds.get("logo")
    if not spec:
        return None, {"skipped": "pack declares no logo block"}
    selector = spec.get("selector") or DEFAULT_SELECTOR
    tol = float(spec.get("tolerancePx", 3))

    m = page.evaluate(MEASURE_JS, selector)
    if "error" in m:
        return None, {"error": m["error"]}
    stem = m.get("template") or ""
    if not stem:
        return None, {"skipped": "slide has no data-template"}
    ref = _template_metrics(page, ds, stem, selector)
    if not ref or "error" in ref or not ref.get("found"):
        return None, {"skipped": f"template {stem} has no logo matching the selector"}

    info = {"template": stem, "found": m.get("found"),
            "expected": {"h": round(ref["h"], 1), "corner": _corner(ref), "fill": ref["fill"]},
            "measured": None}
    findings = []
    if not m.get("found"):
        findings.append(f"logo: no element matches {selector!r}; template {stem} has one "
                        f"({info['expected']['h']}px, {info['expected']['corner']})")
        return findings, info
    info["measured"] = {"h": round(m["h"], 1), "corner": _corner(m), "fill": m["fill"]}
    if m.get("exempt"):
        info["exempt"] = True
        return [], info
    if not m.get("visible"):
        findings.append("logo: element present but not visible")
        return findings, info
    if abs(m["h"] - ref["h"]) > tol:
        findings.append(f"logo: height {m['h']:.0f}px, template {stem} has {ref['h']:.0f}px (±{tol:g})")
    if _corner(m) != _corner(ref):
        findings.append(f"logo: sits {_corner(m)}, template {stem} places it {_corner(ref)}")
    if _norm_hex(m["fill"]) != _norm_hex(ref["fill"]):
        findings.append(f"logo: fill {m['fill'] or '(none)'}, template {stem} uses {ref['fill']} "
                        f"(mark data-logo=\"ok\" if the background changed deliberately)")
    return findings, info


def main():
    from playwright.sync_api import sync_playwright
    ds = load()
    files = sys.argv[1:]
    if not files:
        sys.exit("usage: check_logo.py FILE...")
    cw, ch = ds.canvas
    total = 0
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": cw, "height": ch})
        for f in files:
            page.goto("file://" + os.path.abspath(f), wait_until="networkidle")
            page.wait_for_timeout(300)
            findings, info = analyze_page(page, ds, os.path.basename(f))
            if findings is None:
                print(f"{os.path.basename(f)}: skipped ({info})")
                continue
            for x in findings:
                print(f"{os.path.basename(f)}\n  FAIL  {x}")
            total += len(findings)
            if not findings:
                print(f"{os.path.basename(f)}: logo OK {info.get('measured')} (template {info['template']})")
        browser.close()
    sys.exit(1 if total else 0)


if __name__ == "__main__":
    main()
