#!/usr/bin/env python3
"""
PreToolUse hook (matcher: Bash).

Blocks Bash commands that write slide HTML. Slide files may only be created or
changed through the `Write`/`Edit` tools, or by one of the engine's own scripts.

Why this exists: on a real deck the designing session collapsed "hand a brief to
the designer, wait for one slide, repeat" into a single script that
string-templated all N slides in one pass. That produced inconsistent accent
colours across slides and a bespoke SVG that silently rendered invisible — both
defects a genuine per-slide pass would very likely have caught, because they only
become obvious when someone is looking at one slide at a time with actual design
judgment. A prose instruction not to do it failed the one time it mattered, so it
is mechanical now.

Two things follow from routing every slide write through `Write`/`Edit`:
the per-slide `slide_write_check.py` hook actually fires, and the deck-designer
agent cannot batch even once it "knows" all the content.

Reads the tool call as JSON on stdin. Exit 0 = allow (silent). Exit 2 = block,
stderr is surfaced to Claude as the reason.
"""
import json
import os
import re
import sys

# The engine's own tools legitimately rewrite slide files — fix_font_paths localises
# @font-face URLs, apply_edits materialises staged review edits. Blocking those would
# break the pipeline this hook exists to protect.
ENGINE_SCRIPTS = (
    "fix_font_paths.py", "apply_edits.py", "annotations.py", "build_review.py",
    "render.py", "qa.py", "validate.py", "check_contrast.py", "check_overflow.py",
    "check_paint.py", "pack_inventory.py", "build_gallery.py", "ds_config.py",
    "batch_convert.py", "pdf_renderer.py", "server.py", "html2pptx.py",
    "extract_ir.py", "build_pptx.py", "ir_preview.py", "svg2shapes.py",
    "probe_brand.py", "emit_pack.py", "verify_pack.py", "validate_all.sh",
    # WP1-WP8 additions (token & speed optimization plan, 2026-09).
    "render_checks.py", "log_slide.py", "slide_body.py", "pack_brief.py",
    "plan_check.py", "assemble_deck.py", "session_stats.py",
    # new_slide.py IS a sanctioned engine script for a single slide — but unlike
    # the others above, looping it is itself the batching violation (N slides
    # created without a per-slide look in between), so it gets its own dedicated
    # loop check below RATHER than blanket immunity from the ENGINE_SCRIPTS bypass.
    # It stays listed here for `--help`/discoverability parity with the rest of
    # the allowlist and because a single non-looped call must be allowed too.
    "new_slide.py",
)

# new_slide.py writes its slide file internally (Python file I/O), so a loop that
# calls it leaves no literal ">...html" / "open(...,'w')" text in the Bash command
# for WRITE_PATTERNS/WRITES_HTML to catch below — the exact gap the batching rule
# exists to close. Caught separately, and checked BEFORE the ENGINE_SCRIPTS bypass
# so being a "sanctioned" script doesn't exempt a loop that calls it N times.
NEW_SLIDE_RE = re.compile(r"\bnew_slide\.py\b")

# WP8: the orchestrator archives stale/orphan NN-*.html files it finds on disk
# that deck-state.json doesn't know about, moving them to
# `<deck>/_archive/<date>/...` rather than deleting them. The archived copy
# keeps its slide-shaped filename, which would otherwise trip the cp/mv
# WRITE_PATTERNS rule below (a slide-pattern filename appears in the command).
# Sanctioned specifically when the DESTINATION is under an `_archive/` folder —
# this is housekeeping on already-written slides, not new content being batched
# in without a design-judgment pass.
ARCHIVE_MV_RE = re.compile(r"\b(?:mv|cp|rsync)\b[^|;&]*_archive/")

SLIDE = r"\d{2}-[\w.-]*\.html"

# Shapes that write a slide file. Each is a real way the batching failure showed up.
# Interpolated filenames defeat the literal patterns below, so catch the *shape*:
# something that iterates, combined with something that writes HTML.
ITERATES = re.compile(r"\bfor\b[^;]*\bin\b|\bwhile\b\s|\brange\s*\(|\bxargs\b|\bfind\b[^|]*-exec")
WRITES_HTML = re.compile(
    r">>?\s*['\"]?[^\s'\"|;&]*\.html"          # redirection to any .html
    r"|open\s*\([^)]*\.html[^)]*['\"](?:w|a|x)"   # python open(..., 'w')
    r"|\.html['\"]\s*,\s*['\"](?:w|a|x)"        # open('x.html','w') arg order
    r"|write_text\s*\("                            # pathlib
    r"|\btee\b[^|;&]*\.html")

WRITE_PATTERNS = [
    (re.compile(r">>?\s*['\"]?[^\s'\"|;&]*" + SLIDE), "shell redirection into a slide file"),
    (re.compile(r"\btee\b[^|;&]*" + SLIDE), "tee into a slide file"),
    (re.compile(r"\b(?:cp|mv|rsync|install)\b[^|;&]*" + SLIDE), "copying a file onto a slide path"),
    (re.compile(r"open\s*\(\s*[^)]*" + SLIDE + r"[^)]*['\"](?:w|a|x)"), "python open(..., 'w') on a slide file"),
    (re.compile(r"\.write_text\s*\(|Path\s*\([^)]*" + SLIDE + r"[^)]*\)\s*\.\s*write"), "pathlib write to a slide file"),
    (re.compile(r"\bsed\b[^|;&]*-i[^|;&]*" + SLIDE), "in-place sed on a slide file"),
]


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0

    cmd = (payload.get("tool_input", {}) or {}).get("command", "") or ""
    if not cmd:
        return 0

    # new_slide.py's own file write is invisible to the WRITE_PATTERNS/WRITES_HTML
    # regexes below (it writes via Python, not shell redirection), so a loop that
    # calls it repeatedly would otherwise slip through both this check AND the
    # ENGINE_SCRIPTS bypass right below. Checked FIRST, and independent of
    # ENGINE_SCRIPTS membership, so being a sanctioned script never exempts a loop.
    if ITERATES.search(cmd) and NEW_SLIDE_RE.search(cmd):
        print(
            "BLOCKED by the one-slide-per-turn rule: this Bash command loops and calls "
            "new_slide.py.\n\n"
            "new_slide.py is sanctioned for ONE slide per invocation — that is what keeps a\n"
            "human (or agent) design judgment pass between slides. Looping it recreates the\n"
            "exact batching failure this rule exists to prevent, just one level removed from\n"
            "raw HTML generation: N slides created with nobody looking at any of them.\n\n"
            "Call `new_slide.py` once, edit that slide, report back, and wait for the next\n"
            "brief before creating the next one.",
            file=sys.stderr,
        )
        return 2

    # Archiving stale/orphan slides out of the way is sanctioned regardless of
    # loop shape — it is cleanup of already-written files, not new content
    # created without a design-judgment pass.
    if ARCHIVE_MV_RE.search(cmd):
        return 0

    # An engine script anywhere in the command means this is sanctioned tooling.
    if any(script in cmd for script in ENGINE_SCRIPTS):
        return 0

    # A loop that writes .html is the batching shape even when the filename is
    # interpolated ("$i-slide.html", f"{n}-{t}.html") and so matches no literal
    # slide pattern. This is the case the original failure actually took.
    if ITERATES.search(cmd) and WRITES_HTML.search(cmd):
        print(
            "BLOCKED by the one-slide-per-turn rule: this Bash command loops over slides "
            "and writes HTML.\n\n"
            "Generating several slides in one pass is the specific failure this rule exists\n"
            "to prevent — it produced inconsistent accent colours across a deck and a bespoke\n"
            "SVG that rendered invisible, because no one ever looked at a single slide with\n"
            "design judgment.\n\n"
            "Write one slide with the `Write` tool, report back, and wait for the next brief.",
            file=sys.stderr,
        )
        return 2

    for pattern, shape in WRITE_PATTERNS:
        m = pattern.search(cmd)
        if not m:
            continue
        targets = sorted(set(re.findall(SLIDE, cmd)))
        many = len(targets) > 1 or bool(re.search(r"\bfor\b.*\bin\b|\bwhile\b|range\s*\(|glob", cmd))
        print(
            f"BLOCKED by the one-slide-per-turn rule: this Bash command writes slide HTML "
            f"({shape}).\n"
            f"  target(s): {', '.join(targets[:6]) or 'a slide file'}"
            + (f" …and more" if len(targets) > 6 else "") + "\n\n"
            + ("This looks like a script generating several slides in one pass. That is the\n"
               "specific failure this rule exists to prevent: it produces inconsistent accent\n"
               "colours across slides and SVG bugs nobody notices, because no one ever looked\n"
               "at a single slide with design judgment.\n\n"
               if many else
               "Slide HTML may only be created or changed through the Write/Edit tools.\n"
               "Writing it from Bash also skips slide_write_check.py, so the slide never gets\n"
               "its brand audit.\n\n")
            + "Use the `Write` tool, one slide per turn. If you are the deck-designer agent,\n"
              "write this slide, report back, and wait for the next brief.\n"
              "Engine scripts that legitimately rewrite slides (fix_font_paths.py,\n"
              "apply_edits.py) are allowed and unaffected.",
            file=sys.stderr,
        )
        return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())
