#!/usr/bin/env python3
"""
Print only the SLIDE BRIEFs a designer chunk needs from narrative-outline.md.

The outline is 12–26 KB for a real deck and every chunk agent used to `cat` all
of it at boot (2026-09-07 audit) — the other chunks' briefs are pure context
cost to an agent that is forbidden from touching those slides. This prints the
outline's header (framework + arc, so the chunk knows the story it serves) and
then only the requested `## SLIDE N:` blocks.

Usage:
    narrative_brief.py --deck-dir D --slides 6-10        # a range
    narrative_brief.py --deck-dir D --slides 2,5,6       # a list
    narrative_brief.py --deck-dir D --slides 3 --no-arc  # one brief, no header
    narrative_brief.py --deck-dir D --list               # slide numbers + messages only

Exit 2 if a requested slide has no brief — that is a gap for the orchestrator
to route back to deck-narrative, not one for the designer to fill.
"""
import argparse
import os
import re
import sys

SLIDE_HDR_RE = re.compile(r"^##\s*SLIDE\s+(\d+)\s*:\s*(.*)$", re.I)


def parse_slides(spec):
    out = set()
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        m = re.match(r"^(\d+)\s*[-–]\s*(\d+)$", part)
        if m:
            a, b = int(m.group(1)), int(m.group(2))
            out.update(range(min(a, b), max(a, b) + 1))
        elif part.isdigit():
            out.add(int(part))
        else:
            sys.exit(f"error: cannot parse --slides part {part!r}")
    return sorted(out)


def split_outline(text):
    """Returns (header_lines, {n: [lines]}, order)."""
    header, briefs, order, cur = [], {}, [], None
    for line in text.splitlines():
        m = SLIDE_HDR_RE.match(line)
        if m:
            cur = int(m.group(1))
            briefs[cur] = [line]
            order.append(cur)
            continue
        if cur is None:
            header.append(line)
        else:
            briefs[cur].append(line)
    return header, briefs, order


def main():
    ap = argparse.ArgumentParser(description=__doc__.strip().split("\n")[0])
    ap.add_argument("--deck-dir", required=True)
    ap.add_argument("--slides", help="e.g. 6-10 or 2,5,6")
    ap.add_argument("--list", action="store_true", help="Print slide numbers and messages only")
    ap.add_argument("--no-arc", action="store_true", help="Omit the outline header (framework + arc)")
    args = ap.parse_args()

    path = os.path.join(os.path.abspath(args.deck_dir), "narrative-outline.md")
    if not os.path.isfile(path):
        sys.exit(f"error: {path} not found — has deck-narrative run?")
    header, briefs, order = split_outline(open(path, encoding="utf-8").read())

    if args.list:
        for n in order:
            first = briefs[n][0]
            print(f"{n:02d}  {SLIDE_HDR_RE.match(first).group(2).strip()}")
        return 0

    if not args.slides:
        sys.exit("error: pass --slides <range|list> or --list")
    wanted = parse_slides(args.slides)
    missing = [n for n in wanted if n not in briefs]

    if not args.no_arc:
        hdr = [l for l in header if l.strip()]
        if hdr:
            print("\n".join(hdr))
            print()
    for n in wanted:
        if n in briefs:
            print("\n".join(briefs[n]).rstrip())
            print()
    if missing:
        print(f"error: no SLIDE BRIEF for slide(s) {', '.join(str(m) for m in missing)} in "
              f"{path} — report this gap to the orchestrator; do not invent a brief.", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
