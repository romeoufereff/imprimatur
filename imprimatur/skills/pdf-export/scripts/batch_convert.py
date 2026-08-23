#!/usr/bin/env python3
"""
Batch-convert a directory of HTML slide files to a merged PDF.

Usage:
    python batch_convert.py --deck-dir /path/to/slides/ --output deck.pdf
    python batch_convert.py --deck-dir /path/to/slides/ --output deck.pdf --slide-selector .slide
    python batch_convert.py --deck-dir /path/to/slides/ --output deck.pdf --scale 1 --debug

The script:
  1. Finds all .html files in --deck-dir (sorted alphabetically).
  2. Renders each to a temporary per-slide PDF via pdf_renderer.py.
  3. Merges all per-slide PDFs into --output using PyPDF2.
  4. Cleans up the temporary per-slide PDFs.
"""

import argparse
import sys
import tempfile
from pathlib import Path

# Allow importing sibling scripts
sys.path.insert(0, str(Path(__file__).parent))

from pdf_renderer import render_pdf


def main():
    parser = argparse.ArgumentParser(description="Batch HTML→PDF converter")
    parser.add_argument("--deck-dir", required=True, help="Directory containing HTML slide files")
    parser.add_argument("--output", required=True, help="Output merged PDF path")
    parser.add_argument("--slide-selector", default="#slide", help="CSS selector for the slide element (default: #slide)")
    parser.add_argument("--scale", type=int, default=2, help="device_scale_factor: 2=retina (default), 1=standard")
    parser.add_argument("--viewport-width", type=int, default=1920)
    parser.add_argument("--viewport-height", type=int, default=1080)
    parser.add_argument("--glob", default="*.html", help="Glob pattern for slide files (default: *.html)")
    parser.add_argument("--keep-individual", action="store_true", help="Keep per-slide PDFs after merging")
    parser.add_argument("--debug", action="store_true", help="Save debug PNG alongside each PDF")
    args = parser.parse_args()

    deck_dir = Path(args.deck_dir)
    if not deck_dir.is_dir():
        print(f"❌ --deck-dir not found: {deck_dir}")
        sys.exit(1)

    # Never treat the deck viewer or the review harness as slides — with the default
    # '*.html' glob they would otherwise become extra PDF pages.
    NON_SLIDES = {"index.html", "slide-review.html"}
    slides = [p for p in sorted(deck_dir.glob(args.glob)) if p.name not in NON_SLIDES]
    if not slides:
        print(f"❌ No slide files matching '{args.glob}' in {deck_dir}")
        sys.exit(1)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    viewport = {"width": args.viewport_width, "height": args.viewport_height}

    print(f"📄 Converting {len(slides)} slides to PDF...\n")

    # Use a temp dir for individual slide PDFs unless user wants to keep them
    if args.keep_individual:
        slide_pdf_dir = output_path.parent / (output_path.stem + "_slides")
        slide_pdf_dir.mkdir(exist_ok=True)
        cleanup = False
    else:
        _tmpdir = tempfile.TemporaryDirectory()
        slide_pdf_dir = Path(_tmpdir.name)
        cleanup = True

    slide_pdfs = []
    for i, html_path in enumerate(slides, 1):
        out_pdf = slide_pdf_dir / f"{i:02d}-{html_path.stem}.pdf"
        print(f"[{i:2d}/{len(slides)}] {html_path.name}...", end=" ", flush=True)
        try:
            render_pdf(
                html_path=str(html_path),
                output_path=str(out_pdf),
                slide_selector=args.slide_selector,
                scale=args.scale,
                viewport=viewport,
                debug=args.debug,
            )
            size_kb = out_pdf.stat().st_size / 1024
            print(f"✓ ({size_kb:.1f}KB)")
            slide_pdfs.append(out_pdf)
        except Exception as e:
            print(f"✗\n  Error: {e}")
            if cleanup:
                _tmpdir.cleanup()
            sys.exit(1)

    print(f"\n✨ All slides rendered.\n")
    print(f"🔗 Merging {len(slide_pdfs)} PDFs...")

    try:
        from PyPDF2 import PdfMerger
        merger = PdfMerger()
        for pdf in slide_pdfs:
            merger.append(str(pdf))
        merger.write(str(output_path))
        merger.close()
        size_mb = output_path.stat().st_size / 1024 / 1024
        print(f"✅ Merged → {output_path} ({size_mb:.1f}MB)")
    except ImportError:
        # Fallback: try pypdf (newer name for PyPDF2)
        try:
            from pypdf import PdfMerger
            merger = PdfMerger()
            for pdf in slide_pdfs:
                merger.append(str(pdf))
            merger.write(str(output_path))
            merger.close()
            size_mb = output_path.stat().st_size / 1024 / 1024
            print(f"✅ Merged → {output_path} ({size_mb:.1f}MB)")
        except ImportError:
            print("⚠️  PyPDF2/pypdf not installed. Per-slide PDFs are at:")
            for pdf in slide_pdfs:
                print(f"   {pdf}")
            print("\nInstall with: pip install PyPDF2")
            if cleanup:
                cleanup = False  # don't delete them

    if cleanup:
        _tmpdir.cleanup()

    if args.keep_individual:
        print(f"📁 Per-slide PDFs kept at: {slide_pdf_dir}")


if __name__ == "__main__":
    main()
