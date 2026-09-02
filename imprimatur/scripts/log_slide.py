#!/usr/bin/env python3
"""
Structured, capped bookkeeping (WP3) — design-system agnostic.

Replaces free-text design-decisions.md prose (which grew to 14-28KB across a
deck, 7K tokens of re-read by the tenth slide) and ad-hoc Edit calls onto
deck-state.json with one script that:

  1. Upserts exactly one row for slide N in design-decisions.md's `## Slides`
     table (never a duplicate row — re-logging the same N replaces its row).
  2. `--decision key=value` adds/updates one bullet under `## Locked choices`
     (deduplicated by key — locking the SAME choice twice updates it in place).
  3. `--deviation "..."` appends one line under `## Deviations`.
  4. Upserts `slides[N]` in deck-state.json (n, file, title, status, template,
     visual, updated_at) — every OTHER top-level field in deck-state.json (and
     every OTHER slide's entry) is left untouched.

Both files are protected with an flock on `<deck-dir>/.deck.lock` around the
read-modify-write, so two chunk agents (WP4 parallel designers) writing at the
same time never clobber each other's rows.

`--locked` prints ONLY the Locked-choices block (a designer's cheap pre-slide
check, replacing a full Read of a file that used to grow to 28KB). `--summary`
prints the whole design-decisions.md file (the designer's end-of-chunk report,
verbatim — replacing a hand-typed "what I did" summary).

Fixed format (both this engine and the doctrine/prose side depend on it):

    # Design Decisions — <Deck Title>
    ## Locked choices
    - <key>: <value>
    ## Slides
    | # | File | Template | Visual | Focal | Status |
    |---|---|---|---|---|---|
    ## Deviations
    - <NN>: <one line>

Usage:
    log_slide.py --deck-dir D --n N --template <stem> --visual none|chart|pipeline|bespoke \\
                 --focal "<up to ~12 words>" [--status written|revised|approved|pending] \\
                 [--title "<slide title>"] [--decision "key=value"]... [--deviation "..."]
    log_slide.py --deck-dir D --locked
    log_slide.py --deck-dir D --summary
"""
import argparse
import contextlib
import fcntl
import json
import os
import re
import sys
from datetime import datetime, timezone

DECISIONS_FILE = "design-decisions.md"
STATE_FILE = "deck-state.json"
LOCK_FILE = ".deck.lock"

VALID_VISUAL = ("none", "chart", "pipeline", "bespoke")
# "planned" is the orchestrator's own pre-slide-write status (phase 4a pre-locks
# the plan by writing one row per slide directly, before any designer runs) —
# accepted here too so log_slide.py can UPSERT that row in place once the
# designer actually writes the slide, rather than only ever appending a new one.
VALID_STATUS = ("planned", "pending", "written", "revised", "approved")

SKELETON = """# Design Decisions — {title}

## Locked choices

## Slides
| # | File | Template | Visual | Focal | Status |
|---|---|---|---|---|---|

## Deviations
"""


@contextlib.contextmanager
def deck_lock(deck_dir):
    path = os.path.join(deck_dir, LOCK_FILE)
    fh = open(path, "a+")
    try:
        fcntl.flock(fh, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(fh, fcntl.LOCK_UN)
        fh.close()


# ── design-decisions.md ─────────────────────────────────────────────────────

def load_decisions(deck_dir, title_hint=None):
    path = os.path.join(deck_dir, DECISIONS_FILE)
    if os.path.isfile(path):
        return open(path, encoding="utf-8").read()
    return SKELETON.format(title=title_hint or os.path.basename(os.path.normpath(deck_dir)))


def save_decisions(deck_dir, text):
    path = os.path.join(deck_dir, DECISIONS_FILE)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def split_sections(text):
    """Returns {section_name: [lines]} for Locked choices / Slides / Deviations,
    plus the header line(s) before the first '## '. Order-preserving; unknown
    trailing sections (legacy prose) are kept under '_tail' and re-appended as-is
    so this never silently deletes content a human wrote by hand."""
    lines = text.splitlines()
    header, sections, cur = [], {}, None
    order = []
    for line in lines:
        m = re.match(r"^## (.+)$", line)
        if m:
            cur = m.group(1).strip()
            sections[cur] = []
            order.append(cur)
            continue
        if cur is None:
            header.append(line)
        else:
            sections[cur].append(line)
    return header, sections, order


def render(header, sections, order):
    out = list(header)
    for name in order:
        out.append(f"## {name}")
        out.extend(sections[name])
    return "\n".join(out).rstrip() + "\n"


def upsert_locked(sections, order, key, value):
    name = "Locked choices"
    if name not in sections:
        sections[name] = [""]
        order.append(name)
    lines = sections[name]
    prefix = f"- {key}:"
    new_line = f"- {key}: {value}"
    for i, line in enumerate(lines):
        if line.strip().startswith(prefix):
            lines[i] = new_line
            return
    # insert before the trailing blank line(s) if any, else append
    insert_at = len(lines)
    while insert_at > 0 and not lines[insert_at - 1].strip():
        insert_at -= 1
    lines.insert(insert_at, new_line)


def upsert_slide_row(sections, order, n, file, template, visual, focal, status):
    name = "Slides"
    if name not in sections:
        sections[name] = ["| # | File | Template | Visual | Focal | Status |",
                          "|---|---|---|---|---|---|"]
        order.append(name)
    lines = sections[name]
    n_str = f"{int(n):02d}"
    row = f"| {n_str} | {file} | {template} | {visual} | {focal} | {status} |"
    for i, line in enumerate(lines):
        if line.strip().startswith(f"| {n_str} |") or line.strip().startswith(f"| {int(n)} |"):
            lines[i] = row
            return
    lines.append(row)
    # keep the table sorted by slide number (cosmetic, but re-reading it is the point)
    header_rows = lines[:2]
    body = lines[2:]

    def key(line):
        m = re.match(r"\|\s*(\d+)\s*\|", line)
        return int(m.group(1)) if m else 999999
    body.sort(key=key)
    sections[name] = header_rows + body


def append_deviation(sections, order, n, note):
    name = "Deviations"
    if name not in sections:
        sections[name] = []
        order.append(name)
    n_str = f"{int(n):02d}"
    sections[name].append(f"- {n_str}: {note}")


def locked_block(sections):
    name = "Locked choices"
    lines = [l for l in sections.get(name, []) if l.strip()]
    return "## Locked choices\n" + ("\n".join(lines) if lines else "(none locked yet)") + "\n"


# ── deck-state.json ──────────────────────────────────────────────────────────

def load_state(deck_dir):
    path = os.path.join(deck_dir, STATE_FILE)
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return {"slides": []}


def save_state(deck_dir, data):
    path = os.path.join(deck_dir, STATE_FILE)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")


def upsert_state_slide(data, n, file, title, status, template, visual):
    slides = data.setdefault("slides", [])
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    for s in slides:
        if s.get("n") == n:
            s["file"] = file
            if title is not None:
                s["title"] = title
            s["status"] = status
            s["template"] = template
            s["visual"] = visual
            s["updated_at"] = now
            return
    slides.append({
        "n": n, "file": file, "title": title or file, "status": status,
        "template": template, "visual": visual, "updated_at": now,
    })
    slides.sort(key=lambda s: s.get("n", 0))


def main():
    ap = argparse.ArgumentParser(description="Structured design-decisions.md + deck-state.json bookkeeping.")
    ap.add_argument("--deck-dir", required=True)
    ap.add_argument("--n", type=int, help="Slide number")
    ap.add_argument("--template", help="Template stem this slide was copied from")
    ap.add_argument("--visual", choices=VALID_VISUAL, help="Visual complexity, drives render_checks.py scoping")
    ap.add_argument("--focal", help="Up to ~12 words describing the slide's focal point")
    ap.add_argument("--status", choices=VALID_STATUS, default="written")
    ap.add_argument("--file", help="Slide filename (default: the single NN-*.html in --deck-dir whose "
                                   "prefix matches --n; pass explicitly when ambiguous, e.g. 04-big-idea.html)")
    ap.add_argument("--title", help="Slide title (deck-state.json) / deck title (first-run design-decisions.md header)")
    ap.add_argument("--decision", action="append", default=[], metavar="key=value",
                    help="Add/update one Locked-choices bullet. Repeatable.")
    ap.add_argument("--deviation", help="Append one Deviations line for this slide")
    ap.add_argument("--locked", action="store_true", help="Print only the Locked choices block and exit")
    ap.add_argument("--summary", action="store_true", help="Print the whole design-decisions.md file and exit")
    args = ap.parse_args()

    deck_dir = os.path.abspath(args.deck_dir)
    if not os.path.isdir(deck_dir):
        sys.exit(f"error: no such deck dir: {deck_dir}")

    with deck_lock(deck_dir):
        text = load_decisions(deck_dir, args.title)
        header, sections, order = split_sections(text)

        if args.locked:
            print(locked_block(sections).rstrip())
            return
        if args.summary:
            print(render(header, sections, order).rstrip())
            return

        touched = False
        for kv in args.decision:
            if "=" not in kv:
                sys.exit(f"error: --decision must be key=value, got {kv!r}")
            key, value = kv.split("=", 1)
            upsert_locked(sections, order, key.strip(), value.strip())
            touched = True

        if args.n is not None:
            if not args.file:
                # Infer the filename from disk: exactly one NN-*.html with this prefix.
                prefix = f"{args.n:02d}-"
                cands = sorted(f for f in os.listdir(deck_dir)
                               if f.startswith(prefix) and f.endswith(".html") and f != "index.html")
                if len(cands) == 1:
                    args.file = cands[0]
                elif not cands:
                    sys.exit(f"error: no {prefix}*.html in {deck_dir} — pass --file or run new_slide.py first")
                else:
                    sys.exit(f"error: several {prefix}*.html in {deck_dir} ({', '.join(cands)}) — pass --file")
            missing = [f for f in ("template", "visual", "focal", "file") if not getattr(args, f)]
            if missing:
                sys.exit(f"error: --n requires --{', --'.join(missing)} too")
            for w, limit in [(args.focal, 12)]:
                if w and len(w.split()) > 16:  # generous slack past the ~12-word guidance
                    print(f"warn: --focal is {len(w.split())} words — keep it to ~12 or fewer",
                          file=sys.stderr)
            upsert_slide_row(sections, order, args.n, args.file, args.template,
                             args.visual, args.focal, args.status)
            touched = True

            state = load_state(deck_dir)
            upsert_state_slide(state, args.n, args.file, args.title, args.status,
                               args.template, args.visual)
            save_state(deck_dir, state)

        if args.deviation:
            if args.n is None:
                sys.exit("error: --deviation requires --n")
            append_deviation(sections, order, args.n, args.deviation)
            touched = True

        if not touched:
            sys.exit("error: nothing to do — pass --n (+ --template/--visual/--focal/--file), "
                     "--decision, --deviation, --locked, or --summary")

        save_decisions(deck_dir, render(header, sections, order))

    size = os.path.getsize(os.path.join(deck_dir, DECISIONS_FILE))
    print(f"logged slide {args.n if args.n is not None else '(none)'} — "
          f"{DECISIONS_FILE} is now {size} bytes")


if __name__ == "__main__":
    main()
