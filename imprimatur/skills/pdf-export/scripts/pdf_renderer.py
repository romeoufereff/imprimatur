"""HTML → PDF via Playwright element screenshot (bypasses print-media relayout)."""

import io
import time
from pathlib import Path

from PIL import Image
from playwright.sync_api import sync_playwright

from server import start_http_server


def render_pdf(
    html_path: str,
    output_path: str,
    slide_selector: str = "#slide",
    scale: int = 2,
    viewport: dict = None,
    debug: bool = False,
) -> None:
    """
    Render a single HTML file to PDF using a Playwright element screenshot.

    Why element screenshot instead of page.pdf():
    - page.pdf() always switches Chromium to print media internally, even after
      emulate_media("screen"). This re-layout breaks gradient text clipping,
      text wrapping in long headings, and custom font metrics.
    - Element screenshot captures the element in screen mode — exactly what the
      browser shows — then Pillow converts the PNG to a PDF page at the correct DPI.

    Args:
        html_path: Path to the HTML slide file.
        output_path: Destination PDF path.
        slide_selector: CSS selector for the slide container (default: "#slide").
        scale: device_scale_factor. 2 = retina (3840x2160 → 192 DPI → 20in×11.25in).
        viewport: Browser viewport dict. Defaults to {"width": 1920, "height": 1080}.
        debug: If True, also saves a PNG alongside the PDF for inspection.
    """
    viewport = viewport or {"width": 1920, "height": 1080}
    html_file = Path(html_path).absolute()

    # Serve from filesystem root so absolute-path @font-face src URLs resolve.
    # Without this, Playwright 404s on fonts → falls back to system font with
    # different metrics → text overflows slide boundary → clipping artifacts.
    httpd, port, base_url = start_http_server("/", port=0)
    url = f"{base_url}{html_file}"

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            context = browser.new_context(
                viewport=viewport,
                device_scale_factor=scale,
            )
            page = context.new_page()

            # Emulate screen media BEFORE loading — Tailwind generates utility classes
            # based on the active media type at render time.
            page.emulate_media(media="screen")

            page.on(
                "console",
                lambda msg: print(f"  [browser {msg.type}] {msg.text}")
                if "error" in msg.type.lower()
                else None,
            )
            page.on("pageerror", lambda err: print(f"  [page error] {err}"))

            try:
                page.goto(url, wait_until="networkidle", timeout=60000)

                # Wait for fonts to finish loading.
                page.evaluate("document.fonts.ready || Promise.resolve()")

                # Wait for Tailwind CDN to inject its generated <style> block.
                try:
                    page.wait_for_function(
                        """
                        () => {
                          const styles = [...document.querySelectorAll('style')];
                          const links  = [...document.querySelectorAll('link')];
                          const hasTw  = styles.some(s =>
                            s.textContent.includes('--tw-') ||
                            s.textContent.includes('tailwind')
                          );
                          const hasCss = styles.length > 0 || links.length > 0;
                          return hasTw || hasCss;
                        }
                        """,
                        timeout=10000,
                    )
                except Exception:
                    print("  ⚠️  Tailwind/CSS detection timeout — continuing anyway")

                # Force a layout flush, then let fonts/animations settle.
                page.evaluate("document.body.offsetHeight")
                time.sleep(0.5)

                slide_el = page.query_selector(slide_selector)
                if slide_el is None:
                    print(f"  ⚠️  Selector '{slide_selector}' not found — falling back to viewport screenshot")
                    png_bytes = page.screenshot(full_page=False)
                else:
                    png_bytes = slide_el.screenshot()

            finally:
                browser.close()

    finally:
        httpd.shutdown()

    # PNG → PDF via Pillow.
    # scale=2 → image is 2× viewport pixels → DPI = 96 × 2 = 192
    # At 192 DPI a 3840×2160 image = 20in × 11.25in (correct 16:9 slide size).
    dpi = 96 * scale
    img = Image.open(io.BytesIO(png_bytes))

    if debug:
        debug_png = str(output_path).replace(".pdf", "_debug.png")
        img.save(debug_png)
        print(f"  🔍 Debug PNG saved: {debug_png}")

    img.convert("RGB").save(output_path, format="PDF", resolution=dpi)
