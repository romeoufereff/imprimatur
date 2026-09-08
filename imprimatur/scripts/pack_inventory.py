#!/usr/bin/env python3
"""
pack_inventory.py — ask the ACTIVE pack what it offers.

The engine must not know what any particular pack contains. Naming a file like
`snippets/pipeline-4step.html` in a skill looks harmless and is the same mistake as hardcoding
a hex: it silently assumes one brand's folder, so a pack that organises its assets differently —
or ships none — sends the designer hunting for a file that was never there.

So the boot sequence asks instead of assuming. This prints what the active pack actually has,
resolved through its own manifest (`templatesDir`, `snippetsDir`, `chartsDir`), which means a
pack can rename or omit any of them and the engine keeps working.

An empty category is a real answer, not a failure. A pack with no chart examples is telling you
to author the chart from its tokens rather than copy one.

Usage:
    pack_inventory.py                 # human-readable
    pack_inventory.py --json          # machine-readable
    pack_inventory.py --kind charts   # one category
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ds_config  # noqa: E402

# Manifest key -> what the category is for. The engine knows the ROLES a pack may fill,
# never the filenames that fill them.
CATEGORIES = {
    "templates": ("tokens.templatesDir", "templates",
                  "Full slide layouts. Copy one verbatim to start a slide — its data-template "
                  "attribute is how the validator knows the slide came from the pack."),
    "snippets": ("tokens.snippetsDir", "snippets",
                 "Reusable markup fragments: diagrams, callouts, SVG <defs> starter kits."),
    "charts": ("tokens.chartsDir", "charts",
               "Chart examples already wired to the pack's palette."),
}


def collect(ds):
    out = {}
    for name, (key, default, purpose) in CATEGORIES.items():
        rel = ds.get(key, default)
        entries = []
        if isinstance(rel, str):
            d = ds.path(rel)
            if os.path.isdir(d):
                for fn in sorted(os.listdir(d)):
                    if fn.lower().endswith((".html", ".svg")) and not fn.startswith("."):
                        entries.append(fn)
        out[name] = {"dir": rel if isinstance(rel, str) else None,
                     "declared": ds.get(key) is not None,
                     "purpose": purpose, "entries": entries}
    return out


def main():
    ap = argparse.ArgumentParser(description="List what the active design-system pack provides.")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--kind", choices=sorted(CATEGORIES), default=None)
    ap.add_argument("--design-system", default=None, help="Override the active pack")
    args = ap.parse_args()

    ds = ds_config.load(args.design_system)
    inv = collect(ds)
    if args.kind:
        inv = {args.kind: inv[args.kind]}

    if args.json:
        print(json.dumps({"pack": ds.name, "id": ds.id, "root": ds.root, "inventory": inv},
                         indent=2, ensure_ascii=False))
        return

    print(f"{ds.name}  ({ds.root})")
    for name, info in inv.items():
        if not info["declared"] and not info["entries"]:
            print(f"\n  {name}: not provided by this pack")
            print(f"    {info['purpose']}")
            print("    -> author it from the pack's tokens instead of looking for a file")
            continue
        print(f"\n  {name}/  ({len(info['entries'])})")
        print(f"    {info['purpose']}")
        for e in info["entries"]:
            print(f"      {e}")
        if not info["entries"]:
            print("      (declared but empty — author from tokens)")


if __name__ == "__main__":
    main()
