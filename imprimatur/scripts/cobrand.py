#!/usr/bin/env python3
"""
Co-brand lockup — declared once per deck, applied by the engine, never pasted.

A client deck carries the client's wordmark beside the pack's own logo on every slide.
Until 1.6.1 that was a designer's job: on 2026-10-20 (a 21-slide client deck) the
designers hand-pasted a 23 KB base64 wordmark into each slide and truncated it twice,
the deck then grew its own `assets/apply_cobrand.py` that the permission classifier
would not let subagents run, and qa.py's logo check exempted `data-logo="ok"` so the
lockup was never measured at all. Now:

  1. The orchestrator declares it ONCE at 4a, in deck-state.json:

         "cobrand": {"logo": "assets/<client>.png", "position": "left"}

     optional: "name" (alt text; default from the file name) and
     "sizes": {"content": {"client": 22, "gap": 24}, "cover": {"client": 48, "gap": 40}}.
     The pack's own logo keeps the template's height (28 content / 64 cover in the
     default pack) — only the client mark and the gap are the lockup's to set.

  2. new_slide.py applies it at copy time (cover sizes when the template is listed under
     the pack's `templateRoles.cover`, content sizes otherwise; a `templateRoles.closing`
     template takes cover sizes only when its own pack logo is at least as tall as the
     cover client mark — size_role()), so no designer touches the logo and no subagent
     runs an extra script.

  3. check_cobrand.py (inside render_checks.py, so qa.py and the designer stop gate)
     FAILs a slide whose lockup is missing, misplaced, missized or the wrong colour.

The lockup wraps the template's logo element in place — the template's own wrapper and
its position classes are untouched:

    <div data-cobrand="lockup" style="display:flex;align-items:center;gap:24px">
      <img src="assets/client.png" alt="Client" data-cobrand="client"
           style="height:22px;width:auto;display:block">
      <svg …the template's logo, byte-for-byte…></svg>
    </div>

The client mark is referenced by its deck-relative path, like the fonts, not inlined as
a data URI: a 23 KB line in every slide body is what the designers were reading and
retyping. When the pack logo is white (a gradient panel), the client mark gets
`filter:brightness(0) invert(1)` so it renders white too.

Retrofit an existing deck (idempotent — a slide that has the lockup is left alone):

    cobrand.py --deck-dir D                 # every slide in deck-state.json / on disk
    cobrand.py --deck-dir D --files 03-x.html 04-y.html
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

DEFAULT_SIZES = {"content": {"client": 22, "gap": 24}, "cover": {"client": 48, "gap": 40}}
POSITIONS = ("left",)
WHITE_FILTER = "brightness(0) invert(1)"
LOCKUP_ATTR = 'data-cobrand="lockup"'
DEFAULT_LOGO_SELECTOR = "svg.logo, #logo, [data-logo]"
MIME = {".png": "png", ".jpg": "jpeg", ".jpeg": "jpeg", ".webp": "webp", ".svg": "svg+xml"}


class CobrandError(Exception):
    pass


# ── the declaration ──────────────────────────────────────────────────────────

def load_decl(deck_dir):
    """The deck's normalised `cobrand` block, or None when the deck declares none.
    Raises CobrandError on a declaration that cannot be applied."""
    if not deck_dir:
        return None
    path = os.path.join(deck_dir, "deck-state.json")
    if not os.path.isfile(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            raw = (json.load(f) or {}).get("cobrand")
    except Exception:
        return None
    if not raw:
        return None
    if not isinstance(raw, dict) or not isinstance(raw.get("logo"), str) or not raw["logo"].strip():
        raise CobrandError('deck-state.json "cobrand" needs "logo": "assets/<client>.png"')
    logo = raw["logo"].strip().replace("\\", "/")
    if os.path.isabs(logo) or logo.startswith("../") or "/../" in logo:
        raise CobrandError(f'cobrand.logo must be a path inside the deck folder, got {logo!r} '
                           f'(copy the file into {os.path.join(deck_dir, "assets")}/)')
    position = raw.get("position", "left")
    if position not in POSITIONS:
        raise CobrandError(f'cobrand.position {position!r} is not supported (only "left": '
                           f'client mark left of the pack logo)')
    sizes = {role: dict(v) for role, v in DEFAULT_SIZES.items()}
    for role, v in (raw.get("sizes") or {}).items():
        if role in sizes and isinstance(v, dict):
            sizes[role].update({k: float(x) for k, x in v.items() if k in ("client", "gap")})
    stem = os.path.splitext(os.path.basename(logo))[0]
    name = raw.get("name") or re.sub(r"[-_ ]+", " ",
                                      re.sub(r"[-_ ]?(logo|wordmark|mark)$", "", stem, flags=re.I)).strip().title()
    return {"logo": logo, "position": position, "name": name or "Client", "sizes": sizes,
            "abs": os.path.join(deck_dir, logo)}


def role_for(ds, template_stem):
    """Where the lockup SITS: 'cover' when the pack lists the template under
    templateRoles.cover or .closing (a full-bleed hero slide whose logo sits off the
    content-slide line, so check_cobrand's bottom row skips it), else 'content'.
    How big the client mark is comes from size_role()."""
    covers = list(ds.get("templateRoles.cover") or []) + list(ds.get("templateRoles.closing") or [])
    return "cover" if template_stem in covers else "content"


def size_role(ds, template_stem, decl, logo_h):
    """Which declared size the client mark takes: 'cover' on a cover template, 'content'
    on a content one, and on a closing template whichever the pack logo it pairs with
    can carry — cover sizes only when that logo (`logo_h`, px) is at least as tall as the
    cover client mark, content sizes otherwise. The client mark is never taller than the
    pack logo beside it. Until 1.6.5 closing meant cover, so the EPAM pack's
    35-closing-thank-you (a 28 px content mark) got a 48 px client wordmark, ~1.7x the
    EPAM mark (2026-10-23 exec briefing); a client pack's 56 px closing wordmark
    still takes cover sizes. Unknown height → content (the smaller, safe choice)."""
    if template_stem in (ds.get("templateRoles.cover") or []):
        return "cover"
    if template_stem not in (ds.get("templateRoles.closing") or []):
        return "content"
    return "cover" if logo_h and float(logo_h) >= decl["sizes"]["cover"]["client"] - 0.5 else "content"


def logo_height(mark):
    """The pack logo's height in px from its opening tag — `style="height:Npx"` or a
    `height="N"` attribute (the EPAM pack writes the attribute, a client pack the style) —
    or None."""
    m = _TAG_RE.match(mark)
    attrs = _attrs(m.group(2)) if m else {}
    h = re.search(r"(?:^|;)\s*height:\s*(\d+(?:\.\d+)?)px", attrs.get("style", ""))
    if h:
        return float(h.group(1))
    a = re.fullmatch(r"\s*(\d+(?:\.\d+)?)(?:px)?\s*", attrs.get("height", ""))
    return float(a.group(1)) if a else None


# ── locating the logo without a browser ──────────────────────────────────────
# new_slide.py must stay a sub-second copy, so the pack's CSS selector is matched by a
# small static matcher that covers the forms logo selectors use: tag, #id, .class,
# [attr] and [attr="value"], compound and comma-separated.

_TAG_RE = re.compile(r"<([a-zA-Z][\w-]*)((?:\s+[^\s=>/]+(?:\s*=\s*(?:\"[^\"]*\"|'[^']*'|[^\s>]+))?)*)\s*/?>")
_ATTR_RE = re.compile(r"([^\s=>/]+)(?:\s*=\s*(?:\"([^\"]*)\"|'([^']*)'|([^\s>]+)))?")
_SIMPLE_RE = re.compile(r"""^(?P<tag>[a-zA-Z][\w-]*)?(?P<rest>(?:\#[\w-]+|\.[\w-]+|\[[^\]]+\])*)$""")
_PART_RE = re.compile(r"""\#([\w-]+)|\.([\w-]+)|\[\s*([\w:-]+)\s*(?:=\s*(?:"([^"]*)"|'([^']*)'|([^\]\s]+)))?\s*\]""")


def _parse_selector(selector):
    out = []
    for part in (selector or "").split(","):
        part = part.strip()
        m = _SIMPLE_RE.match(part)
        if not part or not m:
            continue  # descendant / pseudo selectors are beyond the static matcher
        conds = []
        for pm in _PART_RE.finditer(m.group("rest") or ""):
            if pm.group(1):
                conds.append(("id", pm.group(1)))
            elif pm.group(2):
                conds.append(("class", pm.group(2)))
            else:
                val = next((v for v in pm.group(4, 5, 6) if v is not None), None)
                conds.append(("attr", (pm.group(3).lower(), val)))
        out.append(((m.group("tag") or "").lower(), conds))
    return out


def _matches(tag, attrs, parsed):
    for want_tag, conds in parsed:
        if want_tag and want_tag != tag:
            continue
        ok = True
        for kind, v in conds:
            if kind == "id":
                ok = attrs.get("id") == v
            elif kind == "class":
                ok = v in (attrs.get("class") or "").split()
            else:
                name, val = v
                ok = name in attrs and (val is None or attrs[name] == val)
            if not ok:
                break
        if ok:
            return True
    return False


def _attrs(s):
    return {m.group(1).lower(): next((v for v in m.group(2, 3, 4) if v is not None), "")
            for m in _ATTR_RE.finditer(s or "")}


def find_logo(html, selector):
    """(start, end) of the first element in <body> matching the pack's logo selector —
    end is just past its closing tag — or None."""
    parsed = _parse_selector(selector or DEFAULT_LOGO_SELECTOR)
    body = re.search(r"<body\b", html)
    pos = body.start() if body else 0
    for m in _TAG_RE.finditer(html, pos):
        tag, attrs = m.group(1).lower(), _attrs(m.group(2))
        if attrs.get("data-cobrand") == "client" or not _matches(tag, attrs, parsed):
            continue
        if m.group(0).endswith("/>") or tag in ("img", "image", "use", "input"):
            return m.start(), m.end()
        depth, i = 1, m.end()
        tok = re.compile(rf"<(/?){re.escape(m.group(1))}\b[^>]*?(/?)>", re.I)
        while depth:
            t = tok.search(html, i)
            if not t:
                return None
            if t.group(1):
                depth -= 1
            elif not t.group(2):
                depth += 1
            i = t.end()
        return m.start(), i
    return None


def _is_white(fragment):
    m = re.search(r"""fill\s*(?:=\s*["']|:\s*)\s*(#[0-9a-fA-F]{3,6}\b|white\b)""", fragment)
    if not m:
        return False
    v = m.group(1).lower()
    return v in ("white", "#fff", "#ffffff")


# ── applying it ──────────────────────────────────────────────────────────────

def apply(html, decl, role, logo_selector, optical_center=0.5, ds=None, template_stem=""):
    """Returns (new_html, status). status: 'already' (lockup present, unchanged),
    'no-logo' (the template carries no logo — nothing to pair with), or
    'applied:<size role>[:white]'. With `ds` the size role is size_role() of the
    template's actual logo height; without it, `role` is used as given."""
    if LOCKUP_ATTR in html:
        return html, "already"
    span = find_logo(html, logo_selector)
    if span is None:
        return html, "no-logo"
    start, end = span
    mark = html[start:end]
    white = _is_white(mark)   # whole mark: a wordmark's first fill can sit past 600 chars of path data
    mh = logo_height(mark)
    if ds is not None:
        role = size_role(ds, template_stem, decl, mh)
    size = decl["sizes"][role]
    filt = f";filter:{WHITE_FILTER}" if white else ""
    # Optical centring: a pack logo whose letters sit off its box centre (a descender, a
    # tagline below) declares logo.opticalCenter (0..1 of its height); the client mark is
    # nudged so its centre meets the logo's LETTERS, not its bounding box.
    dy = (float(optical_center) - 0.5) * mh if (mh and optical_center != 0.5) else 0.0
    if abs(dy) >= 0.5:
        filt += f";position:relative;top:{dy:.1f}px"
    alt = decl["name"].replace('"', "&quot;")
    img = (f'<img src="{decl["logo"]}" alt="{alt}" data-cobrand="client" '
           f'style="height:{size["client"]:g}px;width:auto;display:block{filt}">')
    lockup = (f'<div {LOCKUP_ATTR} style="display:flex;align-items:center;gap:{size["gap"]:g}px">'
              f'{img}{mark}</div>')
    return html[:start] + lockup + html[end:], f"applied:{role}" + (":white" if white else "")


def template_of(html):
    m = re.search(r'id="slide"[^>]*\bdata-template="([^"]+)"|data-template="([^"]+)"[^>]*\bid="slide"', html)
    return (m.group(1) or m.group(2)) if m else ""


_LOCKUP_RE = re.compile(r'<div data-cobrand="lockup" style="[^"]*"><img [^>]*data-cobrand="client"[^>]*>(.*?)</div>', re.S)


def strip(html):
    """Undo a lockup: the template's logo element comes back byte-for-byte (it is wrapped,
    never edited), so strip + apply is how a changed declaration or pack spec reaches
    slides that already carry a lockup."""
    m = _LOCKUP_RE.search(html)
    return html if not m else html[:m.start()] + m.group(1) + html[m.end():]


def apply_file(path, decl, ds, template_stem=None, reapply=False):
    html = open(path, encoding="utf-8").read()
    if reapply:
        html_in = html
        html = strip(html)
    stem = template_stem or template_of(html)
    role = role_for(ds, stem)
    spec = ds.get("logo") or {}
    out, status = apply(html, decl, role, spec.get("selector"), float(spec.get("opticalCenter", 0.5)),
                        ds=ds, template_stem=stem)
    if reapply:
        html = html_in
    if out != html:
        open(path, "w", encoding="utf-8").write(out)
    return status


def describe(status):
    if status == "already":
        return "lockup already present — left alone"
    if status == "no-logo":
        return "template carries no logo — no lockup (nothing to pair the client mark with)"
    _, role, *white = status.split(":")
    return f"lockup applied ({role} sizes{', white client mark on a white logo' if white else ''})"


def main():
    from ds_config import load
    ap = argparse.ArgumentParser(description="Apply the deck's declared co-brand lockup to existing slides.")
    ap.add_argument("--deck-dir", required=True)
    ap.add_argument("--files", nargs="+", metavar="FILE")
    ap.add_argument("--reapply", action="store_true",
                    help="strip an existing lockup first, so a changed declaration or pack logo spec lands")
    args = ap.parse_args()
    deck_dir = os.path.abspath(args.deck_dir)
    try:
        decl = load_decl(deck_dir)
    except CobrandError as e:
        sys.exit(f"error: {e}")
    if not decl:
        sys.exit(f'error: {deck_dir}/deck-state.json declares no "cobrand" block')
    if not os.path.isfile(decl["abs"]):
        sys.exit(f"error: cobrand.logo {decl['logo']} not found in {deck_dir}")
    ds = load(deck_dir=deck_dir)
    if args.files:
        names = [os.path.basename(f) for f in args.files]
    else:
        names = sorted(f for f in os.listdir(deck_dir) if re.match(r"^\d{2}-.*\.html$", f))
    for n in names:
        p = os.path.join(deck_dir, n)
        if not os.path.isfile(p):
            print(f"{n}: no such slide")
            continue
        print(f"{n}: {describe(apply_file(p, decl, ds, reapply=args.reapply))}")


if __name__ == "__main__":
    main()
