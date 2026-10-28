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
    layout after content edits, which only a layout engine can judge). Since 1.6.1
    every root <svg> is a collision participant (text over a logo, an icon or a
    diagram), and `svg_sizing` fails an SVG laid out below 90% of its written height
    or SVG text rendered below the pack's font floor (check_overflow.py).
  - co-brand lockup (check_cobrand.py): every file, when deck-state.json declares
    `"cobrand"` — both marks, client left, gap, size, shared centre, bottom offset,
    white-on-white; plus a cross-slide bottom-offset row computed after the cache.
  - logo geometry (check_logo.py): every file, when the pack declares a `logo`
    spec — corner, height, fill. Was brand-audit's most expensive judgment row.
  - gradient contrast (check_gradient.py): every file — pixel-sampled worst-case
    WCAG ratio for text over gradients/images, the cases check_contrast defers.
    Reported in the JSON (`gradient_contrast`, `gradient_contrast_fails`) and,
    since 2026-10-06, COUNTED into the slide verdict exactly like computed
    contrast: gates on a whole-deck run (or --contrast), reported-only in a
    --files chunk run. Before that a slide could carry `fail: true` rows and
    still report `failures: 0, pass: true` (a client deck, slide 03).
  - paint (silent-paint-reference check): only files whose `deck-state.json`
    entry has visual in {chart, pipeline, bespoke}; unconditionally when there is
    no deck-state.json to say otherwise.
  - contrast: computed for every file; gates pass/fail only on a whole-deck run
    (`qa.py --deck-dir` without `--files`) or with --contrast.
  - diagram (check_diagram.py): every file — text leaving its box (a box = a fill or
    borders on 3+ sides), connectors visibly running through text, arrow tips buried in
    or floating short of their node, connector stroke contrast < 3:1, accent stripes
    (left bars, top-stripe cards), cards in one row that end at different heights; plus
    the slide's diagram vocabulary (panel styles, tinted panels,
    connector colours, uses of the decision colour), which gates only under the pack's
    rules.enforceDiagramVocabulary. Added 2026-10-26 after a restyle review where each
    of these hid a real defect from every other check.
  - motion (check_motion.py): only files carrying the deck-motion block
    (`id="imprimatur-motion"`, injected by choreograph.py at §7b). Runs LAST on the
    page: screenshots the static slide, plays the timeline to its end, and fails
    unless the two are pixel-identical (pack `motion.qa.maxMae`), every selector
    resolves, nothing in a never-animate region moves, and the spec's body_hash is
    current. Un-choreographed decks pay nothing.

THE FREEZE (2026-10-26): before anything is measured, CSS transitions and animations are
jumped to their end state by a stylesheet whose selector carries four ids, so it beats a
slide's own `!important` transition rules (a `.slide.active .reveal{transition:…!important}`
outranks `html body *`, and the page was measured mid-fade), and running CSS animations
are finished. The motion check is unaffected: deck-motion tweens inline styles through GSAP
on requestAnimationFrame, which no CSS duration touches.

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
import check_cobrand  # noqa: E402
import cobrand  # noqa: E402
import check_gradient  # noqa: E402
import check_motion  # noqa: E402
import check_diagram  # noqa: E402

PAINT_VISUALS = {"chart", "pipeline", "bespoke"}

# Transitions and animations jump to their end state. Four ids in :not() lift the selector
# above any class-based !important rule a slide brings; durations of 0 (not `none`) keep
# each animation's end state instead of dropping back to the un-animated style.
FREEZE_CSS = ("html body *:not(#_qf0#_qf1#_qf2#_qf3), html body *:not(#_qf0#_qf1#_qf2#_qf3)::before, "
              "html body *:not(#_qf0#_qf1#_qf2#_qf3)::after {transition-duration:0s!important;"
              "transition-delay:0s!important;animation-duration:0s!important;"
              "animation-delay:0s!important;animation-iteration-count:1!important}")
FREEZE_JS = """(css) => new Promise(done => {
  const st = document.createElement('style'); st.id = 'imprimatur-qa-freeze'; st.textContent = css;
  document.head.appendChild(st);
  for (const a of document.getAnimations()) {
    if (a instanceof CSSAnimation || a instanceof CSSTransition) { try { a.finish(); } catch (e) {} }
  }
  requestAnimationFrame(() => requestAnimationFrame(() => done(true)));
})"""

CACHE_NAME = ".qa-cache.json"
CHECKS_VERSION = "2026-10-26.1"  # bump whenever a check's logic changes — invalidates every cache


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

def _check_one(page, path, ds, visuals, deck_dir, count_contrast, do_collisions, tol, cb=None):
    name = os.path.basename(path)
    page.goto("file://" + os.path.abspath(path), wait_until="networkidle")
    page.evaluate("document.fonts.ready || Promise.resolve()")
    page.wait_for_timeout(400)  # let the Tailwind CDN inject styles
    page.evaluate(FREEZE_JS, FREEZE_CSS)

    entry = {"file": name, "overflow": [], "collisions": [], "svg_sizing": [], "diagram": [],
             "vocabulary": None, "paint": [], "logo": None,
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
        cols, err = check_overflow.analyze_collisions_page(page, tol, ds.get("logo.selector", ""))
        if cols is None:
            entry["errors"].append(err)
        else:
            entry["collisions"] = cols
            failures += len(cols)

    sizing, err = check_overflow.analyze_svg_sizing_page(page, ds)
    if sizing is None:
        entry["errors"].append(err)
    else:
        entry["svg_sizing"] = sizing
        failures += len(sizing)

    diag, voc, err = check_diagram.analyze_page(page, ds)
    if diag is None:
        entry["errors"].append(err)
    else:
        entry["diagram"] = diag
        entry["vocabulary"] = voc
        failures += len(diag)

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
    entry["gradient_contrast_fails"] = sum(1 for g in grad if g.get("fail"))
    # Every sampled FAIL counts toward the slide verdict under the same scoping as
    # computed contrast (count_contrast: the whole-deck run, or --contrast). Until
    # 2026-10-06 only the flat-background SVG rows below were counted and the rest
    # were "brand-audit's evidence", which let a slide report pass: true while its
    # gradient_contrast list carried fail: true rows.
    if count_contrast:
        failures += entry["gradient_contrast_fails"]
    # SVG text over a FLAT background is measured exactly by the sample (one colour
    # under the glyphs) — that is a plain contrast failure, so it is ALSO listed in
    # contrast_fails for the report. Counted once, above; not again here.
    for g in grad:
        if g.get("svg") and g.get("uniform") and g.get("fail"):
            entry["contrast_fails"].append(
                {"tag": "svg-text", "text": g["text"], "ratio": g["ratio_worst"],
                 "need": g["need"], "fontSize": g.get("fontSize"),
                 "fontWeight": g.get("fontWeight")})

    # logo geometry — when the pack declares a spec
    try:
        logo_findings, logo_info = check_logo.analyze_page(page, ds, name)
    except Exception as e:
        logo_findings, logo_info = None, {"error": str(e)}
    entry["logo"] = logo_findings
    entry["logo_info"] = logo_info
    if logo_findings:
        failures += len(logo_findings)

    # co-brand lockup — when deck-state.json declares one (cobrand.py)
    if cb:
        try:
            cb_findings, cb_info = check_cobrand.analyze_page(page, ds, cb)
        except Exception as e:
            cb_findings, cb_info = [f"cobrand check error: {e}"], {}
        entry["cobrand"] = cb_findings
        entry["cobrand_info"] = cb_info
        if cb_findings:
            failures += len(cb_findings)

    visual = visuals.get(name)
    run_paint = (visual in PAINT_VISUALS) or (not deck_dir) or (name not in visuals)
    if run_paint:
        pviol, err = check_paint.analyze_paint_page(page)
        if pviol is None:
            entry["errors"].append(err)
        else:
            entry["paint"] = pviol
            failures += len(pviol)

    # deck-motion — last, because it drives the page's timeline (and restores the DOM)
    entry["motion"] = None
    entry["motion_fails"] = []
    if check_motion.applies(path):
        try:
            m_findings, m_info = check_motion.analyze_page(page, ds, path)
        except Exception as e:  # never let the motion gate take the whole run down
            m_findings, m_info = [f"motion check error: {e}"], {}
        entry["motion"] = m_info
        entry["motion_fails"] = m_findings or []
        failures += len(entry["motion_fails"])

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
    try:
        cb, cb_error = cobrand.load_decl(deck_dir), None
    except cobrand.CobrandError as e:
        cb, cb_error = None, str(e)
    cb_key = ""
    if cb:
        # the declaration and the client image both change what "pass" means for a slide
        logo_sha = _sha(cb["abs"])[:10] if os.path.isfile(cb["abs"]) else "missing"
        cb_key = "|cb" + hashlib.sha256(jsonlib.dumps(
            {k: v for k, v in cb.items() if k != "abs"}, sort_keys=True).encode()).hexdigest()[:10] \
            + logo_sha
    cache = _load_cache(deck_dir) if use_cache else {}
    results, total_failures = {}, 0
    pending = []
    for path in paths:
        name = os.path.basename(path)
        visual = visuals.get(name)
        run_paint = (visual in PAINT_VISUALS) or (not deck_dir) or (name not in visuals)
        key = f"{_sha(path)}|{fp}|c{int(count_contrast)}|p{int(run_paint)}|v{visual}{cb_key}"
        # the motion runtime lives beside the deck, not in the pack: a new motion.js must re-check
        rt = os.path.join(os.path.dirname(os.path.abspath(path)), "motion", "motion.js")
        if os.path.isfile(rt):
            key += f"|m{_sha(rt)[:10]}"
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
                                   do_collisions, tol, cb)
                results[os.path.basename(path)] = entry
                total_failures += entry["failures"]
                if use_cache and not entry["errors"]:
                    cache[key] = {k: v for k, v in entry.items() if k != "cached"}
            browser.close()
        if use_cache:
            _save_cache(deck_dir, cache)

    # Deck-level co-brand rows depend on the OTHER slides, so they are computed after the
    # cache and never stored in it (new keys on the entry, never mutated cached lists).
    if cb_error:
        for name, entry in results.items():
            entry["cobrand_deck"] = [f"cobrand: {cb_error}"]
            entry["failures"] = entry.get("failures", 0) + 1
            entry["pass"] = False
            total_failures += 1
    elif cb:
        for name, extra in check_cobrand.bottom_consistency(results).items():
            entry = results[name]
            entry["cobrand_deck"] = extra
            entry["failures"] = entry.get("failures", 0) + len(extra)
            entry["pass"] = False
            total_failures += len(extra)
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
        if entry.get("svg_sizing"):
            lines += check_overflow.format_svg_sizing_report(name, entry["svg_sizing"])[1:]
        if entry.get("diagram"):
            lines += check_diagram.format_report(name, entry["diagram"])[1:]
        if entry["paint"]:
            lines += check_paint.format_paint_report(name, entry["paint"])[1:]
        for x in entry.get("logo") or []:
            lines.append(f"  FAIL  {x}")
        for x in (entry.get("cobrand") or []) + (entry.get("cobrand_deck") or []):
            lines.append(f"  FAIL  {x}")
        for x in entry.get("motion_fails") or []:
            lines.append(f"  FAIL  motion: {x}")
        if verbose and entry.get("motion") and entry["motion"].get("mae") is not None:
            mi = entry["motion"]
            lines.append(f"  note  motion end-state MAE {mi['mae']} · {mi.get('beats')} beats · {mi.get('total_ms')} ms"
                         f"{' · ' + str(mi.get('steps')) + ' steps' if mi.get('steps') else ''}")
        want_contrast = entry.get("contrast_counted", True) if show_contrast is None else show_contrast
        if want_contrast:
            for c in entry["contrast_fails"][:10]:
                lines.append(f"  FAIL  <{c['tag']}> {c['ratio']}:1 < {c['need']}:1 — {c['text']!r}")
            counted = entry.get("contrast_counted", True)
            for g in entry.get("gradient_contrast") or []:
                if g.get("fail"):
                    lines.append(f"  {'FAIL' if counted else 'warn'}  <{g['tag']}> over gradient/image: "
                                 f"sampled worst {g['ratio_worst']}:1 < {g['need']}:1 — {g['text']!r}"
                                 + ("" if counted else " (counts on the whole-deck run)"))
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
            print(f"All {n} file(s) pass overflow/collision/svg-sizing/diagram/paint/logo/contrast checks ({cached} from cache).")

    sys.exit(1 if total_failures else 0)


if __name__ == "__main__":
    main()
