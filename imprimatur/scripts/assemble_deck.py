#!/usr/bin/env python3
"""
Assemble the deck viewer + metadata (WP8) — one script call instead of two
hand-typed Writes (`index.html` used to be a "Step 6" the deck-designer agent
did per-deck, duplicating work §7 assembly already owns; `deck-metadata.json`
was retyped from `deck-brief.md` by eye each time).

Writes, from `<deck-dir>/deck-state.json` (+ `deck-brief.md` when present):
  1. `index.html` — the iframe click-through viewer, slide list taken from
     deck-state.json's `slides[]` in `n` order (so an inserted/removed/
     reordered slide is never a stale array retyped by hand).
  2. `deck-metadata.json` — title/client/engagement/audience/deck_type parsed
     from `deck-brief.md`'s `## Intake` bullets when the file exists (best-
     effort; a missing bullet is left as null, never guessed), slide_count +
     dials from deck-state.json, deck_path/deck_url from `--deck-dir`. An
     EXISTING deck-metadata.json's `exports`, `status`, `created_at` and
     `version` fields are preserved across a re-run (an assembled export
     record must never be silently wiped by a later re-assembly).

Usage:
    assemble_deck.py --deck-dir D [--title "Deck Title"]
"""
import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ds_config import load as _load_ds  # noqa: E402  (font family comes from the pack, never hardcoded)

INDEX_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title}</title>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    html, body {{
      width: 100%; height: 100%; background: #111; overflow: hidden;
      font-family: "{font_family}", "-apple-system", sans-serif;
    }}
    iframe {{ width: 100%; height: 100%; border: none; display: block; }}
    #nav {{
      position: fixed; bottom: 20px; left: 50%; transform: translateX(-50%);
      display: flex; align-items: center; gap: 12px;
      background: rgba(0, 0, 0, 0.7); border-radius: 99px; padding: 10px 20px; z-index: 100;
    }}
    #nav button {{
      background: none; border: 1px solid rgba(255, 255, 255, 0.3); color: #fff;
      border-radius: 6px; padding: 6px 16px; cursor: pointer; font-size: 14px;
      transition: all 0.2s ease;
    }}
    #nav button:hover {{ background: rgba(255, 255, 255, 0.1); border-color: rgba(255, 255, 255, 0.6); }}
    #counter {{ color: rgba(255, 255, 255, 0.6); font-size: 13px; min-width: 60px; text-align: center; }}
  </style>
</head>
<body>
  <iframe id="frame" src="{first_slide}"></iframe>

  <div id="nav">
    <button onclick="prev()">← Prev</button>
    <span id="counter">1 / {count}</span>
    <button onclick="next()">Next →</button>
  </div>

  <script>
    const slides = [
{slide_list}
    ];

    let i = 0;
    const frame = document.getElementById('frame');
    const counter = document.getElementById('counter');

    function go(n) {{
      i = Math.max(0, Math.min(slides.length - 1, n));
      frame.src = slides[i];
      counter.textContent = `${{i + 1}} / ${{slides.length}}`;
    }}

    function next() {{ go(i + 1); }}
    function prev() {{ go(i - 1); }}

    document.addEventListener('keydown', (e) => {{
      if (e.key === 'ArrowRight' || e.key === 'ArrowDown') next();
      if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') prev();
    }});

    go(0);
  </script>
</body>
</html>
"""

INTAKE_FIELDS = {
    "client": ("client",),
    "engagement": ("engagement",),
    "audience": ("audience",),
    "outcome": ("deck_type", "outcome"),  # deck-brief's "Outcome:" -> deck_type
}


def load_json(path, default=None):
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return default if default is not None else {}


def parse_intake(brief_path):
    """Best-effort `- **Key:** value` extraction from deck-brief.md's ## Intake
    section. Never guesses a field it can't find — a missing bullet stays null."""
    out = {}
    if not os.path.isfile(brief_path):
        return out
    text = open(brief_path, encoding="utf-8").read()
    m = re.search(r"^## Intake\s*$(.*?)(?=^## |\Z)", text, re.M | re.S)
    section = m.group(1) if m else text
    bullets = dict(re.findall(r"^\s*-\s*\*\*([^*:]+):\*\*\s*(.+)$", section, re.M))
    bullets = {k.strip().lower(): v.strip() for k, v in bullets.items()}
    for meta_key, brief_keys in INTAKE_FIELDS.items():
        for bk in brief_keys:
            if bk in bullets:
                out[meta_key if meta_key != "outcome" else "deck_type"] = bullets[bk]
                break
    # title: the brief's own H1 ("# Deck Brief — <Title>")
    tm = re.search(r"^#\s+Deck Brief\s*[—-]\s*(.+)$", text, re.M)
    if tm:
        out["title"] = tm.group(1).strip()
    return out


def build_index_html(title, slide_files):
    slide_list = ",\n".join(f"      '{s}'" for s in slide_files)
    try:
        font_family = _load_ds().get("typography.familyLabel", "sans-serif")
    except Exception:
        font_family = "sans-serif"
    return INDEX_TEMPLATE.format(
        title=title, first_slide=slide_files[0] if slide_files else "",
        count=len(slide_files), slide_list=slide_list, font_family=font_family,
    )


def main():
    ap = argparse.ArgumentParser(description=__doc__.strip().split("\n")[0])
    ap.add_argument("--deck-dir", required=True)
    ap.add_argument("--title", default=None, help="Override the deck title")
    args = ap.parse_args()

    deck_dir = os.path.abspath(args.deck_dir)
    if not os.path.isdir(deck_dir):
        sys.exit(f"error: no such deck dir: {deck_dir}")

    state = load_json(os.path.join(deck_dir, "deck-state.json"), {})
    slides = sorted(state.get("slides", []) or [], key=lambda s: s.get("n", 0))
    slide_files = [s["file"] for s in slides if s.get("file")]
    if not slide_files:
        sys.exit(f"error: deck-state.json in {deck_dir} has no slides[] with a 'file' field — "
                 f"nothing to assemble")

    title = args.title or state.get("deck") or "Untitled Deck"

    # index.html
    index_path = os.path.join(deck_dir, "index.html")
    with open(index_path, "w", encoding="utf-8") as f:
        f.write(build_index_html(title, slide_files))

    # deck-metadata.json — merge onto whatever already exists so an export
    # record (exports/status/created_at/version) is never silently wiped.
    meta_path = os.path.join(deck_dir, "deck-metadata.json")
    existing = load_json(meta_path, {})
    intake = parse_intake(os.path.join(deck_dir, "deck-brief.md"))

    meta = dict(existing)  # preserve unknown/legacy fields verbatim
    meta["title"] = args.title or existing.get("title") or intake.get("title") or title
    for k in ("client", "engagement", "audience", "deck_type"):
        if intake.get(k):
            meta[k] = intake[k]
        else:
            meta.setdefault(k, existing.get(k))
    meta["slide_count"] = len(slide_files)
    meta["deck_path"] = deck_dir + os.sep
    meta["deck_url"] = "file://" + os.path.join(deck_dir, "index.html")
    meta["deck_brief"] = "deck-brief.md" if os.path.isfile(os.path.join(deck_dir, "deck-brief.md")) else existing.get("deck_brief")
    meta["dials"] = state.get("dials", existing.get("dials", {}))
    meta.setdefault("created_at", datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
    meta.setdefault("version", "1.0")
    meta.setdefault("status", "in_progress")
    meta.setdefault("exports", {})

    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)
        f.write("\n")

    print(f"wrote {index_path} ({len(slide_files)} slide(s))")
    print(f"wrote {meta_path}")


if __name__ == "__main__":
    main()
