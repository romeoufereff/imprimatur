#!/usr/bin/env python3
"""
Design-plan checker (WP4) — mechanically checks a locked `design-decisions.md`
`## Slides` table against the VARIANCE dial's thresholds
(`skills/imprimatur/references/taste-dials.md`), BEFORE any designer is
spawned. Turns "does the plan avoid a wall of cards" from a model tallying
templates by eye into a script that either PASSes or names the exact
violation — and, run again after the deck is assembled, gives design-crit's
deck-level pass the same tally instead of asking the model to recount.

Reads (never writes):
  - `<deck-dir>/design-decisions.md`'s `## Slides` table:
    `| # | File | Template | Visual | Focal | Status |`
  - `<deck-dir>/deck-state.json`'s `dials.variance` (low|medium|high), unless
    `--variance` overrides it.

VARIANCE thresholds (taste-dials.md):
    | Setting | Max same template | Adjacent repeats? | Breather cadence | Min visual (deck >= 8) |
    | low     | <= 3x  | allowed        | >=1 per 5 dense slides | >= 1 |
    | medium  | <= 2x  | allowed        | >=1 per 4 dense slides | >= 2 |
    | high    | <= 2x  | NOT allowed    | >=1 per 3 dense slides | >= 3, incl. >= 1 bespoke |

A "breather" slide is a chapter-break / big-idea / pull-quote / cover-shaped
template — the engine has no brand-specific notion of this, so it is
identified either from the pack's own `templateRoles.breather` list in
design-system.json (if the pack declares one) or, failing that, a filename-
keyword heuristic (divider, big-idea, quote, closing, cover) — imperfect,
but the pack is free to declare the real list. `--breather stem1,stem2,...`
overrides both for one run.

Usage:
    plan_check.py --deck-dir D [--variance low|medium|high] [--breather stem1,stem2]

Exit 0 = PASS; 1 = at least one violation (printed).
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ds_config import load  # noqa: E402

THRESHOLDS = {
    "low":    {"max_repeat": 3, "adjacent_ok": True,  "cadence": 5, "min_visual": 1, "min_bespoke": 0},
    "medium": {"max_repeat": 2, "adjacent_ok": True,  "cadence": 4, "min_visual": 2, "min_bespoke": 0},
    "high":   {"max_repeat": 2, "adjacent_ok": False, "cadence": 3, "min_visual": 3, "min_bespoke": 1},
}

BREATHER_KEYWORDS = ("divider", "big-idea", "quote", "closing", "cover")

ROW_RE = re.compile(
    r"^\|\s*(\d+)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*([^|]*?)\s*\|\s*([^|]+?)\s*\|\s*$"
)


def parse_slides_table(design_decisions_path):
    """Returns a list of {n, file, template, visual, focal, status} dicts, in
    the order they appear in the table (NOT necessarily slide-number order —
    that's the plan's business, not this parser's)."""
    if not os.path.isfile(design_decisions_path):
        sys.exit(f"error: no design-decisions.md at {design_decisions_path}")
    text = open(design_decisions_path, encoding="utf-8").read()
    m = re.search(r"^## Slides\s*$(.*?)(?=^## |\Z)", text, re.M | re.S)
    if not m:
        sys.exit("error: no '## Slides' section found in design-decisions.md")
    rows = []
    for line in m.group(1).splitlines():
        line = line.strip()
        if not line.startswith("|") or set(line.replace("|", "").strip()) <= {"-"}:
            continue
        rm = ROW_RE.match(line)
        if not rm:
            continue
        n, file_, template, visual, focal, status = rm.groups()
        if n.strip() == "#":
            continue  # header row
        rows.append({
            "n": int(n), "file": file_, "template": template,
            "visual": visual.lower(), "focal": focal, "status": status,
        })
    return rows


def load_variance(deck_dir, override):
    if override:
        return override
    path = os.path.join(deck_dir, "deck-state.json")
    if os.path.isfile(path):
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            v = (data.get("dials", {}) or {}).get("variance")
            if v in THRESHOLDS:
                return v
        except Exception:
            pass
    return "medium"  # taste-dials.md's own "system default" framing


def breather_set(ds, override):
    if override:
        return set(override)
    declared = ds.get("templateRoles.breather")
    if isinstance(declared, list) and declared:
        return set(declared)
    # Heuristic fallback — a pack that cares about precision should declare
    # templateRoles.breather in design-system.json instead of relying on this.
    templates = [os.path.splitext(os.path.basename(p))[0]
                for p in __import__("glob").glob(os.path.join(ds.templates_dir, "*.html"))]
    return {t for t in templates if any(k in t.lower() for k in BREATHER_KEYWORDS)}


def check(rows, thresholds, breathers):
    violations = []
    ordered = sorted(rows, key=lambda r: r["n"])
    n_slides = len(ordered)

    # 1. Max same-template repeat count
    counts = {}
    for r in ordered:
        counts[r["template"]] = counts.get(r["template"], 0) + 1
    for tmpl, c in counts.items():
        if c > thresholds["max_repeat"]:
            violations.append(
                f'template "{tmpl}" used {c}x — exceeds the max-repeat threshold '
                f'({thresholds["max_repeat"]}x) for this VARIANCE setting')

    # 2. Adjacent-repeat rule (high only)
    if not thresholds["adjacent_ok"]:
        for a, b in zip(ordered, ordered[1:]):
            if a["template"] == b["template"]:
                violations.append(
                    f'slides {a["n"]:02d} and {b["n"]:02d} both use template '
                    f'"{a["template"]}" — adjacent repeats are not allowed at this '
                    f'VARIANCE setting (high)')

    # 3. Min visual slides (only enforced for decks of 8+)
    if n_slides >= 8:
        visual_rows = [r for r in ordered if r["visual"] not in ("none", "")]
        bespoke_rows = [r for r in visual_rows if r["visual"] == "bespoke"]
        if len(visual_rows) < thresholds["min_visual"]:
            violations.append(
                f'only {len(visual_rows)} slide(s) carry a real visual (chart/pipeline/'
                f'bespoke) — needs >= {thresholds["min_visual"]} for a {n_slides}-slide deck '
                f'at this VARIANCE setting')
        if thresholds["min_bespoke"] and len(bespoke_rows) < thresholds["min_bespoke"]:
            violations.append(
                f'only {len(bespoke_rows)} bespoke-SVG slide(s) — needs >= '
                f'{thresholds["min_bespoke"]} at this VARIANCE setting (high)')

    # 4. Breather cadence: no run of more than `cadence` consecutive non-breather
    #    ("dense") slides without one breather in between.
    run = 0
    max_run = 0
    worst_start = None
    cur_start = None
    for r in ordered:
        is_breather = r["template"] in breathers
        if is_breather:
            run = 0
            cur_start = None
        else:
            if run == 0:
                cur_start = r["n"]
            run += 1
            if run > max_run:
                max_run = run
                worst_start = cur_start
    if max_run > thresholds["cadence"]:
        violations.append(
            f'{max_run} consecutive non-breather slides starting at slide '
            f'{worst_start:02d} — breather cadence for this VARIANCE setting is '
            f'>= 1 per {thresholds["cadence"]} dense slides')

    return violations


def main():
    ap = argparse.ArgumentParser(description=__doc__.strip().split("\n")[0])
    ap.add_argument("--deck-dir", required=True)
    ap.add_argument("--variance", choices=sorted(THRESHOLDS), default=None,
                    help="Override deck-state.json's dials.variance")
    ap.add_argument("--breather", default=None,
                    help="Comma-separated template stems to treat as breathers, "
                        "overriding the pack manifest / filename heuristic")
    args = ap.parse_args()

    deck_dir = os.path.abspath(args.deck_dir)
    if not os.path.isdir(deck_dir):
        sys.exit(f"error: no such deck dir: {deck_dir}")

    ds = load()
    rows = parse_slides_table(os.path.join(deck_dir, "design-decisions.md"))
    if not rows:
        sys.exit("error: '## Slides' table has no data rows to check")

    variance = load_variance(deck_dir, args.variance)
    breathers = breather_set(ds, args.breather.split(",") if args.breather else None)
    thresholds = THRESHOLDS[variance]

    violations = check(rows, thresholds, breathers)

    print(f"VARIANCE={variance}  slides={len(rows)}  "
          f"breather templates considered: {', '.join(sorted(breathers)) or '(none found)'}")
    if violations:
        for v in violations:
            print(f"  FAIL  {v}")
        print(f"\n{len(violations)} plan violation(s). Fix the plan (swap a template variant, "
              f"re-insert a breather) and re-run before spawning designers.")
        sys.exit(1)
    print("PASS")


if __name__ == "__main__":
    main()
