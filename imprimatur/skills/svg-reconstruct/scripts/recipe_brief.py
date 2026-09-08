#!/usr/bin/env python3
"""
Recipe brief — everything a designer needs to build one diagram type, in ≤ 2 KB.

Before this existed, a designer chunk facing one bespoke slide spent ten Bash
calls and ~2.5 minutes reading `svgkit/*.py`, `recipes/*_builder.py` and the
recipe docs with `sed`/`cat` to learn the config schema and the build call
(2026-09-07 audit). This prints, for a recipe type:

  1. the recipe doc (recipes/<type>.md — when to use, schema notes, build steps,
     failure checks)
  2. the example config (configs/example_<type>.json) — copy it, change the values
  3. the exact build and verify commands

Usage:
    recipe_brief.py <type>          # e.g. process, donut, hub_spoke
    recipe_brief.py --list          # the 20 registered types with one-line uses
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.dirname(HERE)
sys.path.insert(0, SKILL)


def one_liner(md_path):
    try:
        lines = open(md_path, encoding="utf-8").read().splitlines()
    except OSError:
        return ""
    grab = False
    for line in lines:
        if line.lower().startswith("## when to use"):
            grab = True
            continue
        if grab and line.strip():
            return line.strip()
    return ""


def main():
    ap = argparse.ArgumentParser(description=__doc__.strip().split("\n")[0])
    ap.add_argument("type", nargs="?")
    ap.add_argument("--list", action="store_true")
    args = ap.parse_args()

    from recipes.registry import available
    types = available()

    if args.list or not args.type:
        for t in types:
            print(f"{t:14s} {one_liner(os.path.join(SKILL, 'recipes', t + '.md'))}")
        if not args.type:
            print("\nrecipe_brief.py <type> for the schema, example config and build command.")
        return 0

    t = args.type
    if t not in types:
        sys.exit(f"error: no recipe {t!r}. Available: {', '.join(types)}. A one-off shape "
                 f"is built from primitives per recipes/_generic.md.")

    md = os.path.join(SKILL, "recipes", f"{t}.md")
    cfg = os.path.join(SKILL, "configs", f"example_{t}.json")
    print(f"# svg-reconstruct recipe: {t}\n")
    if os.path.isfile(md):
        print(open(md, encoding="utf-8").read().rstrip())
        print()
    if os.path.isfile(cfg):
        data = json.load(open(cfg, encoding="utf-8"))
        print(f"## Example config ({os.path.relpath(cfg, SKILL)}) — copy, then change values only")
        print("```json")
        print(json.dumps(data, indent=2, ensure_ascii=False)[:1400])
        print("```")
        print()
    print("## Build and verify")
    print("```bash")
    print(f'cd "{SKILL}" && python3 -c "from recipes.registry import get_builder; '
          f'get_builder(\'{t}\')(\'<your-config>.json\', \'<out>.svg\')"')
    print(f'python3 "{os.path.join(SKILL, "svgkit", "render.py")}" <out>.svg <out>.png   # look once (size from the viewBox); never ship round 1')
    print("```")
    print("Colours come from the pack via svgkit.presets (sequential_stops / gradients.auto); "
          "icons via svgkit.icons.place; primary labels ≥ presets.MIN_BODY_PX, sub-labels ≥ "
          "presets.MIN_LABEL_PX. Merge the SVG's <defs> + body into the host slide's visual area "
          "(designer-bespoke-svg.md § How to build one). Do not read svgkit/*.py to learn the API — "
          "the builder call above is the whole API for a recipe.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
