#!/usr/bin/env python3
"""
Copy-then-edit slide authoring (WP2) — design-system agnostic.

Starts a new deck slide by copying a pack template BYTE-FOR-BYTE instead of the
designer retyping it as output tokens ("copying a template verbatim" that was,
in every observed transcript, actually regenerating 7-24K tokens of identical
boilerplate — half of every slide write, and the mechanism behind brand drift
whenever the retyping went slightly wrong).

What it does:
  1. Copies `<pack>/templates/<template>.html` byte-for-byte to
     `<deck-dir>/NN-<slug>.html`.
  2. Localises any `@font-face url(...)` references to `fonts/<file>` and
     copies the referenced font files into `<deck-dir>/fonts/` (per file, at
     creation — there is no whole-deck rescan any more).
  3. Sets the footer page number: the pack's `<span … id="page-number">N</span>`
     hook wherever it sits, else the bold span right after the confidentiality
     footer text (`<span class="font-bold">N</span>`), when the template carries
     one — some templates (covers, section dividers) deliberately have none.
     Until 2026-10-06 the detector wanted a bare `class="font-bold"` span holding
     DIGITS, so every template with the `id` hook or the literal `N` placeholder
     printed "no footer page-number span found" and shipped with `N`.
  4. Refuses to overwrite an existing file unless `--force` (which deletes it
     first, so the Edit that follows never hits Claude Code's "File has not
     been read yet" error on a stale read).
  5. Injects `<deck-dir>/deck-overrides.html` (if present) into `<head>` — the
     orchestrator writes it once at phase 4a for any deck-wide CSS/token
     override, so it is never retyped per slide (one real deck carried the
     same 459-character gradient override as a hand Edit on every slide).
     validate.py's head-identity check tolerates additions.
  6. Applies the deck's co-brand lockup when deck-state.json declares
     `"cobrand": {"logo": "assets/<client>.png", "position": "left"}` (cobrand.py):
     the client mark goes left of the template's logo, cover sizes on a
     `templateRoles.cover` template, content sizes elsewhere, white on a white logo.
     Until 1.6.1 designers pasted a 23 KB base64 wordmark per slide and truncated it.
  7. Prints the SLOT LIST (every text node / metric / label with its line
     number) and the body's line range — NOT the body itself. Claude Code's
     `Edit` tool requires a prior `Read` of the file, so the designer does one
     ranged `Read` (offset/limit printed here) anyway; printing the body too
     put the same 4 K tokens in context twice per slide (2026-09-07 audit).
     `--body` restores the old body print for humans.

Usage:
    new_slide.py --deck-dir D --template <stem> --n NN --slug <slug> [--page N] [--force]
    new_slide.py ... --body            # also print the body region with line numbers
    new_slide.py ... --no-overrides    # skip deck-overrides.html injection

`--n` may be given as `4` or `04` — it is always zero-padded to 2 digits in the
output filename. `--page` defaults to `--n` (the common case: page number ==
slide number); pass it explicitly when they diverge (e.g. a cover has no page
number, or slides were inserted/removed and the deck hasn't been renumbered).
"""
import argparse
import glob
import os
import re
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ds_config import load  # noqa: E402
import cobrand  # noqa: E402

FONT_URL_RE = re.compile(r"url\(\s*['\"]?([^'\")]+\.(?:ttf|woff2?|otf))['\"]?\s*\)")

# Preferred: the pack's explicit page-number hook, wherever it sits in the chrome.
# The placeholder is the literal `N` in every template, a number on a re-created slide.
PAGE_NUM_ID_RE = re.compile(r'(<span\b[^>]*\bid="page-number"[^>]*>)\s*(?:N|\d+)\s*(</span>)')
# Fallback for packs without the id: the confidentiality string immediately followed
# by a bold span (any attribute order, `N` or digits inside). Scoped to text NEAR the
# footer's required string so it can't misfire on an unrelated bold number elsewhere.
PAGE_NUM_RE_TMPL = (r'({footer}[^<]*</span>\s*<span\b[^>]*\bclass="[^"]*\bfont-bold\b[^"]*"[^>]*>)'
                    r'\s*(?:N|\d+)\s*(</span>)')

SLOT_TEXT_RE = re.compile(r">\s*([^<>{}][^<>]*?)\s*<")


def localise_fonts(dest_path, ds):
    """Rewrite @font-face url(...) refs to fonts/<basename> and copy the files
    into <deck-dir>/fonts/. Scoped to one file (the file just created); a slide
    whose fonts stopped resolving is re-created with --force, never rescanned.
    """
    deck_dir = os.path.dirname(dest_path)
    ds_files = {os.path.basename(p): p for p in glob.glob(os.path.join(ds.fonts_dir, "*"))}
    fonts_dir = os.path.join(deck_dir, "fonts")

    s = open(dest_path, encoding="utf-8").read()
    copied, changed, unknown = set(), False, set()

    def repl(m):
        nonlocal changed
        url = m.group(1)
        base = os.path.basename(url)
        if base not in ds_files:
            unknown.add(url)
            return m.group(0)
        copied.add(base)
        local = f"fonts/{base}"
        if url == local:
            return m.group(0)
        changed = True
        return f"url('{local}')"

    s2 = FONT_URL_RE.sub(repl, s)
    if changed:
        open(dest_path, "w", encoding="utf-8").write(s2)
    if copied:
        os.makedirs(fonts_dir, exist_ok=True)
        for base in sorted(copied):
            dst = os.path.join(fonts_dir, base)
            if not os.path.isfile(dst):
                shutil.copy2(ds_files[base], dst)
    return changed, copied, unknown


def find_page_number_pattern(html, footer):
    """The compiled pattern that matches this file's page-number span (two groups:
    opening tag, closing tag), or None when the file has none. The id hook wins;
    the footer-adjacent bold span is the fallback for packs without it."""
    if PAGE_NUM_ID_RE.search(html):
        return PAGE_NUM_ID_RE
    if footer:
        pat = re.compile(PAGE_NUM_RE_TMPL.format(footer=re.escape(footer)))
        if pat.search(html):
            return pat
    return None


def set_page_number(dest_path, ds, page):
    """Best-effort: set the footer's page-number span to `page`. Returns True if
    a page-number span was found and set, False if the template has none
    (covers/dividers legitimately have no page number — not an error)."""
    if page is None:
        return False
    s = open(dest_path, encoding="utf-8").read()
    pattern = find_page_number_pattern(s, ds.get("footer.requiredText"))
    if pattern is None:
        return False
    s2, n = pattern.subn(lambda m: f"{m.group(1)}{page}{m.group(2)}", s, count=1)
    if n:
        open(dest_path, "w", encoding="utf-8").write(s2)
        return True
    return False


OVERRIDES_FILE = "deck-overrides.html"


def inject_overrides(dest_path, deck_dir):
    """Append <deck-dir>/deck-overrides.html (a <style>/<script> fragment the
    orchestrator wrote once for the whole deck) just before </head>. Returns the
    number of bytes injected, 0 if there is no overrides file. Idempotent per
    file: new_slide.py only ever runs on a fresh copy."""
    src = os.path.join(deck_dir, OVERRIDES_FILE)
    if not os.path.isfile(src):
        return 0
    frag = open(src, encoding="utf-8").read().strip()
    if not frag:
        return 0
    s = open(dest_path, encoding="utf-8").read()
    marker = f"\n<!-- deck-overrides: injected by new_slide.py from {OVERRIDES_FILE} -->\n"
    if "</head>" not in s:
        return 0
    s = s.replace("</head>", marker + frag + "\n</head>", 1)
    open(dest_path, "w", encoding="utf-8").write(s)
    return len(frag)


def body_range(path):
    """(start_line, end_line), 1-based inclusive, of the <body>…</body> region."""
    lines = open(path, encoding="utf-8").read().splitlines()
    start = end = None
    for i, line in enumerate(lines):
        if start is None and re.search(r"<body\b", line):
            start = i
        if re.search(r"</body\s*>", line):
            end = i
    if start is None:
        start, end = 0, len(lines) - 1
    if end is None or end < start:
        end = len(lines) - 1
    return start + 1, end + 1


def body_region_with_lines(path):
    lines = open(path, encoding="utf-8").read().splitlines()
    start, end = body_range(path)
    return "\n".join(f"{i:>6}\t{lines[i - 1]}" for i in range(start, end + 1))


def list_slots(path):
    """Cheap, XPath-free scan: every line in the body region carrying inline
    text content (a metric, a label, a bullet, a title fragment), with its
    line number, so the designer can see what to Edit without reading markup."""
    lines = open(path, encoding="utf-8").read().splitlines()
    start = None
    for i, line in enumerate(lines):
        if re.search(r"<body\b", line):
            start = i
            break
    start = start or 0
    out = []
    for i in range(start, len(lines)):
        line = lines[i]
        if "<script" in line or "<style" in line:
            continue
        for m in SLOT_TEXT_RE.finditer(line):
            text = m.group(1).strip()
            if text and not text.startswith("<!--"):
                out.append(f"{i + 1:>6}\t{text[:100]}")
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser(description="Copy a pack template byte-for-byte into a new deck slide.")
    ap.add_argument("--deck-dir", required=True)
    ap.add_argument("--template", required=True, help="Template stem (no .html), e.g. 01-cover")
    ap.add_argument("--n", required=True, help="Slide number, e.g. 4 or 04")
    ap.add_argument("--slug", required=True, help="Slug for the filename, e.g. big-idea")
    ap.add_argument("--page", default=None, help="Footer page number (default: --n)")
    ap.add_argument("--force", action="store_true", help="Overwrite an existing slide file")
    ap.add_argument("--list-slots", action="store_true",
                    help="(default behaviour; kept for compatibility) print the slot list")
    ap.add_argument("--body", action="store_true",
                    help="Also print the <body> region with line numbers (humans; agents do one ranged Read instead)")
    ap.add_argument("--no-overrides", action="store_true",
                    help=f"Do not inject <deck-dir>/{OVERRIDES_FILE} into <head>")
    args = ap.parse_args()

    ds = load()
    template_path = os.path.join(ds.templates_dir, f"{args.template}.html")
    if not os.path.isfile(template_path):
        available = sorted(os.path.splitext(os.path.basename(p))[0]
                           for p in glob.glob(os.path.join(ds.templates_dir, "*.html")))
        sys.exit(f"error: no template '{args.template}' in {ds.templates_dir}\n"
                 f"available: {', '.join(available)}")

    deck_dir = os.path.abspath(args.deck_dir)
    os.makedirs(deck_dir, exist_ok=True)

    # The co-brand declaration is checked BEFORE the copy, so a bad one leaves no half-made slide.
    try:
        cb = cobrand.load_decl(deck_dir)
    except cobrand.CobrandError as e:
        sys.exit(f"error: {e}")
    if cb and not os.path.isfile(cb["abs"]):
        sys.exit(f"error: deck-state.json cobrand.logo {cb['logo']} not found in {deck_dir} — "
                 f"copy the client's logo there first")

    try:
        n_int = int(args.n)
    except ValueError:
        sys.exit(f"error: --n must be a number, got {args.n!r}")
    n_str = f"{n_int:02d}"
    dest_path = os.path.join(deck_dir, f"{n_str}-{args.slug}.html")

    if os.path.exists(dest_path):
        if not args.force:
            sys.exit(f"error: {dest_path} already exists — pass --force to overwrite "
                     f"(this deletes it first, so the following Edit never hits a "
                     f"stale-read error)")
        os.remove(dest_path)

    # Byte-for-byte copy — no read-then-retype in the model's context.
    shutil.copyfile(template_path, dest_path)

    changed, copied, unknown = localise_fonts(dest_path, ds)
    page = args.page if args.page is not None else str(n_int)
    got_page = set_page_number(dest_path, ds, page)
    injected = 0 if args.no_overrides else inject_overrides(dest_path, deck_dir)
    cb_status = cobrand.apply_file(dest_path, cb, ds, args.template) if cb else None

    print(f"created {dest_path}  (from {args.template}, {os.path.getsize(dest_path)} bytes)")
    if copied:
        print(f"fonts: {len(copied)} file(s) ensured in {os.path.join(deck_dir, 'fonts')}"
              + (" (URLs rewritten)" if changed else " (already local)"))
    if unknown:
        print(f"warn: {len(unknown)} font URL(s) not found in the pack's fonts dir: "
              + ", ".join(sorted(unknown)))
    if got_page:
        print(f"footer page number set to {page}")
    else:
        print("no footer page-number span found (expected for covers/dividers) — skipped")
    if injected:
        print(f"overrides: injected {injected} bytes from {OVERRIDES_FILE} into <head>")
    if cb_status:
        print(f"cobrand: {cobrand.describe(cb_status)} — do not edit the logo row")

    start, end = body_range(dest_path)
    print()
    print(f"# {os.path.basename(dest_path)} — text slots (template: {args.template})")
    print(list_slots(dest_path))
    print()
    print(f"# body is lines {start}–{end}. Next: ONE `Read` of this file with "
          f"offset={start} limit={end - start + 1} (Edit needs a prior Read; do not Read the "
          f"whole file, do not Read again after editing), then 2–4 Edits on the slot lines.")
    if args.body:
        print()
        print(f"# {os.path.basename(dest_path)} — <body>…</body> region")
        print(body_region_with_lines(dest_path))


if __name__ == "__main__":
    main()
