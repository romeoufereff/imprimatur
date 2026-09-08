#!/usr/bin/env python3
"""
deck-review — annotations.json lifecycle CLI.

Eliminates the ad-hoc scratch scripts previously needed to flip annotation
statuses: one Bash call per operation, and the resolution note is read from
STDIN so apostrophes/quotes in prose never fight shell escaping.

Usage:
    annotations.py --file <annotations.json> list [--open] [--kind edit|comment]
    annotations.py --file <annotations.json> show <id>
    echo "note text" | annotations.py --file <annotations.json> resolve <id>
    echo "reason"    | annotations.py --file <annotations.json> decline <id>

Notes:
  - resolve/decline read the note from stdin (pipe, heredoc, or `<<<`).
    An empty stdin is rejected — every status change must carry a note.
  - `list` prints one line per annotation: id, kind marker, status, slide, comment head.
    A `kind: "edit"` entry is a direct manipulation staged by the harness's Edit mode;
    its `decl` holds the exact declarations currently overriding the slide. Resolving one
    means you PROMOTED it into the slide source (tokens/classes, re-audited) — after which
    `apply_edits.py` drops its rule from the override block. Never resolve an edit you have
    not actually folded into the markup: the override would vanish and the change with it.
  - Exit code 0 on success; 1 on any error (unknown id, empty note, bad JSON).
"""

import argparse
import json
import sys


def load(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        sys.exit(f"error: no such file: {path}")
    except json.JSONDecodeError as e:
        sys.exit(f"error: {path} is not valid JSON: {e}")


def save(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")


def find(data, ann_id):
    for a in data.get("annotations", []):
        if a.get("id") == ann_id:
            return a
    sys.exit(f"error: no annotation with id {ann_id!r}")


def cmd_list(data, only_open, only_kind):
    anns = data.get("annotations", [])
    shown = 0
    for a in anns:
        if only_open and a.get("status") != "open":
            continue
        kind = a.get("kind", "comment")
        if only_kind and kind != only_kind:
            continue
        head = " ".join(a.get("comment", "").split())[:86]
        mark = "\u270e" if kind == "edit" else " "
        print(f"{a['id']:>4} {mark} {a.get('status','?'):8}  {a.get('slide_file','?'):24}  {head}")
        shown += 1
    n_open = sum(1 for a in anns if a.get("status") == "open")
    n_edit = sum(1 for a in anns if a.get("kind") == "edit")
    tail = f", {shown} shown" if (only_open or only_kind) else ""
    print(f"-- {len(anns)} total, {n_open} open, {n_edit} staged edit(s){tail}")


def cmd_show(data, ann_id):
    print(json.dumps(find(data, ann_id), indent=2, ensure_ascii=False))


def read_note():
    note = sys.stdin.read().strip()
    if not note:
        sys.exit("error: empty note on stdin — every status change must carry a note")
    return note


def main():
    ap = argparse.ArgumentParser(description="Manage review annotations.json")
    ap.add_argument("--file", required=True, help="Path to annotations.json")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_list = sub.add_parser("list", help="List annotations")
    p_list.add_argument("--open", action="store_true", help="Only open annotations")
    p_list.add_argument("--kind", choices=("edit", "comment"), default=None,
                        help="Only edits (staged direct manipulations) or only written comments")

    p_show = sub.add_parser("show", help="Print one annotation as JSON")
    p_show.add_argument("id")

    for name in ("resolve", "decline"):
        p = sub.add_parser(name, help=f"Mark an annotation {name}d (note from stdin)")
        p.add_argument("id")

    args = ap.parse_args()
    data = load(args.file)

    if args.cmd == "list":
        cmd_list(data, args.open, args.kind)
    elif args.cmd == "show":
        cmd_show(data, args.id)
    else:
        a = find(data, args.id)
        a["status"] = "resolved" if args.cmd == "resolve" else "declined"
        a["resolution"] = read_note()
        save(args.file, data)
        print(f"{args.id} -> {a['status']}")


if __name__ == "__main__":
    main()
