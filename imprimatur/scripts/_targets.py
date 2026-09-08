"""Shared argument handling for the four slide checkers.

They all take the same shape — zero or more HTML files, defaulting to the active
pack's template set — and all four used to read `sys.argv[1:]` raw. That meant
`--help` was treated as a filename and surfaced as a `FileNotFoundError`
traceback (or, for the Playwright-based ones, as `net::ERR_FILE_NOT_FOUND` on a
file:// URL). A mistyped path did the same.

These are the pipeline's most-invoked scripts and the ones a hook runs
unattended, so a bad path has to come back as an error the orchestrator can route
rather than a stack trace it has to parse.
"""

import argparse
import glob
import os
import sys


def parse(description, default_glob_dir=None, extra=None):
    """Return (args, targets).

    `default_glob_dir` is the directory to sweep when no files are given —
    normally the active pack's `templates/`. `extra` is a callable that can add
    script-specific flags to the parser before it runs.
    """
    ap = argparse.ArgumentParser(
        description=description,
        epilog="With no FILE arguments, checks the active design system's whole template set.",
    )
    ap.add_argument("files", nargs="*", metavar="FILE",
                    help="Slide .html files to check")
    if extra:
        extra(ap)
    args = ap.parse_args()

    targets = list(args.files)
    if not targets and default_glob_dir:
        targets = sorted(glob.glob(os.path.join(default_glob_dir, "*.html")))

    missing = [t for t in targets if not os.path.isfile(t)]
    if missing:
        for m in missing:
            print(f"error: no such file: {m}", file=sys.stderr)
        sys.exit(2)

    if not targets:
        print("error: nothing to check — no files given and the pack's templates "
              "directory is empty.", file=sys.stderr)
        sys.exit(2)

    return args, targets
