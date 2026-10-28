#!/usr/bin/env python3
"""Smoke test: a deck's own deck-state.json `design_system` selects the pack ahead of the
environment, for ds_config directly and for the two hooks that resolve the pack themselves.

Why this exists: on 2026-09-22 a client deck was built while DECK_DESIGN_SYSTEM named the EPAM
pack. Every per-write STATIC verdict and every designer stop gate judged the client slides against
EPAM tokens; three designer agents each burned ~100k tokens arguing with a gate that was reading
the wrong brand. The fix: the deck records its pack once and every consumer reads it from there.

Usage:  python3 hooks/test_ds_config_deck_state.py
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN = os.path.dirname(HERE)
SCRIPTS = os.path.join(PLUGIN, "scripts")
sys.path.insert(0, SCRIPTS)
import ds_config  # noqa: E402

SEED = ds_config.find_root()  # whatever the env/default gives us — a real pack to clone


def make_pack(tmp, name):
    """A second, distinguishable pack: the default pack copied with a new id/name."""
    dst = os.path.join(tmp, name)
    shutil.copytree(SEED, dst, symlinks=True,
                    ignore=shutil.ignore_patterns("templates", "references", "evals", "fonts",
                                                  "charts", "snippets", "assets", "*.png"))
    os.makedirs(os.path.join(dst, "templates"), exist_ok=True)
    m = json.load(open(os.path.join(dst, "design-system.json")))
    m["id"], m["name"] = name, f"{name} test pack"
    json.dump(m, open(os.path.join(dst, "design-system.json"), "w"))
    return dst


def main():
    results = []

    def check(label, ok, detail=""):
        results.append((label, ok, detail))
        print(("PASS " if ok else "FAIL ") + label + (f"  ({detail})" if detail and not ok else ""))

    with tempfile.TemporaryDirectory() as tmp:
        other = make_pack(tmp, "otherbrand")
        deck = os.path.join(tmp, "deck")
        os.makedirs(deck)
        json.dump({"deck": "t", "design_system": other, "slides": []},
                  open(os.path.join(deck, "deck-state.json"), "w"))
        slide = os.path.join(deck, "01-cover.html")
        open(slide, "w").write("<html></html>")
        env = dict(os.environ, DECK_DESIGN_SYSTEM=SEED, CLAUDE_PLUGIN_ROOT=PLUGIN)
        env.pop("DECK", None)

        # 1. explicit deck_dir wins over the env
        check("deck_dir= selects the deck's pack over $DECK_DESIGN_SYSTEM",
              ds_config.find_root(deck_dir=deck) == other)
        # 2. a path INSIDE the deck (a slide) is enough
        check("a slide path inside the deck resolves the deck's pack",
              ds_config.find_root(deck_dir=slide) == other)
        # 3. no hint at all -> env still wins (cwd is not a deck)
        saved = os.environ.get("DECK_DESIGN_SYSTEM")
        os.environ["DECK_DESIGN_SYSTEM"] = SEED
        os.environ.pop("DECK", None)
        try:
            check("without a deck hint the env pack is used",
                  ds_config.find_root() == os.path.abspath(SEED))
            # 4. $DECK alone is enough
            os.environ["DECK"] = deck
            check("$DECK selects the deck's pack", ds_config.find_root() == other)
            os.environ.pop("DECK", None)
            # 5. explicit path beats the deck
            check("an explicit path beats the deck's declaration",
                  ds_config.find_root(explicit=SEED, deck_dir=deck) == os.path.abspath(SEED))
        finally:
            if saved is None:
                os.environ.pop("DECK_DESIGN_SYSTEM", None)
            else:
                os.environ["DECK_DESIGN_SYSTEM"] = saved

        # 6. the CLI --header names the deck's pack
        out = subprocess.run([sys.executable, os.path.join(SCRIPTS, "ds_config.py"), "--header",
                              "--deck-dir", deck], capture_output=True, text=True, env=env)
        check("ds_config.py --header --deck-dir reports the deck's pack",
              f"PACK={other}" in out.stdout, out.stdout.strip()[:200] or out.stderr[-200:])

        # 7. the per-write hook judges the slide against the deck's pack (id shows in the verdict
        #    only on FAIL text; here we check it did not SKIP and did not name the env pack's tokens)
        hook = os.path.join(HERE, "slide_write_check.py")
        proc = subprocess.run([sys.executable, hook], input=json.dumps({"tool_input": {"file_path": slide}}),
                              capture_output=True, text=True, env=env, timeout=60)
        ctx = ""
        try:
            ctx = json.loads(proc.stdout)["hookSpecificOutput"]["additionalContext"]
        except Exception:
            pass
        seed_prefix = json.load(open(os.path.join(SEED, "design-system.json")))["tokens"].get("prefix", "")
        check("slide_write_check resolves the deck's pack (verdict mentions no env-pack prefix)",
              ctx.startswith("STATIC") and (not seed_prefix or f"{seed_prefix}-*" not in ctx),
              ctx[:200])

        # 8. a declaration that points nowhere falls through with a stderr note, never crashes
        bad = os.path.join(tmp, "baddeck")
        os.makedirs(bad)
        json.dump({"design_system": os.path.join(tmp, "nowhere")}, open(os.path.join(bad, "deck-state.json"), "w"))
        check("a dangling declaration falls back instead of crashing",
              ds_config.find_root(deck_dir=bad) is not None)

    failed = [r for r in results if not r[1]]
    print(f"\n{len(results) - len(failed)}/{len(results)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
