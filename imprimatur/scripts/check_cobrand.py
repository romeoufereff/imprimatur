#!/usr/bin/env python3
"""
Co-brand lockup check (render-level) — design-system agnostic.

Runs only when the deck declares `"cobrand"` in deck-state.json (see cobrand.py), inside
render_checks.py's single page load, so qa.py, the designer stop gate and brand-audit all
see it. Until 1.6.1 a lockup was exempted from the logo check by `data-logo="ok"` and
never measured; this measures it and FAILs:

  per slide (every slide whose template carries a logo):
    · both marks present — the client mark (`[data-cobrand="client"]`) and the pack logo
      (the pack's `logo.selector`); the client image actually loads (a truncated data URI
      or a wrong path renders as nothing and used to pass)
    · the client mark sits LEFT of the pack logo, with the declared gap (± tolerance)
    · the client mark's height is the declared size for the template's size role
      (cover / content; a closing template by its pack logo's measured height —
      cobrand.size_role) (± tolerance)
    · both marks share one vertical centre (± 2 px) — the pack logo's centre is its
      `logo.opticalCenter` (0..1 of its height, default 0.5) when the pack declares one
    · white client mark (filter brightness(0) invert(1)) exactly when the pack logo is
      white — a dark client mark on a gradient panel, or a white one on paper, FAILs
  across the run (bottom_consistency, called by render_checks.run):
    · every content slide's lockup sits at the same bottom offset as the others (± 2 px;
      the reference is the unique most common offset among the run's content slides, so
      it is measured on the whole-deck run and in chunk runs, not on a one-file run)

A slide whose lockup came from the old per-deck helper (an `<img data-logo="ok">` beside
the mark, no `data-cobrand`) is measured the same way — the exemption no longer hides it.

Exposes analyze_page(page, ds, decl) → (findings | None, info) and
bottom_consistency(entries) → {filename: [finding]}.
"""
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import check_logo  # noqa: E402
import cobrand  # noqa: E402

CENTRE_TOL = 2.0

MEASURE_JS = """
(selector) => {
  const slide = document.getElementById('slide');
  if (!slide) return { error: 'no #slide element' };
  const sb = slide.getBoundingClientRect();
  const template = slide.getAttribute('data-template') || '';
  const box = (el) => { const r = el.getBoundingClientRect();
    return { x: r.left - sb.left, y: r.top - sb.top, w: r.width, h: r.height }; };
  const shown = (el) => { const cs = getComputedStyle(el);
    return cs.display !== 'none' && cs.visibility !== 'hidden' && parseFloat(cs.opacity) > 0.01; };
  let client = slide.querySelector('[data-cobrand="client"]');
  const marks = [...slide.querySelectorAll(selector)];
  let legacy = false;
  if (!client) {  // the pre-1.6.1 per-deck helper: <img data-logo="ok"> beside the mark
    client = marks.find(e => e.tagName.toLowerCase() === 'img') || null;
    legacy = !!client;
  }
  const mark = marks.find(e => e !== client && !e.closest('[data-cobrand="client"]')) || null;
  const out = { template, sw: sb.width, sh: sb.height, legacy, client: null, mark: null };
  if (client) {
    const cs = getComputedStyle(client);
    out.client = Object.assign(box(client), {
      loaded: client.tagName.toLowerCase() !== 'img' || (client.complete && client.naturalWidth > 0),
      visible: shown(client), filter: cs.filter || 'none',
      src: (client.getAttribute('src') || '').slice(0, 80) });
  }
  if (mark) {
    let fill = mark.getAttribute('fill') || '';
    if (!fill) { const g = mark.querySelector('[fill]'); if (g) fill = g.getAttribute('fill') || ''; }
    if (!fill) fill = getComputedStyle(mark).fill || '';
    out.mark = Object.assign(box(mark), { visible: shown(mark), fill: fill.trim() });
  }
  return out;
}
"""


def _is_white(fill):
    return check_logo._norm_hex(fill) in ("#ffffff", "white")


def _bottom(sh, *boxes):
    return sh - max(b["y"] + b["h"] for b in boxes)


def analyze_page(page, ds, decl):
    """(findings, info); findings is None when the check does not apply (no declaration,
    or a template that carries no logo to pair with)."""
    if not decl:
        return None, {"skipped": "deck declares no cobrand"}
    spec = ds.get("logo") or {}
    selector = spec.get("selector") or check_logo.DEFAULT_SELECTOR
    tol = float(spec.get("tolerancePx", 3))
    m = page.evaluate(MEASURE_JS, selector)
    if "error" in m:
        return None, {"error": m["error"]}
    stem = m.get("template") or ""
    ref = check_logo._template_metrics(page, ds, stem, selector) if stem else None
    if stem and (not ref or "error" in ref or not ref.get("found")):
        return None, {"skipped": f"template {stem} carries no logo"}
    role = cobrand.role_for(ds, stem)          # where it sits (bottom row skips cover/closing)
    c, k = m.get("client"), m.get("mark")
    info = {"role": role, "template": stem, "legacy": m.get("legacy"), "bottom": None}
    findings = []
    fix = "re-create the slide with new_slide.py --force, or run cobrand.py --deck-dir D --files <slide>"
    if not k:
        findings.append(f"cobrand: pack logo missing — the lockup needs both marks ({fix})")
    if not c:
        findings.append(f"cobrand: client mark missing — deck-state.json declares {decl['logo']} ({fix})")
    if findings:
        return findings, info
    # how big the client mark is: sized from the pack logo actually on the slide, the
    # same rule cobrand.py applied (a closing slide with a content-size mark gets content sizes)
    size_role = cobrand.size_role(ds, stem, decl, k["h"])
    size = decl["sizes"][size_role]
    info["size_role"] = size_role
    if not c["loaded"]:
        findings.append(f"cobrand: client mark does not load (src {c['src']!r}) — a broken path or "
                        f"truncated data URI renders as nothing")
    if not c["visible"] or not k["visible"]:
        findings.append("cobrand: a mark of the lockup is hidden")
    c_right, k_left = c["x"] + c["w"], k["x"]
    if c_right > k_left + 0.5:
        findings.append(f"cobrand: client mark must sit left of the pack logo "
                        f"(client right edge {c_right:.0f}px, logo left edge {k_left:.0f}px)")
    elif c["loaded"] and abs((k_left - c_right) - size["gap"]) > tol:
        findings.append(f"cobrand: gap {k_left - c_right:.0f}px between the marks, "
                        f"{size_role} lockup wants {size['gap']:g}px (±{tol:g})")
    if c["loaded"] and abs(c["h"] - size["client"]) > tol:
        findings.append(f"cobrand: client mark {c['h']:.0f}px tall, {size_role} lockup wants "
                        f"{size['client']:g}px (±{tol:g})")
    oc = float(spec.get("opticalCenter", 0.5))          # pack logo's letter centre, 0..1 of its height
    dc = abs((c["y"] + c["h"] / 2) - (k["y"] + k["h"] * oc))
    if dc > CENTRE_TOL:
        findings.append(f"cobrand: vertical centres differ by {dc:.1f}px (±{CENTRE_TOL:g}) — "
                        f"the marks must share one centre line")
    # Bottom offset is a CROSS-slide row (bottom_consistency), not a template one: the
    # rule is "the lockup sits where it sits on every other content slide", and the
    # default pack has three templates whose own logo is off the 24 px chrome line.
    info["bottom"] = round(_bottom(m["sh"], c, k), 1)
    white_mark = _is_white(k["fill"])
    white_client = "invert(1)" in c["filter"].replace(" ", "") or "invert(100%)" in c["filter"].replace(" ", "")
    if white_mark and not white_client:
        findings.append(f"cobrand: pack logo is white here but the client mark is not — add "
                        f"filter:{cobrand.WHITE_FILTER} (cobrand.py does this)")
    elif white_client and not white_mark:
        findings.append(f"cobrand: client mark is filtered white but the pack logo is "
                        f"{k['fill'] or 'not white'} — drop the filter")
    info["measured"] = {"client_h": round(c["h"], 1), "logo_h": round(k["h"], 1),
                        "gap": round(k_left - c_right, 1),
                        "centre_delta": round(dc, 1), "white": white_client}
    return findings, info


def bottom_consistency(entries):
    """Cross-slide row: every content-slide lockup at the same bottom offset as the others.
    `entries` is render_checks' {name: entry}; returns {name: [finding]} for the outliers.
    The reference is the unique most common offset (rounded to 1px) among content slides;
    with no unique mode there is no majority to measure against and nothing is reported
    (the per-slide template-bottom row still runs)."""
    bottoms = {}
    for name, e in entries.items():
        info = (e or {}).get("cobrand_info") or {}
        if info.get("role") == "content" and info.get("bottom") is not None:
            bottoms[name] = round(info["bottom"])
    if len(bottoms) < 2:
        return {}
    counts = Counter(bottoms.values()).most_common()
    if len(counts) > 1 and counts[0][1] == counts[1][1]:
        return {}
    ref = counts[0][0]
    return {n: [f"cobrand: lockup bottom offset {b}px, the deck's other content slides sit at "
                f"{ref}px — align the logo wrapper with them"]
            for n, b in bottoms.items() if abs(b - ref) > 2}
