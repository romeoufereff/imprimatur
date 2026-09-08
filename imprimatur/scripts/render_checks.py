#!/usr/bin/env python3
"""
Batch render-level QA — one Chromium launch for N files, with a content-hash cache.

Before this script, `qa.py` ran check_contrast.py, check_overflow.py and
check_paint.py as three separate subprocesses, each opening its OWN headless
Chromium instance and reloading every file again — 3 browser launches x N page
loads per invocation, run on every single Write/Edit via the PostToolUse hook.

This script loads each file ONCE in a single shared browser/page and runs
whichever checks apply to that file:
  - overflow + collisions: EVERY file (the one thing byte-copying cannot fix —
    layout after content edits, which only a layout engine can judge).
  - logo geometry (check_logo.py): every file, when the pack declares a `logo`
    spec — corner, height, fill. Was brand-audit's most expensive judgment row.
  - gradient contrast (check_gradient.py): every file — pixel-sampled worst-case
    WCAG ratio for text over gradients/images, the cases check_contrast defers.
    Reported in the JSON (`gradient_contrast`, `gradient_contrast_fails`) for
    brand-audit; never gates a run on its own — it is a sample, not a proof.
  - paint (silent-paint-reference check): only files whose `deck-state.json`
    entry has visual in {chart, pipeline, bespoke}; unconditionally when there is
    no deck-state.json to say otherwise.
  - contrast: computed for every file; gates pass/fail only on a whole-deck run
    (`qa.py --deck-dir` without `--files`) or with --contrast.

THE CACHE (2026-09-07 audit): the same unchanged slide was rendered four times
per deck — the designer's batch, the stop gate, the orchestrator's whole-deck
run, brand-audit's whole-deck run. Results are now memoised in
`<deck>/.qa-cache.json`, keyed by the file's content hash + a pack fingerprint
(design-system.json, tailwind config, slide base, template listing) + the engine
version + the check scope. A file that has not changed since it last passed
costs no page load; a browser launches only if at least one file is uncached.
`--no-cache` forces a full run; a changed pack or engine invalidates everything.

Usage:
    render_checks.py FILE... [--deck-dir D] [--json] [--verbose] [--contrast] [--no-cache]

Exit code 0 = clean; 1 = at least one overflow/collision/paint/logo FAIL, or a
hard (or sampled) contrast FAIL when contrast gates.
"""
import argparse
import hashlib
import json as jsonlib
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ds_config import load  # noqa: E402
import check_contrast  # noqa: E402
import check_overflow  # noqa: E402
import check_paint  # noqa: E402
import check_logo  # noqa: E402
import check_gradient  # noqa: E402

PAINT_VISUALS = {"chart", "pipeline", "bespoke"}
CACHE_NAME = ".qa-cache.json"
CHECKS_VERSION = "2026-09-07.1"  # bump whenever a check's logic changes — invalidates every cache


def load_visuals(deck_dir):
    """{filename: visual} from <deck_dir>/deck-state.json, or {} if absent/unreadable."""
    if not deck_dir:
        return {}
    path = os.path.join(deck_dir, "deck-state.json")
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            data = jsonlib.load(f)
    except Exception:
        return {}
    out = {}
    for s in data.get("slides", []) or []:
        fn = s.get("file")
        if fn:
            out[fn] = s.get("visual")
    return out


# ── cache ────────────────────────────────────────────────────────────────────

def _sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def pack_fingerprint(ds):
    """Anything that changes what 'pass' means: the manifest, the token config, the
    slide base, the template set (name+size+mtime is enough — templates are copied,
    not rendered here), and the engine version."""
    h = hashlib.sha256()
    for rel in ("design-system.json", ds.get("tokens.configFile", "tailwind.config.js"),
                ds.get("tokens.baseFile", "slide-base.html")):
        p = os.path.join(ds.root, rel)
        if os.path.isfile(p):
            h.update(_sha(p).encode())
    try:
        for name in sorted(os.listdir(ds.templates_dir)):
            p = os.path.join(ds.templates_dir, name)
            if name.endswith(".html"):
                st = os.stat(p)
                h.update(f"{name}:{st.st_size}:{int(st.st_mtime)}".encode())
    except OSError:
        pass
    manifest = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            ".claude-plugin", "plugin.json")
    try:
        h.update(open(manifest, "rb").read())
    except OSError:
        pass
    h.update(CHECKS_VERSION.encode())
    return h.hexdigest()[:16]


def _load_cache(deck_dir):
    if not deck_dir:
        return {}
    p = os.path.join(deck_dir, CACHE_NAME)
    try:
        with open(p, encoding="utf-8") as f:
            return jsonlib.load(f)
    except Exception:
        return {}


def _save_cache(deck_dir, cache):
    if not deck_dir:
        return
    p = os.path.join(deck_dir, CACHE_NAME)
    try:
        # keep the file bounded: drop entries for hashes no longer on disk is overkill;
        # simply cap the number of entries
        if len(cache) > 400:
            for k in list(cache)[: len(cache) - 400]:
                del cache[k]
        with open(p, "w", encoding="utf-8") as f:
            jsonlib.dump(cache, f, indent=0)
    except OSError:
        pass


# ── the checks ───────────────────────────────────────────────────────────────

def _check_one(page, path, ds, visuals, deck_dir, count_contrast, do_collisions, tol):
    name = os.path.basename(path)
    page.goto("file://" + os.path.abspath(path), wait_until="networkidle")
    page.evaluate("document.fonts.ready || Promise.resolve()")
    page.wait_for_timeout(400)  # let the Tailwind CDN inject styles

    entry = {"file": name, "overflow": [], "collisions": [], "paint": [], "logo": None,
             "logo_info": None, "gradient_contrast": [], "contrast_fails": [],
             "contrast_manual": 0, "errors": [], "cached": False}
    failures = 0

    viol, err = check_overflow.analyze_overflow_page(page, ds, name)
    if viol is None:
        entry["errors"].append(err)
    else:
        entry["overflow"] = viol
        failures += len(viol)

    if do_collisions:
        cols, err = check_overflow.analyze_collisions_page(page, tol)
        if cols is None:
            entry["errors"].append(err)
        else:
            entry["collisions"] = cols
            failures += len(cols)

    fails, manual = check_contrast.analyze_page(page)
    if fails is None:
        entry["errors"].append(manual)
    else:
        entry["contrast_fails"] = [
            {"tag": it["tag"], "text": it["text"], "ratio": round(ratio, 2), "need": need,
             "fontSize": it.get("fontSize"), "fontWeight": it.get("fontWeight")}
            for it, ratio, need in fails]
        entry["contrast_manual"] = manual
        if count_contrast:
            failures += len(fails)

    # sampled contrast over gradients/images — the deferred cases, now measured
    try:
        grad = check_gradient.analyze_page(page)
    except Exception as e:  # never let the sampler take the whole run down
        grad = [{"unsampled": True, "reason": f"sampler error: {e}", "fail": False}]
    entry["gradient_contrast"] = grad
    # Sampled ratios are reported, never gated: they are brand-audit's evidence for
    # the row it used to render slides for, not a reason to bounce a designer chunk.
    entry["gradient_contrast_fails"] = sum(1 for g in grad if g.get("fail"))

    # logo geometry — when the pack declares a spec
    try:
        logo_findings, logo_info = check_logo.analyze_page(page, ds, name)
    except Exception as e:
        logo_findings, logo_info = None, {"error": str(e)}
    entry["logo"] = logo_findings
    entry["logo_info"] = logo_info
    if logo_findings:
        failures += len(logo_findings)

    visual = visuals.get(name)
    run_paint = (visual in PAINT_VISUALS) or (not deck_dir) or (name not in visuals)
    if run_paint:
        pviol, err = check_paint.analyze_paint_page(page)
        if pviol is None:
            entry["errors"].append(err)
        else:
            entry["paint"] = pviol
            failures += len(pviol)

    entry["visual"] = visual
    entry["contrast_counted"] = count_contrast
    entry["failures"] = failures
    entry["pass"] = failures == 0 and not entry["errors"]
    if entry["errors"]:
        failures = max(failures, 1)
        entry["failures"] = failures
    return entry


def run(paths, ds, deck_dir=None, verbose=False, count_contrast=True, use_cache=True):
    """Returns (per_file_results: dict, total_failures: int). Entries are plain
    JSON-safe dicts (so they can be cached and printed alike)."""
    visuals = load_visuals(deck_dir)
    do_collisions = ds.rule("banElementCollisions")
    tol = float(ds.get("collisionTolerancePx", 4))
    cw, ch = ds.canvas

    fp = pack_fingerprint(ds)
    cache = _load_cache(deck_dir) if use_cache else {}
    results, total_failures = {}, 0
    pending = []
    for path in paths:
        name = os.path.basename(path)
        visual = visuals.get(name)
        run_paint = (visual in PAINT_VISUALS) or (not deck_dir) or (name not in visuals)
        key = f"{_sha(path)}|{fp}|c{int(count_contrast)}|p{int(run_paint)}|v{visual}"
        hit = cache.get(key) if use_cache else None
        if hit:
            entry = dict(hit)
            entry["cached"] = True
            results[name] = entry
            total_failures += entry.get("failures", 0)
        else:
            pending.append((path, key))
            results[name] = None  # placeholder keeps input order

    if pending:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": cw, "height": ch})
            for path, key in pending:
                entry = _check_one(page, path, ds, visuals, deck_dir, count_contrast,
                                   do_collisions, tol)
                results[os.path.basename(path)] = entry
                total_failures += entry["failures"]
                if use_cache and not entry["errors"]:
                    cache[key] = {k: v for k, v in entry.items() if k != "cached"}
            browser.close()
        if use_cache:
            _save_cache(deck_dir, cache)
    return results, total_failures


def print_report(results, verbose=False, show_contrast=None):
    for name, entry in results.items():
        lines = []
        for err in entry["errors"]:
            lines.append(f"  FAIL  {err}")
        if entry["overflow"]:
            lines += check_overflow.format_overflow_report(name, entry["overflow"])[1:]
        if entry.get("collisions"):
            lines += check_overflow.format_collisions_report(name, entry["collisions"])[1:]
        if entry["paint"]:
            lines += check_paint.format_paint_report(name, entry["paint"])[1:]
        for x in entry.get("logo") or []:
            lines.append(f"  FAIL  {x}")
        want_contrast = entry.get("contrast_counted", True) if show_contrast is None else show_contrast
        if want_contrast:
            for c in entry["contrast_fails"][:10]:
                lines.append(f"  FAIL  <{c['tag']}> {c['ratio']}:1 < {c['need']}:1 — {c['text']!r}")
            for g in entry.get("gradient_contrast") or []:
                if g.get("fail"):
                    lines.append(f"  warn  <{g['tag']}> over gradient/image: sampled worst {g['ratio_worst']}:1 "
                                 f"< {g['need']}:1 — {g['text']!r} (brand-audit judges; not gated)")
            if verbose:
                unsampled = [g for g in entry.get("gradient_contrast") or [] if g.get("unsampled")]
                if unsampled:
                    lines.append(f"  note  {len(unsampled)} element(s) over gradient/image not sampled "
                                 f"({unsampled[0].get('reason')}) — verify manually")
        if lines:
            print(name + ("  (cached)" if entry.get("cached") else ""))
            for line in lines:
                print(line)


def to_jsonable(results):
    """Entries are already JSON-safe; kept for callers written against the old API."""
    return {name: dict(entry) for name, entry in results.items()}


def main():
    ap = argparse.ArgumentParser(description=__doc__.strip().split("\n")[0])
    ap.add_argument("files", nargs="+", metavar="FILE")
    ap.add_argument("--deck-dir", default=None,
                    help="Deck folder holding deck-state.json (scopes the paint check; hosts the cache)")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--verbose", action="store_true", help="Include 'verify manually' notes")
    ap.add_argument("--contrast", action="store_true",
                    help="Count contrast hard-FAILs (computed and sampled) toward pass/fail")
    ap.add_argument("--no-cache", action="store_true", help="Ignore and do not write .qa-cache.json")
    args = ap.parse_args()

    missing = [f for f in args.files if not os.path.isfile(f)]
    if missing:
        for m in missing:
            print(f"error: no such file: {m}", file=sys.stderr)
        sys.exit(2)

    ds = load()
    deck_dir = args.deck_dir or (os.path.dirname(os.path.abspath(args.files[0])) if args.files else None)
    results, total_failures = run(args.files, ds, deck_dir=deck_dir, verbose=args.verbose,
                                  count_contrast=args.contrast, use_cache=not args.no_cache)

    if args.json:
        print(jsonlib.dumps({"files": to_jsonable(results),
                             "total_failures": total_failures}, indent=2, ensure_ascii=False))
    else:
        print_report(results, verbose=args.verbose)
        n = len(args.files)
        cached = sum(1 for e in results.values() if e.get("cached"))
        if total_failures:
            print(f"\n{total_failures} render-check failure(s) across {n} file(s) ({cached} from cache).")
        else:
            print(f"All {n} file(s) pass overflow/collision/paint/logo/contrast checks ({cached} from cache).")

    sys.exit(1 if total_failures else 0)


if __name__ == "__main__":
    main()
