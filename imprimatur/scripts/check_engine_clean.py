#!/usr/bin/env python3
"""Check the engine does not know any brand.

The pipeline's central claim is that every concrete visual value comes from the
active pack. Nothing ever verified it, and 72 hardcoded hexes had accumulated in
engine code — all of them the *default* pack's values, inlined as fallbacks and as
literals. That is an easy drift to make and a hard one to notice: while the default
pack was loaded, everything looked right. Point DECK_DESIGN_SYSTEM at another pack
and the engine kept painting accent runs in the default pack's blue. Prose said
"never hardcode a brand value" in five places while that ran.

So: this check exists because the rule was unenforced, not because anyone doubted
it. It classifies every hex in engine code and in the shipped SVG example configs,
and fails on the ones that cannot be explained.

Allowed:
  · CSS/SVG specification defaults      (#000000, #FFFFFF, the named colours)
  · values the active pack declares     (Tailwind config + design-system.json)
  · the achromatic role fallbacks       (grey placeholders, listed below)
  · deliberately off-brand fixture seeds (the forge writes these to be rejected)
  · the review harness's dark chrome    (tool UI, deliberately not the brand)

Anything else is a brand value that has leaked into the engine.

Usage:  scripts/check_engine_clean.py [--verbose]
Exit 0 when clean, 1 otherwise.
"""

import argparse
import glob
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from ds_config import load  # noqa: E402

HEX = re.compile(r'#([0-9A-Fa-f]{6})\b')

SPEC_DEFAULTS = {"000000", "FFFFFF", "808080", "FF0000", "008000", "0000FF"}

# Achromatic stand-ins for roles a pack does not fill. Grey is honest about being a
# placeholder in a way a plausible blue is not — see svgkit/presets.py.
NEUTRAL_FALLBACKS = {"1A1A1A", "3D3D3D", "6A6A6A", "D0D0D0", "F5F5F5",
                     "999999", "3355DD", "B4690E", "1A7F37"}

# The forge writes these into every off-brand fixture precisely so the pack rejects
# them. They are supposed to look wrong.
FIXTURE_SEEDS = {"D97757", "F5F1E8", "FF00AA", "123456", "0048FE"}

# The review harness chrome: a dark toolbar that deliberately does not borrow the
# brand, so it never competes with the slide it frames. Its accents DO come from the
# pack (see build_review.py) — these are only the greys.
HARNESS_CHROME = {"0F1115", "171A21", "272B34", "E6E8EC", "9AA0AA",
                  "222732", "3A4150", "14171E", "0E1116"}


def main():
    ap = argparse.ArgumentParser(description=__doc__.strip().split("\n")[0])
    ap.add_argument("--verbose", action="store_true",
                    help="List every hex found and how it was classified")
    args = ap.parse_args()

    ds = load()
    # The sanctioned palette is everything the pack DECLARES, which is both files: the
    # Tailwind config holds the colour tokens, and design-system.json's `svg` block holds
    # the gradient stops (wedge sequences, hub, tint). Reading only the first classified a
    # pack's own wedge colours as foreign — a false positive that would have driven a
    # large and completely wrong "fix".
    pack_hexes = set()
    for f in (ds.config_file, os.path.join(ds.root, "design-system.json")):
        try:
            pack_hexes |= {h.upper() for h in HEX.findall(open(f, encoding="utf-8").read())}
        except OSError:
            pass

    allowed = SPEC_DEFAULTS | NEUTRAL_FALLBACKS | FIXTURE_SEEDS | HARNESS_CHROME | pack_hexes

    # Python plus the shipped SVG example configs. The configs are the fixtures the
    # svg-reconstruct skill tells you to start from, so a stale value there is copied into
    # the next reconstruction exactly as one in code would be.
    scan = sorted(glob.glob(os.path.join(PLUGIN, "**", "*.py"), recursive=True))
    scan += sorted(glob.glob(os.path.join(PLUGIN, "skills", "svg-reconstruct",
                                          "configs", "*.json")))

    offenders, counted = [], 0
    for path in scan:
        if os.path.basename(path) == os.path.basename(__file__):
            continue
        rel = os.path.relpath(path, PLUGIN)
        for lineno, line in enumerate(open(path, encoding="utf-8"), 1):
            for h in HEX.findall(line):
                counted += 1
                H = h.upper()
                if H in allowed:
                    if args.verbose:
                        print(f"  ok   {rel}:{lineno}  #{H}")
                    continue
                offenders.append((rel, lineno, H, line.strip()[:70]))

    if offenders:
        print(f"{len(offenders)} unexplained hex value(s) in engine code — a brand value has "
              f"leaked out of the pack:\n")
        for rel, lineno, H, src in offenders:
            print(f"  {rel}:{lineno}")
            print(f"    #{H}   {src}")
        print("\nAsk the pack for it instead: ds.color('<role>'), or add the role to the "
              "pack's manifest if none fits.")
        return 1

    print(f"engine clean — {counted} hex value(s), all accounted for [{ds.name}]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
