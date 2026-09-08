#!/usr/bin/env python3
"""Run the eval suite's scripted graders.

`evals/evals.json` has defined nine evals and specified how to grade them —
"qa.py for designer outputs, seeded-violations.json recall/precision for the audit
eval, field-presence checks for narrative briefs" — since it was written. Nothing
computed any of it. The suite was a specification a human executed by hand, which
in practice meant it was not executed.

This runs the parts that can be graded deterministically, and sets up the parts
that need a model rather than pretending it can score them.

    run_evals.py audit                        # fully scripted; the fixture-rot check
    run_evals.py designer   <dir-of-slides>   # qa.py + per-eval assertions
    run_evals.py narrative  <briefs.md>       # SLIDE BRIEF field presence
    run_evals.py setup <id> <dir>             # stage an eval's working folder

Exit 0 when every scripted assertion passes.
"""

import argparse
import glob
import json
import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN = os.path.dirname(HERE)
EVALS = os.path.join(PLUGIN, "skills", "imprimatur", "evals")
sys.path.insert(0, HERE)
from ds_config import load  # noqa: E402

GREEN, RED, DIM, OFF = "\033[32m", "\033[31m", "\033[2m", "\033[0m"
if not sys.stdout.isatty():
    GREEN = RED = DIM = OFF = ""


def _run(script, *args):
    r = subprocess.run([sys.executable, os.path.join(HERE, script), *args],
                       capture_output=True, text=True)
    return r.returncode, r.stdout + r.stderr


def _fails(output):
    return [ln.strip()[6:].strip() for ln in output.splitlines()
            if ln.strip().startswith("FAIL")]


# ── audit: the one the eval contract names and nothing ever ran ──────────
def grade_audit():
    """Recall and precision against the pack's seeded-violation fixtures.

    Two things are being checked, and the second is the one that rots. Recall: does
    the script suite still flag every seed it is supposed to? Precision: does it flag
    anything *else*? A fixture that grows extra failures stops being ground truth —
    that already happened once, when stale font paths and a dropped data-template
    added six phantom failures and the eval had to be repaired rather than trusted.
    """
    ds = load()
    truth_path = os.path.join(ds.root, "evals", "stage-brand-audit", "seeded-violations.json")
    if not os.path.isfile(truth_path):
        print(f"{DIM}pack ships no seeded-violation fixtures — skipping{OFF}")
        return 0

    truth = json.load(open(truth_path, encoding="utf-8"))
    expected = truth.get("expected_script_output", {})
    ok = True

    print(f"audit fixtures  [{ds.name}]\n")
    total_seeds = script_detectable = flagged = false_pos = 0

    for fname, spec in truth["files"].items():
        path = os.path.join(ds.root, "evals", "stage-brand-audit", fname)
        if not os.path.isfile(path):
            print(f"  {RED}✗{OFF} {fname}: fixture missing")
            ok = False
            continue

        _, vout = _run("validate.py", path)
        _, cout = _run("check_contrast.py", path)
        v_fails, c_fails = _fails(vout), _fails(cout)

        want = expected.get(fname, {})
        v_want, c_want = want.get("validate.py"), want.get("check_contrast.py")

        seeds = spec["violations"]
        total_seeds += len(seeds)
        # Read the explicit flag, not the prose: one seed's `detectable_by` names
        # validate.py in order to say it does not catch it.
        scripted = [s for s in seeds if s.get("scripted") is True] or \
                   [s for s in seeds if s.get("scripted") is None
                    and ("validate.py" in s["detectable_by"]
                         or "check_contrast.py" in s["detectable_by"])]
        script_detectable += len(scripted)
        flagged += len(v_fails) + len(c_fails)

        print(f"  {fname}")
        print(f"    seeds: {len(seeds)}  ({len(scripted)} script-detectable, "
              f"{len(seeds) - len(scripted)} judgment-only)")

        for label, got, want_n in (("validate.py", len(v_fails), v_want),
                                   ("check_contrast.py", len(c_fails), c_want)):
            if want_n is None:
                print(f"    {DIM}{label}: {got} (no expectation recorded){OFF}")
                continue
            mark = f"{GREEN}✓{OFF}" if got == want_n else f"{RED}✗{OFF}"
            note = "" if got == want_n else \
                f"  {RED}— fixture rot: any failure not in the ground truth is a false positive{OFF}"
            print(f"    {mark} {label}: {got} failure(s), expected {want_n}{note}")
            if got != want_n:
                ok = False
                false_pos += max(0, got - want_n)
                for f in (v_fails if label == "validate.py" else c_fails):
                    print(f"        {f[:110]}")
        print()

    judgment = total_seeds - script_detectable
    print(f"  recall (scripted)  : {script_detectable}/{script_detectable} of the "
          f"script-detectable seeds" if ok else
          f"  recall (scripted)  : MISMATCH — see above")
    print(f"  precision          : {'no false positives' if not false_pos else f'{false_pos} false positive(s)'}")
    print(f"  {DIM}{judgment} seed(s) are judgment-only and are the brand-audit agent's job, "
          f"not a script's{OFF}")
    print(f"\n{GREEN if ok else RED}audit eval: {'PASS' if ok else 'FAIL'}{OFF}")
    return 0 if ok else 1


# ── designer: grade produced slides ──────────────────────────────────────
def grade_designer(target):
    slides = sorted(glob.glob(os.path.join(target, "[0-9]*.html"))) \
        if os.path.isdir(target) else [target]
    if not slides:
        print(f"{RED}no NN-*.html slides in {target}{OFF}")
        return 1

    print(f"designer outputs ({len(slides)} slide(s))\n")
    ok = True
    for s in slides:
        name = os.path.basename(s)
        rc, out = _run("qa.py", s)
        html = open(s, encoding="utf-8").read()

        checks = [
            ("mechanical QA (validate + contrast + overflow + paint)", rc == 0),
            ("carries data-template", bool(re.search(r'data-template="[^"]+"', html))),
            ("self-contained (no external css/js beyond CDNs)",
             not re.search(r'<link[^>]+href="(?!https?://)[^"]+\.css"', html)),
            ("no raster referenced by path (data: URIs only)",
             not re.search(r'<img[^>]+src="(?!data:)[^"]+"', html)),
        ]
        print(f"  {name}")
        for label, passed in checks:
            print(f"    {GREEN + '✓' + OFF if passed else RED + '✗' + OFF} {label}")
            ok &= passed
        if rc != 0:
            for f in _fails(out)[:6]:
                print(f"        {f[:110]}")
        print()
    print(f"{GREEN if ok else RED}designer eval: {'PASS' if ok else 'FAIL'}{OFF}")
    return 0 if ok else 1


# ── narrative: SLIDE BRIEF field presence ────────────────────────────────
REQUIRED_FIELDS = ("Message:", "Structure:", "Visual:", "Key data:",
                   "Emphasis:", "Audience:", "Density:")


def grade_narrative(path):
    text = open(path, encoding="utf-8").read()
    briefs = re.split(r'^SLIDE \d+:', text, flags=re.M)[1:]
    print(f"narrative briefs ({len(briefs)} found)\n")
    if not briefs:
        print(f"{RED}no 'SLIDE N:' blocks — the designer cannot consume this{OFF}")
        return 1

    ok = True
    for i, b in enumerate(briefs, 1):
        missing = [f for f in REQUIRED_FIELDS if f not in b]
        mark = f"{GREEN}✓{OFF}" if not missing else f"{RED}✗{OFF}"
        print(f"  {mark} slide {i}" + (f"  missing: {', '.join(missing)}" if missing else ""))
        ok &= not missing

    # The variance dial's whole purpose: enough slides carrying a real visual.
    visuals = [b for b in briefs if re.search(r'Visual:\s*(?!none)\S', b)]
    print(f"\n  visual slides: {len(visuals)}/{len(briefs)}"
          f"  {DIM}(taste-dials.md: low >=1, medium >=2, high >=3 incl. >=1 bespoke){OFF}")
    if len(visuals) == 0:
        print(f"  {RED}✗ an all-cards deck is the wall-of-cards tell{OFF}")
        ok = False
    print(f"\n{GREEN if ok else RED}narrative eval: {'PASS' if ok else 'FAIL'}{OFF}")
    return 0 if ok else 1


# ── setup: stage an eval's isolated working folder ───────────────────────
def setup(eval_id, dest):
    data = json.load(open(os.path.join(EVALS, "evals.json"), encoding="utf-8"))
    ev = next((e for e in data["evals"] if str(e["id"]) == str(eval_id)), None)
    if not ev:
        print(f"no eval with id {eval_id}. Available: "
              f"{', '.join(str(e['id']) for e in data['evals'])}")
        return 1
    os.makedirs(dest, exist_ok=True)
    for rel in ev.get("files") or []:
        src = os.path.join(EVALS, rel)
        if not os.path.isfile(src):
            print(f"  {RED}missing fixture: {rel}{OFF}")
            return 1
        shutil.copy2(src, os.path.join(dest, os.path.basename(rel)))
        print(f"  copied {os.path.basename(rel)}")
    print(f"\neval {ev['id']} — {ev['name']}\n  {dest}\n")
    print("PROMPT:")
    print("  " + (ev.get("prompt", "") or "").replace("\n", "\n  "))
    print("\nEXPECTED:")
    print("  " + (ev.get("expected_output", "") or "").replace("\n", "\n  "))
    print(f"\nGrade with:  run_evals.py designer {dest}")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.strip().split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("audit", help="Scripted recall/precision on the pack's seeded fixtures")
    d = sub.add_parser("designer", help="Grade produced slides"); d.add_argument("target")
    n = sub.add_parser("narrative", help="Grade produced SLIDE BRIEFs"); n.add_argument("path")
    s = sub.add_parser("setup", help="Stage an eval's working folder")
    s.add_argument("eval_id"); s.add_argument("dest")
    a = ap.parse_args()

    if a.cmd == "audit":
        return grade_audit()
    if a.cmd == "designer":
        return grade_designer(a.target)
    if a.cmd == "narrative":
        return grade_narrative(a.path)
    return setup(a.eval_id, a.dest)


if __name__ == "__main__":
    sys.exit(main())
