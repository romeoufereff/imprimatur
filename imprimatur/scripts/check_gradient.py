#!/usr/bin/env python3
"""
Sampled contrast for text over gradients and images — design-system agnostic.

check_contrast.py computes WCAG ratios from computed styles and, correctly,
defers when the background is a gradient or an image: the ratio depends on
where the text sits. That deferral became brand-audit's most expensive
judgment row — auditors rendered slides and eyeballed luminance (2026-09-07
audit). The position-dependence is exactly what a pixel sample resolves:

  1. collect every element with direct text whose background stack contains a
     gradient/image (the same walk check_contrast.py does), with its rect and
     text colour;
  2. make the element's own text transparent, screenshot its rect, restore;
  3. luminance of every sampled pixel → the darkest and lightest background
     the text sits on → the WORST ratio against the text colour.

A worst-case ratio below the WCAG threshold (4.5:1, or 3:1 for large text) is
flagged with a number, not a "verify manually" note. It is a *sampled* measure
(the middle band of the element, text hidden), so render_checks reports it in
the JSON as `gradient_contrast` for brand-audit to judge — it never gates a
designer chunk or the orchestrator's run on its own. Elements marked
`data-decor-text="ok"` are skipped (decorative glyphs), as in check_contrast.

Exposes analyze_page(page) → list of dicts:
    {"tag","text","ratio_worst","ratio_best","need","fail","fontSize","fontWeight"}
for render_checks.py (same page load). Requires Pillow for the pixel pass; if
it is missing every entry is returned with "unsampled": True so brand-audit can
fall back to judgment for that row, explicitly.

Standalone:
    python3 scripts/check_gradient.py FILE...
"""
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

COLLECT_JS = """
() => {
  const slide = document.getElementById('slide');
  if (!slide) return { error: 'no #slide element' };
  const sb = slide.getBoundingClientRect();
  const parse = (c) => {
    const m = (c || '').match(/rgba?\\(([\\d.]+),\\s*([\\d.]+),\\s*([\\d.]+)(?:,\\s*([\\d.]+))?\\)/);
    return m ? [+m[1], +m[2], +m[3], m[4] === undefined ? 1 : +m[4]] : null;
  };
  const out = [];
  let idx = 0;
  for (const el of slide.querySelectorAll('*')) {
    if (el.closest('svg')) continue;
    const direct = Array.from(el.childNodes).some(n => n.nodeType === 3 && n.textContent.trim().length > 0);
    if (!direct) continue;
    const cs = getComputedStyle(el);
    if (cs.display === 'none' || cs.visibility === 'hidden') continue;
    const r = el.getBoundingClientRect();
    if (r.width < 2 || r.height < 2) continue;
    const col = parse(cs.color);
    if (!col || col[3] === 0) continue;
    if ((cs.webkitBackgroundClip || cs.backgroundClip) === 'text') continue;
    if (el.closest('[data-decor-text="ok"]')) continue;
    let bgImage = false, node = el;
    while (node && node.nodeType === 1) {
      const ncs = node === el ? cs : getComputedStyle(node);
      if (ncs.backgroundImage && ncs.backgroundImage !== 'none') { bgImage = true; break; }
      const pb = getComputedStyle(node, '::before').backgroundImage;
      const pa = getComputedStyle(node, '::after').backgroundImage;
      if ((pb && pb !== 'none') || (pa && pa !== 'none')) { bgImage = true; break; }
      const b = parse(ncs.backgroundColor);
      if (b && b[3] >= 1) break;
      if (node === slide) break;
      node = node.parentElement;
    }
    if (!bgImage) continue;
    el.setAttribute('data-gradient-probe', String(idx));
    out.push({
      idx, tag: el.tagName.toLowerCase(),
      text: (el.textContent || '').trim().slice(0, 50),
      color: col,
      x: r.left, y: r.top, w: r.width, h: r.height,
      fontSize: parseFloat(cs.fontSize), fontWeight: parseInt(cs.fontWeight, 10) || 400,
    });
    idx++;
  }
  return { items: out, vw: window.innerWidth, vh: window.innerHeight };
}
"""

HIDE_JS = """
([idx, on]) => {
  const root = document.querySelector('[data-gradient-probe="' + idx + '"]');
  if (!root) return;
  // Hide the text of the element AND its descendants (child spans, icons, badges keep
  // their own colour otherwise and pollute the background sample).
  const els = [root, ...root.querySelectorAll('*')];
  for (const el of els) {
    if (on) {
      el.__c = el.style.color; el.__wc = el.style.webkitTextFillColor; el.__ts = el.style.textShadow;
      el.__v = el.style.visibility;
      if (el !== root && (el.tagName === 'SVG' || el.tagName === 'svg' || el.tagName === 'IMG')) el.style.visibility = 'hidden';
      el.style.color = 'transparent'; el.style.webkitTextFillColor = 'transparent'; el.style.textShadow = 'none';
    } else {
      el.style.color = el.__c || ''; el.style.webkitTextFillColor = el.__wc || ''; el.style.textShadow = el.__ts || '';
      el.style.visibility = el.__v || '';
    }
  }
}
"""

# Sample only the middle band of the element: rounded corners, borders and the page
# behind a pill's curve sit at the edges, and the glyphs sit in the middle.
INSET_X, INSET_Y = 0.15, 0.30


def _lum(rgb):
    def chan(c):
        c /= 255.0
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (chan(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _ratio(l1, l2):
    hi, lo = max(l1, l2), min(l1, l2)
    return (hi + 0.05) / (lo + 0.05)


def analyze_page(page):
    res = page.evaluate(COLLECT_JS)
    if "error" in res:
        return []
    items = res["items"]
    if not items:
        return []
    try:
        from PIL import Image
    except ImportError:
        return [{"tag": it["tag"], "text": it["text"], "need": None, "fail": False,
                 "unsampled": True, "reason": "Pillow not installed"} for it in items]

    out = []
    vw, vh = res["vw"], res["vh"]
    for it in items:
        ix, iy = it["w"] * INSET_X, it["h"] * INSET_Y
        x = max(0, int(it["x"] + ix))
        y = max(0, int(it["y"] + iy))
        w = max(1, min(int(it["w"] - 2 * ix), vw - x))
        h = max(1, min(int(it["h"] - 2 * iy), vh - y))
        if w < 2 or h < 2:
            continue
        page.evaluate(HIDE_JS, [it["idx"], True])
        try:
            png = page.screenshot(clip={"x": x, "y": y, "width": w, "height": h})
        finally:
            page.evaluate(HIDE_JS, [it["idx"], False])
        img = Image.open(io.BytesIO(png)).convert("RGB")
        step = max(1, int((w * h / 4000) ** 0.5))  # ≤ ~4000 samples per element
        lums = []
        px = img.load()
        for yy in range(0, img.height, step):
            for xx in range(0, img.width, step):
                lums.append(_lum(px[xx, yy]))
        if not lums:
            continue
        text_l = _lum(tuple(it["color"][:3]))
        r_dark, r_light = _ratio(text_l, min(lums)), _ratio(text_l, max(lums))
        worst, best = min(r_dark, r_light), max(r_dark, r_light)
        large = it["fontSize"] >= 24 or (it["fontSize"] >= 18.66 and it["fontWeight"] >= 700)
        need = 3.0 if large else 4.5
        out.append({"tag": it["tag"], "text": it["text"], "ratio_worst": round(worst, 2),
                    "ratio_best": round(best, 2), "need": need, "fail": worst < need - 0.005,
                    "fontSize": it["fontSize"], "fontWeight": it["fontWeight"]})
    return out


def main():
    from playwright.sync_api import sync_playwright
    from ds_config import load
    ds = load()
    files = sys.argv[1:]
    if not files:
        sys.exit("usage: check_gradient.py FILE...")
    cw, ch = ds.canvas
    total = 0
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": cw, "height": ch})
        for f in files:
            page.goto("file://" + os.path.abspath(f), wait_until="networkidle")
            page.wait_for_timeout(300)
            rows = analyze_page(page)
            name = os.path.basename(f)
            fails = [r for r in rows if r.get("fail")]
            total += len(fails)
            print(f"{name}: {len(rows)} text element(s) over gradient/image, {len(fails)} FAIL")
            for r in rows:
                flag = "FAIL" if r.get("fail") else ("skip" if r.get("unsampled") else "ok  ")
                print(f"  {flag}  <{r['tag']}> worst {r.get('ratio_worst')}:1 (need {r.get('need')}) — {r['text']!r}")
        browser.close()
    sys.exit(1 if total else 0)


if __name__ == "__main__":
    main()
