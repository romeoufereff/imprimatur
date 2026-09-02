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

    # WP2: new_slide.py is sanctioned for ONE slide per invocation — a loop
    # calling it must still be blocked (its own file write is invisible to the
    # WRITE_PATTERNS regexes above, so this needs its own check).
    (ALLOW, "new_slide.py single call",
     'python3 scripts/new_slide.py --deck-dir "/decks/acme" --template 01-cover --n 1 --slug cover'),
    (ALLOW, "new_slide.py chained with an Edit-adjacent Bash call (not a loop)",
     'python3 scripts/new_slide.py --deck-dir "/decks/acme" --template 04-big-idea --n 4 --slug big-idea '
     '&& python3 scripts/log_slide.py --deck-dir "/decks/acme" --n 4 --template 04-big-idea --visual none '
     '--focal "hero stat" --status written'),
    (BLOCK, "for-loop calling new_slide.py for every slide",
     'for i in 01 02 03; do python3 scripts/new_slide.py --deck-dir "/d" --template 02-content-bullets '
     '--n "$i" --slug "s$i"; done'),
    (BLOCK, "while-loop calling new_slide.py",
     'while read -r n t; do python3 scripts/new_slide.py --deck-dir "/d" --template "$t" --n "$n" '
     '--slug "s$n"; done < briefs.txt'),
    (BLOCK, "python range() driving new_slide.py via subprocess",
     'python3 -c "import subprocess\\nfor n in range(1,6): subprocess.run([\'python3\','
     '\'scripts/new_slide.py\',\'--deck-dir\',\'/d\',\'--template\',\'t\',\'--n\',str(n),\'--slug\',\'s\'])"'),

    # WP1/WP3/WP5/WP6/WP7/WP8: the rest of the plan's new engine scripts are
    # sanctioned single-call tooling, same as qa.py/validate.py above.
    (ALLOW, "render_checks.py on a batch of files (not a write)",
     'python3 scripts/render_checks.py deck/01-cover.html deck/02-body.html --deck-dir deck --json'),
    (ALLOW, "log_slide.py bookkeeping call",
     'python3 scripts/log_slide.py --deck-dir "/decks/acme" --n 1 --template 01-cover --visual none '
     '--focal "cover" --status written'),
    (ALLOW, "slide_body.py read helper",
     'python3 scripts/slide_body.py deck/01-cover.html deck/02-body.html'),
    (ALLOW, "pack_brief.py boot-sequence call",
     'python3 scripts/pack_brief.py'),
    (ALLOW, "plan_check.py",
     'python3 scripts/plan_check.py --deck-dir "/decks/acme"'),
    (ALLOW, "assemble_deck.py",
     'python3 scripts/assemble_deck.py --deck-dir "/decks/acme"'),

    # WP8: archiving stale/orphan slides is sanctioned, even though the archived
    # filename still matches the slide pattern (so it would otherwise trip the
    # cp/mv WRITE_PATTERNS rule below).
    (ALLOW, "mv a stale slide into _archive/",
     'mv "/decks/acme/08-orphan.html" "/decks/acme/_archive/2026-09-02/08-orphan.html"'),
    (ALLOW, "mv several stale slides into _archive/ in one loop",
     'for f in 08-orphan.html 09-old.html; do mv "/decks/acme/$f" '
     '"/decks/acme/_archive/2026-09-02/$f"; done'),
    (BLOCK, "mv onto a slide path that is NOT an archive destination",
     'mv "/decks/acme/draft.html" "/decks/acme/04-solution.html"'),
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
