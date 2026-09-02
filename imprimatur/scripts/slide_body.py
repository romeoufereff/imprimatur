#!/usr/bin/env python3
"""
Print only the `<body>...</body>` region of one or more slide files, with line
numbers (WP5).

Both auditors (brand-audit, design-crit) and the revision designer used to
`Read` a slide's full HTML — including its identical ~15-25KB head boilerplate
(Tailwind config, @font-face declarations, the scaler script) — every time
they needed to see a slide's content. That head is design-system-agnostic
noise for anyone judging composition, wording, or a token value already
covered by `validate.py`; re-reading it N times per deck is exactly the kind
of re-read the optimization plan measured (7K tokens by the tenth slide via
design-decisions.md's growth, the same shape of waste here per full-file Read).

Usage:
    slide_body.py FILE...

Prints, for each file: a `# <filename>` header, then the body region with
1-based line numbers matching the file's own line numbering (so a finding can
still be reported as "line 142", directly Editable).
"""
import argparse
import os
import re
import sys


def body_region_with_lines(path):
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
    return "\n".join(f"{i + 1:>6}\t{lines[i]}" for i in range(start, end + 1))


def main():
    ap = argparse.ArgumentParser(description=__doc__.strip().split("\n")[0])
    ap.add_argument("files", nargs="+", metavar="FILE")
    args = ap.parse_args()

    missing = [f for f in args.files if not os.path.isfile(f)]
    if missing:
        for m in missing:
            print(f"error: no such file: {m}", file=sys.stderr)
        sys.exit(2)

    for i, path in enumerate(args.files):
        if i:
            print()
        print(f"# {os.path.basename(path)}")
        print(body_region_with_lines(path))


if __name__ == "__main__":
    main()
