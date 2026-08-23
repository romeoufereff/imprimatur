#!/usr/bin/env python3
"""
verify_pack.py — prove a pack is a design system rather than a palette.

Two halves:

1. CONTRACT (always runs, no dependencies). Does the pack contain what the contract requires —
   the files, the required manifest keys, roles that resolve to real tokens, gradients that
   match the config, a fixture at all?

2. INTEGRATION (runs when a deck orchestrator is installed). Point that install's own
   validate.py at the pack via DECK_DESIGN_SYSTEM and check the two outcomes that matter:

       the pack's seed templates PASS      — the pack can produce on-brand work
       off-brand-fixture.html FAILS        — the pack can REJECT off-brand work

   The second is the one people skip, and it is the one that matters. A pack whose fixture
   passes has rules that do not bite; every deck built on it will drift, and nothing will say so.

Usage:
    verify_pack.py --pack <pack dir> [--orchestrator <path to a skill root>] [--json]
"""
import argparse
import glob
import json
import os
import re
import subprocess
import sys

REQUIRED_FILES = ["design-system.json", "tailwind.config.js", "slide-base.html"]

# Where a pack may keep its off-brand fixture. The forge writes it at the pack root; a pack
# that keeps its eval material together puts it under evals/. Both are legitimate, so the
# check looks rather than dictates — the same reason the engine asks a pack what it provides
# instead of naming its files.
FIXTURE_NAMES = ["off-brand-fixture.html", "evals/off-brand-fixture.html",
                 "off-brand-regression-fixture.html", "evals/off-brand-regression-fixture.html"]


def find_fixture(pack):
    for rel in FIXTURE_NAMES:
        p = os.path.join(pack, rel)
        if os.path.isfile(p):
            return p
    return None
REQUIRED_KEYS = ["id", "name", "canvas", "tokens", "typography", "roles", "rules", "palette"]
CORE_ROLES = ["primary", "ink", "body", "muted", "rule", "surface"]
SUPPORTED_CONTRACT = 1


def find_validator(explicit=None):
    """Locate the engine's validate.py.

    Order matters. The engine that ships beside this script is the one the pack will
    actually face, so it wins outright. Only if that is missing do we look at what is
    installed — and there, an ambiguous match is refused rather than resolved by picking
    the shortest path, which used to bind the acceptance test to whichever unrelated deck
    pipeline happened to sort first and still print ACCEPTED.
    """
    if explicit:
        cand = os.path.join(os.path.expanduser(explicit), "scripts", "validate.py")
        return cand if os.path.isfile(cand) else None

    # 1. the sibling engine in this repository
    probe = os.path.dirname(os.path.abspath(__file__))
    while probe != os.path.dirname(probe):
        if os.path.isdir(os.path.join(probe, ".claude-plugin")):
            cand = os.path.join(probe, "scripts", "validate.py")
            if os.path.isfile(cand):
                return cand
            break
        probe = os.path.dirname(probe)

    # 2. anything installed, but only if the answer is unambiguous
    hits = []
    for root in (os.path.expanduser("~/.claude/skills"), os.path.expanduser("~/.claude/plugins")):
        hits += glob.glob(os.path.join(root, "**", "scripts", "validate.py"), recursive=True)
    hits = sorted({h for h in hits
                   if os.path.isfile(os.path.join(os.path.dirname(h), "ds_config.py"))})
    if len(hits) == 1:
        return hits[0]
    if len(hits) > 1:
        listing = "\n".join(f"    {h}" for h in hits)
        sys.exit(
            "Ambiguous engine: found more than one validate.py and cannot tell which one\n"
            "this pack will face in production. Verifying against the wrong engine would\n"
            "report a pass that means nothing, so pass --orchestrator explicitly.\n\n"
            f"{listing}"
        )
    return None



FONT_EXT = (".ttf", ".otf", ".woff", ".woff2", ".eot")

# Families a pack may name without declaring them: generics and the system stacks everyone
# falls back to. Anything else is a real typeface the pack is asking for, and it either
# matches the family the pack declares or it is a leftover.
SYSTEM_FAMILIES = {
    "sans-serif", "serif", "monospace", "cursive", "fantasy", "system-ui", "ui-sans-serif",
    "ui-serif", "ui-monospace", "-apple-system", "blinkmacsystemfont", "segoe ui", "roboto",
    "helvetica", "helvetica neue", "arial", "noto sans", "liberation sans", "sans", "inherit",
}


def check_fonts(pack, manifest):
    """Font hygiene, without knowing any brand's typeface.

    Three things rot silently when a pack changes its font, and all three shipped in a real
    migration before this check existed: a licensed font file left behind in a second
    directory nobody remembered; @font-face rules still pointing at files that were deleted;
    and markup still naming the old family. None of them fail validation — the slides look
    fine on the machine that still has the old font installed.

    So: every font file present must be referenced, every reference must resolve, and every
    family named must be either the one the pack declares or a system fallback.
    """
    problems, warnings = [], []
    pattern = ((manifest.get("typography") or {}).get("familyRequiredPattern") or "").strip()
    declared_re = re.compile(pattern, re.I) if pattern else None

    on_disk, referenced, families = set(), set(), {}
    for root, _dirs, files in os.walk(pack):
        for fn in files:
            full = os.path.join(root, fn)
            if fn.lower().endswith(FONT_EXT):
                on_disk.add(os.path.realpath(full))
                continue
            if not fn.lower().endswith((".html", ".css", ".js")):
                continue
            try:
                text = open(full, encoding="utf-8", errors="replace").read()
            except OSError:
                continue
            for block in re.findall(r"@font-face\s*\{(.*?)\}", text, re.S):
                fam = re.search(r"font-family:\s*['\"]?([^;'\"]+)", block)
                if fam:
                    families.setdefault(fam.group(1).strip(), set()).add(os.path.relpath(full, pack))
                for url in re.findall(r"url\(\s*['\"]?([^)'\"]+)", block):
                    if not url.lower().endswith(FONT_EXT):
                        continue
                    target = os.path.realpath(os.path.join(root, url))
                    referenced.add(target)
                    if not os.path.isfile(target):
                        problems.append(f"@font-face points at a missing file: {url} "
                                        f"(in {os.path.relpath(full, pack)})")
            # families named in a Tailwind fontFamily stack
            for stack in re.findall(r"fontFamily:\s*\{(.*?)\}", text, re.S):
                for fam in re.findall(r"['\"]([A-Za-z][A-Za-z0-9 .-]{1,40})['\"]", stack):
                    families.setdefault(fam.strip(), set()).add(os.path.relpath(full, pack))

    real_pack = os.path.realpath(pack)
    orphans = sorted(on_disk - referenced)
    for o in orphans:
        problems.append(f"font file present but never referenced: {os.path.relpath(o, real_pack)} "
                        f"— delete it, or declare it in an @font-face")

    if declared_re:
        for fam, where in sorted(families.items()):
            if fam.lower() in SYSTEM_FAMILIES or declared_re.search(fam):
                continue
            sample = sorted(where)[:2]
            problems.append(f"font family {fam!r} does not match the pack's declared family "
                            f"({pattern!r}) — seen in {', '.join(sample)}"
                            + (f" +{len(where)-2} more" if len(where) > 2 else ""))
    elif families:
        warnings.append("typography.familyRequiredPattern is empty, so no font family can be "
                        "checked against the pack's own declaration")

    return problems, warnings

def check_contract(pack):
    """Returns (problems, warnings, manifest)."""
    problems, warnings = [], []
    for name in REQUIRED_FILES:
        if not os.path.isfile(os.path.join(pack, name)):
            problems.append(f"missing {name}")
    if not find_fixture(pack):
        problems.append("no off-brand fixture found (looked for " + ", ".join(FIXTURE_NAMES) +
                        ") — without one, nothing proves this pack can reject anything")
    manifest_path = os.path.join(pack, "design-system.json")
    if not os.path.isfile(manifest_path):
        return problems, warnings, None
    try:
        with open(manifest_path, encoding="utf-8") as f:
            m = json.load(f)
    except json.JSONDecodeError as e:
        problems.append(f"design-system.json is not valid JSON: {e}")
        return problems, warnings, None

    for key in REQUIRED_KEYS:
        if key not in m:
            problems.append(f"design-system.json has no '{key}'")

    # The pack/engine interface version. Checked here as well as at load time because the
    # whole point is to catch the mismatch before a deck is built on it, not during.
    cv = m.get("contractVersion")
    if cv is None:
        warnings.append("no contractVersion — an engine cannot tell whether this pack still "
                        "matches it; re-forge to stamp one")
    else:
        try:
            major = int(str(cv).split(".")[0])
            if major != SUPPORTED_CONTRACT:
                problems.append(f"contractVersion {cv} but this forge writes "
                                f"{SUPPORTED_CONTRACT}.x — re-forge the pack")
        except (TypeError, ValueError):
            problems.append(f"contractVersion {cv!r} is not a version number")

    cfg = ""
    cfg_path = os.path.join(pack, "tailwind.config.js")
    if os.path.isfile(cfg_path):
        cfg = open(cfg_path, encoding="utf-8").read()

    prefix = (m.get("tokens") or {}).get("prefix", "")
    roles = m.get("roles") or {}
    for role in CORE_ROLES:
        tok = roles.get(role)
        if not tok:
            problems.append(f"role '{role}' is unfilled — engines asking for it get nothing")
        elif prefix and f"'{prefix}-{tok}'" not in cfg:
            problems.append(f"role '{role}' points at '{tok}', which is not a token in tailwind.config.js")
    viz = roles.get("viz")
    if not viz:
        warnings.append("no 'viz' role — charts will fall back to a library default palette")
    elif len(viz) < 3:
        warnings.append(f"'viz' has only {len(viz)} colour(s); charts with more series will repeat")

    typo = m.get("typography") or {}
    if not typo.get("allowedWeights"):
        warnings.append("typography.allowedWeights is empty — banOffScaleFontWeights cannot bite")
    if not typo.get("familyMarker"):
        warnings.append("typography.familyMarker is empty — requireFontMarker cannot bite")

    grads = (m.get("gradients") or {}).get("canonical") or []
    for g in grads:
        if g.replace(" ", "") not in cfg.replace(" ", ""):
            warnings.append(f"canonical gradient not present in tailwind.config.js: {g[:48]}…")

    rules = m.get("rules") or {}
    on = sum(1 for v in rules.values() if v)
    if on < 6:
        warnings.append(f"only {on} rule(s) enabled — a pack this permissive will not catch drift")
    fp, fw = check_fonts(pack, m)
    problems += fp
    warnings += fw

    return problems, warnings, m


def run_validator(validator, pack, targets):
    env = dict(os.environ, DECK_DESIGN_SYSTEM=os.path.abspath(pack))
    try:
        r = subprocess.run([sys.executable, validator, *targets], env=env,
                           capture_output=True, text=True, timeout=180)
        return r.returncode, (r.stdout or "") + (r.stderr or "")
    except (subprocess.SubprocessError, OSError) as e:
        return None, f"could not run validator: {e}"


def main():
    ap = argparse.ArgumentParser(description="Verify a design-system pack.")
    ap.add_argument("--pack", required=True)
    ap.add_argument("--orchestrator", default=None,
                    help="Skill root containing scripts/validate.py (auto-detected if omitted)")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--allow-unproven", action="store_true",
                    help="Exit 0 even when no engine was found to run the pack through. "
                         "Off by default: a contract-only pass says the pack is well formed, "
                         "not that it can reject anything.")
    args = ap.parse_args()

    pack = os.path.abspath(os.path.expanduser(args.pack))
    if not os.path.isdir(pack):
        sys.exit(f"error: no such pack: {pack}")

    problems, warnings, manifest = check_contract(pack)
    result = {"pack": pack, "contract_problems": problems, "contract_warnings": warnings,
              "integration": None}

    print(f"pack: {pack}")
    print(f"contract: {len(problems)} problem(s), {len(warnings)} warning(s)")
    for p in problems:
        print(f"  PROBLEM  {p}")
    for w in warnings:
        print(f"  warn     {w}")

    validator = find_validator(args.orchestrator)
    if not validator:
        print("integration: no deck orchestrator found — contract check only.")
        print("  The pack is structurally sound but UNPROVEN: nothing has confirmed it can")
        print("  reject off-brand work. Re-run this with an orchestrator installed before")
        print("  trusting it for client-facing decks.")
    else:
        print(f"integration: {validator}")
        templates = sorted(glob.glob(os.path.join(pack, "templates", "*.html")))
        fixture = find_fixture(pack)
        t_code, t_out = (None, "no templates to check")
        if templates:
            t_code, t_out = run_validator(validator, pack, templates)
        f_code, f_out = run_validator(validator, pack, [fixture]) if fixture else (None, "no fixture")
        t_pass = t_code == 0
        f_fails = f_code not in (0, None)
        result["integration"] = {"templates_pass": t_pass, "fixture_fails": f_fails,
                                 "templates_output": t_out[-2000:], "fixture_output": f_out[-2000:]}
        print(f"  templates PASS : {t_pass}" + ("" if t_pass else "   <-- the pack cannot produce clean work"))
        for line in [l for l in t_out.splitlines() if "FAIL" in l][:6]:
            print(f"      {line.strip()}")
        print(f"  fixture  FAILS : {f_fails}" + ("" if f_fails else "   <-- the pack cannot DEFEND itself"))
        tripped = [l.strip() for l in f_out.splitlines() if "FAIL" in l]
        for line in tripped[:8]:
            print(f"      {line}")
        if f_fails:
            print(f"      ({len(tripped)} rule(s) tripped by the fixture)")

    if args.json:
        print(json.dumps(result, indent=2))

    integration = result["integration"]
    ok = not problems and (integration is None or
                           (integration["templates_pass"] and integration["fixture_fails"]))
    # A contract-only run proves the pack is well formed. It proves nothing about whether the
    # pack can REJECT anything, which is the whole acceptance bar — so it must not exit 0 and
    # let a CI step wave the pack through. --allow-unproven is the deliberate opt-out.
    unproven = integration is None and not args.allow_unproven

    if not ok:
        print("\nNOT ACCEPTED. Fix the problems above; in particular, a fixture that passes means "
              "some rule is toothless — find out which before shipping the pack.")
    elif unproven:
        print("\nNOT ACCEPTED — UNPROVEN. The pack is structurally sound, but no engine was\n"
              "found to run its templates and off-brand fixture through, so nothing has\n"
              "confirmed it can reject off-brand work. Re-run with --orchestrator pointing at\n"
              "the engine, or pass --allow-unproven if you genuinely mean to accept it blind.")
    else:
        print("\nACCEPTED." + ("" if integration else " (contract only — integration unproven)"))
    sys.exit(0 if (ok and not unproven) else 1)


if __name__ == "__main__":
    main()
