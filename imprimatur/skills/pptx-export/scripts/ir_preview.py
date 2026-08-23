#!/usr/bin/env python3
"""
pptx-export — IR preview + fidelity verify loop.

Renders an IR JSON back into a minimal HTML approximation of what build_pptx.py will
produce (absolute-positioned boxes / text / pictures using EXACTLY the properties the
builder writes — nothing the builder drops may appear here), screenshots it at 1920x1080,
and pixel-diffs it against a render of the original slide. Output: per-slide MAE +
diff heatmap PNG.

This is the "measure, don't eyeball" engine for the exporter: every extraction/builder
change is judged by the MAE, not by opening PowerPoint. Acceptance bar: MAE < 8.

Honest caveat: the preview uses the browser's text engine, not PowerPoint's — it catches
property loss and geometry drift, not PPT-specific line wrapping. A final human open in
PowerPoint stays in the checklist.

Usage:
    python3 ir_preview.py <deck>/.pptx-ir/02-slide.json --original <deck>/02-slide.html \
        [--out-dir /tmp/irdiff]
    python3 ir_preview.py --deck-dir <deck>   # all slides: IR in <deck>/.pptx-ir, report table
"""

import argparse
import glob as globmod
import json
import os
import sys

from playwright.sync_api import sync_playwright

MAE_PASS = 8.0            # legacy whole-canvas bar (kept for reference)
CONTENT_MAE_PASS = 60.0   # gating bar: MAE over ink-carrying pixels only — calibrate
                          # against a known-good run; whole-canvas MAE is too diluted
                          # (a full serif-fallback preview once passed it)

# Weights the builder can actually produce — the same per-weight family names the
# exporter writes, read from the active design system so the preview matches the PPTX.
# Depth-independent: anchor on the plugin marker rather than counting `..` hops,
# so moving this file between skill folders cannot silently resolve to the wrong
# directory. See scripts/_paths.py.
_here = os.path.dirname(os.path.abspath(__file__))
_probe = _here
while not os.path.isdir(os.path.join(_probe, ".claude-plugin")):
    _parent = os.path.dirname(_probe)
    if _parent == _probe:
        raise RuntimeError(f"No .claude-plugin/ found above {_here}")
    _probe = _parent
sys.path.insert(0, os.path.join(_probe, "scripts"))
from ds_config import load as _load_ds  # noqa: E402

_DS = _load_ds()


def _brand_gradient_css():
    """The pack's brand gradient as a CSS string, for the preview render."""
    stops = _DS.get('svg.brandGradientStops') or []
    if stops:
        parts = ', '.join(f"{hexv} {pos}" for pos, hexv, *_ in stops)
        return f"linear-gradient(60deg, {parts})"
    canonical = _DS.get('gradients.canonical') or []
    if canonical:
        return canonical[0]
    return _DS.color('primary') or '#000000'


_BRAND_GRADIENT_CSS = _brand_gradient_css()
_FONT_BY_WEIGHT = sorted(
    ((int(k), v) for k, v in (_DS.get("pptx.fontFamilyByWeight", {}) or {}).items()),
    reverse=True)
_PREVIEW_FONT = _DS.get("typography.familyLabel", "sans-serif")


def _font_for_weight(w):
    for threshold, name in _FONT_BY_WEIGHT:
        if w >= threshold:
            return name
    return _FONT_BY_WEIGHT[-1][1] if _FONT_BY_WEIGHT else "sans-serif"


def ir_to_html(ir):
    """Build the preview page. Mirrors build_pptx.py's output model 1:1."""
    parts = []
    meta = ir['slide']
    if meta.get('bgAsset'):
        parts.append(f'<img src="file://{meta["bgAsset"]}" style="position:absolute;left:0;top:0;'
                     f'width:1920px;height:1080px">')
    bg = meta.get('bg', '#FFFFFF')
    grad = meta.get('bgGradientCss')
    bg_css = f'background:{grad}' if grad else f'background:{bg}'

    for n in ir['nodes']:
        r = n['rect']
        pos = f'position:absolute;left:{r["x"]}px;top:{r["y"]}px;width:{r["w"]}px;height:{r["h"]}px;'
        if n['kind'] == 'box':
            css = pos + 'box-sizing:border-box;'
            if n.get('fill'):
                a = n.get('fillAlpha', 1)
                if a < 1:  # builder pre-composites over white
                    c = n['fill'].lstrip('#')
                    rgb = tuple(int(c[i:i+2], 16) for i in (0, 2, 4))
                    comp = tuple(int(round(v * a + 255 * (1 - a))) for v in rgb)
                    css += f'background:rgb{comp};'
                else:
                    css += f'background:{n["fill"]};'
            if n.get('border'):
                css += f'border:{n["border"]["width"]}px solid {n["border"]["color"]};'
            if n.get('radius'):
                css += f'border-radius:{min(n["radius"], min(r["w"], r["h"])/2)}px;'
            parts.append(f'<div style="{css}"></div>')
        elif n['kind'] == 'raster':
            if n.get('asset'):
                parts.append(f'<img src="file://{n["asset"]}" style="{pos}">')
        elif n['kind'] == 'text':
            align = n.get('align', 'left')
            anchor = n.get('anchor', 'top')
            wrap = (pos + f'text-align:{align};display:flex;flex-direction:column;'
                    + ('justify-content:center;' if anchor == 'middle' else '')
                    + 'overflow:visible;white-space:nowrap;')
            # group runs into paragraphs (mirrors the builder), each with its own
            # line-height from its runs
            paragraphs, current = [], []
            for run in n['runs']:
                if run['text'] == '\n':
                    paragraphs.append(current)
                    current = []
                else:
                    current.append(run)
            paragraphs.append(current)
            para_html = []
            for para_runs in paragraphs:
                spans = []
                lhs = [r['st'].get('lineHeight') for r in para_runs if r.get('st') and r['st'].get('lineHeight')]
                lh = max(lhs) if lhs else n.get('lineHeight')
                for run in para_runs:
                    st = run['st']
                    # browsers resolve family+weight (PowerPoint resolves the per-weight
                    # full names the builder writes — same physical fonts either way)
                    # single quotes: the style attribute itself is double-quoted —
                    # nested double quotes truncate it and EVERYTHING after silently
                    # falls back (this bug hid behind the diluted whole-canvas MAE)
                    s = (f"font-family:'{_PREVIEW_FONT}';font-weight:{st['weight']};"
                         f"font-size:{st['size']}px;color:{st['color']};")
                    if st.get('accent'):
                        # The builder writes a real per-run brand-gradient fill, so the
                        # preview has to use the SAME gradient or the MAE reports drift that
                        # is really just this file disagreeing with the pack. Read it from
                        # svg.brandGradientStops rather than restating it.
                        s += (f'background:{_BRAND_GRADIENT_CSS};'
                              '-webkit-background-clip:text;background-clip:text;color:transparent;')
                    if st.get('italic'):
                        s += 'font-style:italic;'
                    if st.get('spacing'):
                        s += f'letter-spacing:{st["spacing"]}px;'
                    spans.append(f'<span style="{s}">{_esc(run["text"])}</span>')
                lh_css = f'line-height:{lh}px;' if lh else 'line-height:normal;'
                para_html.append(f'<div style="{lh_css}">{"".join(spans)}</div>')
            parts.append(f'<div style="{wrap}">{"".join(para_html)}</div>')
    return ('<!DOCTYPE html><html><head><meta charset="utf-8"></head>'
            f'<body style="margin:0"><div id="slide" style="position:relative;width:1920px;'
            f'height:1080px;{bg_css};overflow:hidden">' + '\n'.join(parts) + '</div></body></html>')


def _esc(s):
    return s.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def diff_images(a_path, b_path, heatmap_path):
    """Returns (whole-canvas MAE, content MAE). The content MAE averages only over
    pixels that carry ink in either image — the whole-canvas mean on mostly-white
    slides is so diluted it once passed a preview whose fonts had ALL fallen back
    to serif. Content MAE is the gating number."""
    from PIL import Image, ImageFilter
    import numpy as np
    ai = Image.open(a_path).convert('RGB')
    bi = Image.open(b_path).convert('RGB')
    if ai.size != bi.size:
        bi = bi.resize(ai.size)
    # light blur before diffing: 1px stroke offsets on thin text are rendering noise,
    # not infidelity — without this, a visually identical slide scores ~100 on text
    # pixels while wrong-font/wrong-size defects score the same. Blur separates them.
    ai = ai.filter(ImageFilter.GaussianBlur(2))
    bi = bi.filter(ImageFilter.GaussianBlur(2))
    a = np.asarray(ai, dtype=np.int16)
    b = np.asarray(bi, dtype=np.int16)
    d = np.abs(a - b).mean(axis=2)
    mae = float(d.mean())
    mask = (a.min(axis=2) < 245) | (b.min(axis=2) < 245)
    mae_content = float(d[mask].mean()) if mask.any() else 0.0
    hm = np.zeros((*d.shape, 3), dtype=np.uint8)
    hm[..., 0] = np.clip(d * 3, 0, 255)
    Image.fromarray(hm).save(heatmap_path)
    return mae, mae_content


def preview_one(page, ir_path, original, out_dir):
    name = os.path.splitext(os.path.basename(ir_path))[0]
    os.makedirs(out_dir, exist_ok=True)
    ir = json.load(open(ir_path, encoding='utf-8'))

    html_path = os.path.join(out_dir, f'{name}-preview.html')
    open(html_path, 'w', encoding='utf-8').write(ir_to_html(ir))
    prev_png = os.path.join(out_dir, f'{name}-preview.png')
    page.goto('file://' + os.path.abspath(html_path))
    page.wait_for_timeout(250)
    page.locator('#slide').screenshot(path=prev_png)

    orig_png = os.path.join(out_dir, f'{name}-original.png')
    page.goto('file://' + os.path.abspath(original), wait_until='networkidle')
    page.evaluate("document.fonts.ready || Promise.resolve()")
    page.wait_for_timeout(600)
    page.locator('#slide').screenshot(path=orig_png)

    mae, mae_content = diff_images(orig_png, prev_png, os.path.join(out_dir, f'{name}-heatmap.png'))
    return name, mae, mae_content


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('ir', nargs='?', help='single IR JSON')
    ap.add_argument('--original', help='original slide HTML (single mode)')
    ap.add_argument('--deck-dir', help='deck mode: previews every IR in <deck>/.pptx-ir')
    ap.add_argument('--out-dir', default=None)
    args = ap.parse_args()

    jobs = []
    if args.deck_dir:
        deck = os.path.abspath(args.deck_dir)
        for irp in sorted(globmod.glob(os.path.join(deck, '.pptx-ir', '[0-9]*.json'))):
            src = json.load(open(irp)).get('source')
            if src and os.path.isfile(src):
                jobs.append((irp, src))
        out_dir = args.out_dir or os.path.join(deck, '.pptx-ir', 'preview')
    else:
        if not (args.ir and args.original):
            sys.exit('need IR + --original, or --deck-dir')
        jobs = [(args.ir, args.original)]
        out_dir = args.out_dir or os.path.join(os.path.dirname(os.path.abspath(args.ir)), 'preview')

    worst = 0.0
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={'width': 1920, 'height': 1080})
        for irp, orig in jobs:
            name, mae, mae_c = preview_one(page, irp, orig, out_dir)
            worst = max(worst, mae_c)
            flag = 'PASS' if mae_c < CONTENT_MAE_PASS else 'FAIL'
            print(f'{flag}  {name}: content-MAE {mae_c:.1f} (canvas {mae:.2f})')
        browser.close()
    print(f'\nworst content-MAE {worst:.1f} (bar: < {CONTENT_MAE_PASS}); previews + heatmaps in {out_dir}')
    sys.exit(0 if worst < CONTENT_MAE_PASS else 1)


if __name__ == '__main__':
    main()
