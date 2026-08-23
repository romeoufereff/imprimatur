#!/usr/bin/env python3
"""Smoke test for block_batch_slide_write.py — run any time the hook changes.

A blocking hook is only worth having if it blocks the right things and lets the
rest through. The false-positive cases below matter more than the true positives:
a hook that blocks `validate.py` would make the pipeline unusable, and the
temptation would be to disable it rather than fix it.

Usage:  python3 hooks/test_block_batch_slide_write.py
"""
import json
import os
import subprocess
import sys

HOOK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "block_batch_slide_write.py")

BLOCK = 2
ALLOW = 0

CASES = [
    # (expected, name, command)
    (BLOCK, "heredoc into one slide",
     "cat > 03-problem.html <<'EOF'\n<html>…</html>\nEOF"),
    (BLOCK, "loop templating every slide",
     'for i in 01 02 03; do echo "$HTML" > "$i-slide.html"; done'),
    (BLOCK, "python writing slides in one pass",
     "python3 -c \"for n,t in slides: open(f'{n}-{t}.html','w').write(render(t))\""),
    (BLOCK, "append redirection",
     "echo '<div>' >> 07-risks.html"),
    (BLOCK, "cp a template onto a slide path",
     "cp design-system/templates/03-two-column.html deck/04-solution.html"),
    (BLOCK, "in-place sed across slides",
     "sed -i '' 's/foo/bar/' 01-cover.html 02-big-idea.html"),
    (BLOCK, "tee into a slide",
     "echo '<html>' | tee 09-closing.html"),

    (ALLOW, "validate a slide",
     "python3 scripts/validate.py deck/01-cover.html"),
    (ALLOW, "qa a slide",
     "python3 scripts/qa.py deck/05-architecture.html --render /tmp/s.png"),
    (ALLOW, "fix_font_paths rewrites slides on purpose",
     'python3 scripts/fix_font_paths.py --deck-dir "/decks/acme"'),
    (ALLOW, "apply_edits materialises review edits",
     'python3 skills/deck-review/scripts/apply_edits.py --deck-dir "/decks/acme"'),
    (ALLOW, "serve the preview",
     'python3 -m http.server 8934 --directory "/decks/acme"'),
    (ALLOW, "export to pdf",
     'python3 skills/pdf-export/scripts/batch_convert.py --deck-dir "/d" --output "/d/x.pdf" --glob "[0-9]*.html"'),
    (ALLOW, "read a slide",
     "cat 01-cover.html | head -40"),
    (ALLOW, "grep across slides",
     "grep -l 'data-template' deck/*.html"),
    (ALLOW, "write a non-slide file",
     "cat > deck-metadata.json <<'EOF'\n{}\nEOF"),
    (ALLOW, "write index.html (the viewer, not a slide)",
     "cat > index.html <<'EOF'\n<html></html>\nEOF"),
    (ALLOW, "unrelated command",
     "ls -la /tmp"),
]


def run(command):
    proc = subprocess.run(
        [sys.executable, HOOK],
        input=json.dumps({"tool_input": {"command": command}}),
        capture_output=True, text=True,
    )
    return proc.returncode, proc.stderr


def main():
    results = []
    for expected, name, command in CASES:
        code, err = run(command)
        ok = code == expected
        results.append(ok)
        verb = "BLOCK" if expected == BLOCK else "allow"
        detail = "" if ok else f"  (expected {expected}, got {code})"
        print(f"{'PASS' if ok else 'FAIL'}  [{verb}] {name}{detail}")

    failed = results.count(False)
    print(f"\n{results.count(True)}/{len(results)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
