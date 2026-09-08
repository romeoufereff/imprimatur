#!/usr/bin/env python3
"""Smoke test for export_gate.py — run any time the hook changes.

Usage:  python3 ~/.claude/hooks/test_export_gate.py
Prints one PASS/FAIL line per case and exits non-zero on any failure.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

HOOK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "export_gate.py")


def run_hook(command):
    payload = json.dumps({"tool_input": {"command": command}})
    proc = subprocess.run(
        [sys.executable, HOOK], input=payload, capture_output=True, text=True
    )
    return proc.returncode, proc.stderr


def main():
    tmp = tempfile.mkdtemp(prefix="export_gate_test_")
    results = []

    def check(name, expected_code, actual_code, stderr=""):
        ok = expected_code == actual_code
        results.append(ok)
        detail = "" if ok else f"  (expected {expected_code}, got {actual_code}; stderr: {stderr.strip()[:120]})"
        print(f"{'PASS' if ok else 'FAIL'}  {name}{detail}")

    def deck(name, state=None, annotations=None, slides=True):
        d = os.path.join(tmp, name)
        os.makedirs(d, exist_ok=True)
        if slides:
            # a folder only counts as a deck if it holds slides — see _looks_like_deck
            open(os.path.join(d, "01-cover.html"), "w").write("<html></html>")
        if state is not None:
            with open(os.path.join(d, "deck-state.json"), "w") as f:
                json.dump(state, f)
        if annotations is not None:
            with open(os.path.join(d, "annotations.json"), "w") as f:
                json.dump(annotations, f)
        return d

    export_cmd = 'python batch_convert.py --deck-dir "{}" --output out.pdf'

    # 1. Non-export command is never touched
    code, err = run_hook("ls -la /tmp")
    check("non-export command allowed", 0, code, err)

    # 2. Export without --deck-dir: nothing to gate on
    code, err = run_hook("python batch_convert.py --output out.pdf")
    check("export without --deck-dir allowed", 0, code, err)

    # 3. No annotations.json, no deck-state.json -> review skipped -> BLOCK
    d = deck("skipped-review")
    code, err = run_hook(export_cmd.format(d))
    check("no review record blocks export", 2, code, err)

    # 4. No annotations.json, deck-state without review flags -> BLOCK
    d = deck("state-no-flags", state={"phase": 10, "review": {"offered": False}})
    code, err = run_hook(export_cmd.format(d))
    check("deck-state without review flags blocks export", 2, code, err)

    # 5. Harness offered, user declined to comment -> allow
    d = deck("offered", state={"review": {"offered": True}})
    code, err = run_hook(export_cmd.format(d))
    check("review.offered allows export", 0, code, err)

    # 6. Recorded fast-track -> allow
    d = deck("fast-track", state={"review": {"fast_track": True}})
    code, err = run_hook(export_cmd.format(d))
    check("review.fast_track allows export", 0, code, err)

    # 7. Open annotations -> BLOCK (regardless of review flags)
    d = deck(
        "open-comments",
        state={"review": {"offered": True}},
        annotations={"annotations": [{"id": "a1", "status": "open", "comment": "fix", "slide_file": "01.html"}]},
    )
    code, err = run_hook(export_cmd.format(d))
    check("open annotation blocks export", 2, code, err)

    # 8. All annotations resolved/declined -> allow
    d = deck(
        "clean",
        annotations={"annotations": [
            {"id": "a1", "status": "resolved"},
            {"id": "a2", "status": "declined"},
        ]},
    )
    code, err = run_hook(export_cmd.format(d))
    check("resolved annotations allow export", 0, code, err)

    # 9. html2pptx.py is gated the same way
    d = deck("pptx-skipped")
    code, err = run_hook(f'python3 html2pptx.py --deck-dir "{d}" --output out.pptx')
    check("pptx export gated too", 2, code, err)

    # 10. build_pptx.py takes IR paths, not --deck-dir — the gate must still find the deck
    #     via --output. Calling the internals directly used to bypass the gate entirely.
    d = deck("via-build-pptx")
    code, err = run_hook(f'python3 build_pptx.py {d}/.pptx-ir/*.json --output "{d}/Deck.pptx"')
    check("build_pptx.py gated via --output", 2, code, err)

    # 11. Same for the single-file PDF renderer.
    d = deck("via-pdf-renderer")
    code, err = run_hook(f'python3 pdf_renderer.py 01-cover.html --output "{d}/01.pdf"')
    check("pdf_renderer.py gated via --output", 2, code, err)

    # 12. An --output whose parent is a reviewed deck must still be allowed through.
    d = deck("reviewed", state={"review": {"offered": True}})
    code, err = run_hook(f'python3 build_pptx.py ir.json --output "{d}/Deck.pptx"')
    check("reviewed deck allows --output-derived export", 0, code, err)

    # 13. An --output pointing somewhere that is not a deck folder is not gateable;
    #     allowing beats blocking on a guessed directory.
    code, err = run_hook('python3 batch_convert.py --output /nonexistent/dir/out.pdf')
    check("unidentifiable deck dir allowed", 0, code, err)

    # 14. An --output into a folder that holds no slides is not a deck export.
    d = deck("scratch", slides=False)
    code, err = run_hook(f'python3 batch_convert.py --output "{d}/out.pdf"')
    check("non-deck output folder allowed", 0, code, err)

    shutil.rmtree(tmp, ignore_errors=True)
    failed = results.count(False)
    print(f"\n{results.count(True)}/{len(results)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
