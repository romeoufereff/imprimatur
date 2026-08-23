"""Render SVG to raster and compute a perceptual diff for the verify loop.

Rendering engine: Playwright + headless Chromium, NOT cairosvg.

Why: cairosvg is not installed in this environment and pulls in a system
Cairo dependency; Playwright already is installed and is what
design-system/scripts/check_overflow.py uses to validate every slide
in the deck pipeline. More importantly, the final artifact is a browser-
rendered HTML slide (Tailwind + inline SVG, exported to PDF via a headless
Chromium screenshot per pdf-export/SKILL.md) — so verifying against
Chromium's rendering is verifying against the actual target renderer, not
a second, textPath-incompatible one. cairosvg support is kept as an
optional fallback only (pip install cairosvg) for environments without
Playwright.
"""
import json
import os

import numpy as np
from PIL import Image, ImageChops


def render(svg_path, png_path, width, height):
    """Render an SVG file to PNG at (width, height) using headless Chromium."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as e:
        return _render_cairosvg(svg_path, png_path, width, height, fallback_error=e)

    svg_markup = open(svg_path).read()
    html = (
        "<!DOCTYPE html><html><head><meta charset='utf-8'>"
        "<style>*{margin:0;padding:0}html,body{background:#fff}</style>"
        f"</head><body>{svg_markup}</body></html>"
    )
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": width, "height": height})
        page.set_content(html, wait_until="networkidle")
        page.screenshot(path=png_path)
        browser.close()
    return png_path


def _render_cairosvg(svg_path, png_path, width, height, fallback_error):
    try:
        import cairosvg
    except ImportError:
        raise RuntimeError(
            "Neither Playwright nor cairosvg is available. Install one: "
            "`pip install playwright && playwright install chromium` "
            "(preferred — matches the deck pipeline's own renderer) or "
            "`pip install cairosvg`."
        ) from fallback_error
    cairosvg.svg2png(url=svg_path, write_to=png_path,
                      output_width=width, output_height=height)
    return png_path


def diff(original_png, candidate_png, heatmap_path="diff_heatmap.png",
         threshold=30):
    """Perceptual diff between the reference screenshot and the candidate
    render. Returns mae (0 = identical), per-quadrant error, and the worst
    quadrant so the agent knows WHERE to focus the next config edit instead
    of guessing across the whole image."""
    a = Image.open(original_png).convert("RGB")
    b = Image.open(candidate_png).convert("RGB").resize(a.size)
    delta = np.asarray(ImageChops.difference(a, b))
    mae = float(delta.mean())

    mask = (delta.sum(2) > threshold).astype("uint8") * 255
    Image.fromarray(mask).save(heatmap_path)

    h, w = delta.shape[:2]
    q = {
        "TL": float(delta[: h // 2, : w // 2].mean()),
        "TR": float(delta[: h // 2, w // 2:].mean()),
        "BL": float(delta[h // 2:, : w // 2].mean()),
        "BR": float(delta[h // 2:, w // 2:].mean()),
    }
    worst = max(q, key=q.get)
    return {
        "mae": round(mae, 2),
        "quadrants": {k: round(v, 2) for k, v in q.items()},
        "worst_quadrant": worst,
        "heatmap_path": heatmap_path,
    }


def verify_loop(build_fn, config_path, original_png, out_dir,
                 width, height, max_rounds=6, mae_threshold=8.0,
                 min_gain=0.5):
    """Drive the CLASSIFY->MEASURE->BUILD->VERIFY->REPORT loop's VERIFY step.

    build_fn(config_path, out_svg_path) -> svg_path  (a recipe's build())

    Stops when mae < mae_threshold, or after max_rounds, or when two
    consecutive rounds fail to improve mae by at least min_gain (the
    "no gain in 2 rounds" stop condition from CLAUDE.md). Returns the
    full round-by-round history so the agent (or a human) can see the
    convergence path, not just the final number.
    """
    os.makedirs(out_dir, exist_ok=True)
    history = []
    prev_mae = None
    stall_count = 0

    for round_i in range(1, max_rounds + 1):
        svg_path = os.path.join(out_dir, f"round{round_i}.svg")
        png_path = os.path.join(out_dir, f"round{round_i}.png")
        heatmap_path = os.path.join(out_dir, f"round{round_i}_heatmap.png")

        build_fn(config_path, svg_path)
        render(svg_path, png_path, width, height)
        report = diff(original_png, png_path, heatmap_path)
        report["round"] = round_i
        report["svg_path"] = svg_path
        history.append(report)

        if report["mae"] < mae_threshold:
            report["stop_reason"] = f"mae {report['mae']} < threshold {mae_threshold}"
            break
        if prev_mae is not None and (prev_mae - report["mae"]) < min_gain:
            stall_count += 1
            if stall_count >= 2:
                report["stop_reason"] = "no gain in 2 rounds"
                break
        else:
            stall_count = 0
        prev_mae = report["mae"]
    else:
        history[-1]["stop_reason"] = f"max_rounds ({max_rounds}) reached"

    summary_path = os.path.join(out_dir, "verify_history.json")
    with open(summary_path, "w") as f:
        json.dump(history, f, indent=2)

    return history
