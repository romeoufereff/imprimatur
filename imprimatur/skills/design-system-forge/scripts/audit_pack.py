#!/usr/bin/env python3
"""
audit_pack.py — find drift in a pack you are AMENDING, without needing an installed orchestrator.

verify_pack.py answers "does this pack meet its contract?" This script answers a narrower,
complementary question that only comes up mid-amendment: "did the change I just made actually
reach every consumer, and did I introduce a token collision while making it?" It is standalone
by the same design as the rest of this skill — it reads only design-system.json,
tailwind.config.js and the pack's own HTML files, and needs no deck orchestrator installed.

Four checks, each tied to a documented failure mode (see references/amendment-patterns.md):

  1. token collisions   — the same token name defined in more than one Tailwind theme category
                           (colors vs fontSize is the classic one: one wins the cascade silently).
  2. config drift        — a template/chart/snippet's inline tailwind.config disagrees with the
                           canonical tailwind.config.js for a key both define.
  3. font-size floor      — raw text-[Npx] below typography.minFontSizePx, inside <svg> too
                           (since 2026-10-06 the prose floor applies to SVG text as written;
                           svg.minCaptionPx is svgkit's sizing tier, not an exemption — the
                           engine's validate.py applies the same rule), the
                           token-only-scale-raise regression made visible.
  4. hex census (warn)   — a literal #RRGGBB that is neither a pack token/gradient stop nor
                           reused anywhere else in the pack — the signature of a stray value one
                           file missed, not the many legitimate bespoke colours a diagram uses
                           repeatedly on purpose. Reported as a warning, not a problem: it is a
                           lead worth checking, not proof of drift.

Usage:
    audit_pack.py --pack <pack dir> [--json]
"""
import argparse
import glob
import json
import os
import re
import sys

HEX_RE = re.compile(r"#[0-9A-Fa-f]{6}\b")
FONT_SIZE_RE = re.compile(r"text-\[(\d+(?:\.\d+)?)px\]")
LEFT_BAR_CLASS_RE = re.compile(r"\bborder-l-(2|4|8|\[[0-9.]+px\])\b")
LEFT_BAR_CSS_RE = re.compile(r"border-left\s*:\s*([\d.]+)px")
CONFIG_START_RE = re.compile(r"(?:tailwind\.config|module\.exports)\s*=\s*\{")
EXTEND_START_RE = re.compile(r"extend\s*:\s*\{")
CATEGORY_RE = re.compile(r"([A-Za-z_$][\w$]*)\s*:\s*\{")
KV_ARRAY_STRING_RE = re.compile(r"""['"]([\w.\-]+)['"]\s*:\s*\[\s*['"]([^'"]*)['"]""")
KV_STRING_RE = re.compile(r"""['"]([\w.\-]+)['"]\s*:\s*['"]([^'"]*)['"]""")
NESTED_OBJ_RE = re.compile(r"\{[^{}]*\}")

# fontFamily entries are `name: [...]` string lists, not `'token': value` pairs — comparing
# them the same way as colors/fontSize produces noise, so they're read but not drift-checked.
SKIP_CATEGORIES = {"fontFamily"}

# A "collision" only matters if two categories generate the SAME Tailwind utility prefix for
# the token — e.g. `colors.epam-body` and `fontSize.epam-body` both produce a `text-*` class,
# so `text-epam-body` is genuinely ambiguous (this is the exact bug known-issues.md calls out).
# `fontSize.epam-label` and `letterSpacing.epam-label` produce DIFFERENT classes (`text-*` vs
# `tracking-*`) and are not ambiguous — reusing a name across those is normal, not a bug.
# Categories not listed here are skipped for collision purposes rather than guessed at.
CATEGORY_PREFIXES = {
    "colors": {"text", "bg", "border", "ring", "fill", "stroke", "divide", "outline",
               "decoration", "accent", "caret", "from", "via", "to"},
    "fontSize": {"text"},
    "backgroundImage": {"bg"},
    "borderRadius": {"rounded"},
    "letterSpacing": {"tracking"},
    "boxShadow": {"shadow"},
}


def strip_block_comments(text):
    """Blank the contents of /* ... */ comments (keep newlines, for line-number accuracy).

    A real pack's tailwind.config.js commonly opens with a doc comment describing usage —
    including, in practice, a literal example of `tailwind.config = {…}` in prose. Searching
    the raw text finds that example instead of the real `module.exports = {`. Blanking comment
    interiors before searching avoids matching inside documentation.
    """
    def repl(m):
        return "".join(ch if ch == "\n" else " " for ch in m.group(0))
    return re.sub(r"/\*.*?\*/", repl, text, flags=re.S)


def brace_match(text, open_idx):
    """Index of the '}' that closes text[open_idx] == '{', or -1."""
    depth = 0
    for i in range(open_idx, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return i
    return -1


def find_config_span(text):
    """(start, end) of a `tailwind.config = {...}` / `module.exports = {...}` block, or None."""
    search_text = strip_block_comments(text)
    m = CONFIG_START_RE.search(search_text)
    if not m:
        return None
    open_idx = m.end() - 1
    close_idx = brace_match(search_text, open_idx)
    if close_idx == -1:
        return None
    return m.start(), close_idx + 1


def extract_categories(config_text):
    """{category_name: raw_block_text} for every top-level key inside theme.extend."""
    m = EXTEND_START_RE.search(config_text)
    if not m:
        return {}
    open_idx = m.end() - 1
    close_idx = brace_match(config_text, open_idx)
    if close_idx == -1:
        return {}
    body = config_text[open_idx + 1 : close_idx]
    categories, pos = {}, 0
    while True:
        m2 = CATEGORY_RE.search(body, pos)
        if not m2:
            break
        brace_open = m2.end() - 1
        brace_close = brace_match(body, brace_open)
        if brace_close == -1:
            break
        categories[m2.group(1)] = body[brace_open + 1 : brace_close]
        pos = brace_close + 1  # jump past this category so nested `{` never re-match
    return categories


def extract_kv(block_text):
    """{token_name: primary_value} for a category block, ignoring nested meta objects."""
    stripped = NESTED_OBJ_RE.sub("", block_text)
    kv = {}
    for m in KV_ARRAY_STRING_RE.finditer(stripped):
        kv.setdefault(m.group(1), m.group(2))
    for m in KV_STRING_RE.finditer(stripped):
        kv.setdefault(m.group(1), m.group(2))
    return kv


def load_config(path):
    """(categories: {cat: {token: value}}, span) for a file containing tailwind.config = {...}."""
    if not os.path.isfile(path):
        return {}, None
    text = open(path, encoding="utf-8", errors="replace").read()
    span = find_config_span(text)
    if not span:
        return {}, None
    cats = extract_categories(text[span[0] : span[1]])
    return {name: extract_kv(block) for name, block in cats.items()}, span


def check_token_collisions(categories, source_label):
    """Same token name defined in 2+ categories that generate the SAME utility class prefix."""
    problems = []
    by_prefix_token = {}
    for cat, kv in categories.items():
        if cat in SKIP_CATEGORIES:
            continue
        prefixes = CATEGORY_PREFIXES.get(cat)
        if not prefixes:
            continue
        for token in kv:
            for prefix in prefixes:
                by_prefix_token.setdefault((prefix, token), set()).add(cat)

    flagged = {}
    for (prefix, token), cats in by_prefix_token.items():
        if len(cats) > 1:
            flagged.setdefault(token, set()).update(f"{c} → {prefix}-{token}" for c in cats)
    for token, descriptions in sorted(flagged.items()):
        problems.append(
            f"{source_label}: token '{token}' defined in categories that collide on the same "
            f"class — {', '.join(sorted(descriptions))} — whichever Tailwind resolves last "
            f"wins for every element using that class, silently overriding the other(s)"
        )
    return problems


def check_config_drift(canonical, file_path, rel):
    """A consumer file's inline config disagreeing with the canonical tailwind.config.js."""
    cats, span = load_config(file_path)
    if span is None:
        return []
    problems = []
    for cat, kv in cats.items():
        canon_kv = canonical.get(cat, {})
        for token, value in kv.items():
            canon_value = canon_kv.get(token)
            # Whitespace-only differences (e.g. a gradient's comma spacing) aren't real drift —
            # verify_pack.py's own gradient check ignores whitespace for the same reason.
            if canon_value is not None and canon_value.replace(" ", "") != value.replace(" ", ""):
                problems.append(
                    f"{rel}: '{cat}.{token}' = {value!r} but canonical tailwind.config.js "
                    f"says {canon_value!r} — this file's copy is stale"
                )
    return problems


def svg_spans(text):
    return [(m.start(), m.end()) for m in re.finditer(r"<svg\b.*?</svg>", text, re.S)]


def check_font_floor(text, rel, min_body_px, min_svg_px):
    problems = []
    spans = svg_spans(text)
    for m in FONT_SIZE_RE.finditer(text):
        px = float(m.group(1))
        in_svg = any(s <= m.start() < e for s, e in spans)
        floor = min_svg_px if in_svg else min_body_px
        if floor is not None and px < floor:
            line = text.count("\n", 0, m.start()) + 1
            where = "SVG label" if in_svg else "body text"
            problems.append(
                f"{rel}:{line}: text-[{m.group(1)}px] is below the {floor}px floor for "
                f"{where} (typography.minFontSizePx)"
            )
    return problems


WIDTH_ZERO_RE = re.compile(r"width\s*:\s*0(?:px)?\b")


def has_accent_bar_escape(text, idx):
    """True if the enclosing tag carries data-accent-bar="ok", or the enclosing CSS rule also
    sets width:0 — a border-left used to DRAW a vertical line (a Gantt now-marker, a milestone
    rail) rather than decorate a card, which is a real, sanctioned pattern, not the banned one.
    """
    tag_start = text.rfind("<", 0, idx)
    tag_end = text.find(">", idx)
    if tag_start != -1 and tag_end != -1 and 'data-accent-bar="ok"' in text[tag_start:tag_end]:
        return True
    rule_start = text.rfind("{", 0, idx)
    rule_end = text.find("}", idx)
    if rule_start != -1 and rule_end != -1 and WIDTH_ZERO_RE.search(text[rule_start:rule_end]):
        return True
    return False


def check_left_bars(text, rel, rule_on):
    warnings = []
    for m in LEFT_BAR_CLASS_RE.finditer(text):
        if has_accent_bar_escape(text, m.start()):
            continue
        line = text.count("\n", 0, m.start()) + 1
        warnings.append(f"{rel}:{line}: class '{m.group(0)}' — decorative left-accent bar"
                        + ("" if rule_on else " (banLeftAccentBars is off in this pack, informational only)"))
    for m in LEFT_BAR_CSS_RE.finditer(text):
        if float(m.group(1)) < 2:
            continue
        if has_accent_bar_escape(text, m.start()):
            continue
        line = text.count("\n", 0, m.start()) + 1
        warnings.append(f"{rel}:{line}: 'border-left: {m.group(1)}px' — decorative left-accent bar"
                        + ("" if rule_on else " (banLeftAccentBars is off in this pack, informational only)"))
    return warnings


def owned_hexes(canonical, manifest):
    owned = set()
    for kv in canonical.values():
        for v in kv.values():
            if HEX_RE.fullmatch(v):
                owned.add(v.upper())
    grads = (manifest.get("gradients") or {})
    for stop in grads.get("brandHexMarkers", []) or []:
        if isinstance(stop, str):
            owned.add(stop.upper())
    for g in grads.get("canonical", []) or []:
        owned.update(h.upper() for h in HEX_RE.findall(g))
    return owned


def find_hex_hits(text, rel, owned, config_span):
    """(hex, rel, line_no) for every non-token literal hex outside the inline config / data URIs.

    Deliberately does not flag every off-token hex as a problem — real packs legitimately carry
    bespoke, un-tokenised colours in SVG diagrams (gradient stops, a chart's own palette), and a
    hex used many times for one diagram is an intentional choice, not drift. What amendment work
    actually needs to catch is the ORPHAN: a value that shows up exactly once anywhere in the
    pack, which is the signature of a stray literal — a typo, or one file that never got the
    token swap everywhere else received. See check_hex_census, which turns this into that count.
    """
    hits = []
    for m in HEX_RE.finditer(text):
        if config_span and config_span[0] <= m.start() < config_span[1]:
            continue  # already covered by the drift check
        line_start = text.rfind("\n", 0, m.start()) + 1
        line_end = text.find("\n", m.start())
        line = text[line_start : line_end if line_end != -1 else len(text)]
        if "data:image" in line or "data:font" in line:
            continue
        hexv = m.group(0).upper()
        if hexv in owned:
            continue
        line_no = text.count("\n", 0, m.start()) + 1
        hits.append((hexv, rel, line_no))
    return hits


def check_hex_census(all_hits):
    """Warn on hexes seen exactly once across the whole pack — likely drift, not a palette."""
    from collections import Counter
    counts = Counter(h[0] for h in all_hits)
    warnings = []
    for hexv, rel, line_no in all_hits:
        if counts[hexv] == 1:
            warnings.append(f"{rel}:{line_no}: literal {hexv} appears nowhere else in the pack "
                            f"— not a declared token/gradient stop and not reused, which is the "
                            f"usual signature of a stray value an amendment missed")
    return warnings


def gather_targets(pack):
    targets = []
    for pattern in ("templates/*.html", "charts/*.html", "snippets/*.html"):
        targets += sorted(glob.glob(os.path.join(pack, pattern)))
    base = os.path.join(pack, "slide-base.html")
    if os.path.isfile(base):
        targets.append(base)
    return targets


def main():
    ap = argparse.ArgumentParser(description="Audit an existing HTML design-system pack for drift.")
    ap.add_argument("--pack", required=True)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    pack = os.path.abspath(os.path.expanduser(args.pack))
    if not os.path.isdir(pack):
        sys.exit(f"error: no such pack: {pack}")

    canonical_path = os.path.join(pack, "tailwind.config.js")
    canonical, _ = load_config(canonical_path)
    if not canonical:
        sys.exit(f"error: could not find a `tailwind.config = {{...}}` or `module.exports = "
                 f"{{...}}` block in {canonical_path}")

    manifest_path = os.path.join(pack, "design-system.json")
    manifest = {}
    if os.path.isfile(manifest_path):
        try:
            manifest = json.load(open(manifest_path, encoding="utf-8"))
        except json.JSONDecodeError as e:
            sys.exit(f"error: design-system.json is not valid JSON: {e}")

    min_body_px = (manifest.get("typography") or {}).get("minFontSizePx")
    # Same floor inside <svg> as for prose (validate.py agrees since 2026-10-06);
    # svg.minCaptionPx is svgkit's sizing tier, no longer a validator exemption.
    min_svg_px = min_body_px
    rule_on = bool((manifest.get("rules") or {}).get("banLeftAccentBars", True))
    owned = owned_hexes(canonical, manifest)

    problems, warnings = [], []
    problems += check_token_collisions(canonical, "tailwind.config.js")

    targets = gather_targets(pack)
    if not targets:
        warnings.append("no templates/, charts/, snippets/ or slide-base.html found to audit")

    all_hex_hits = []
    for path in targets:
        rel = os.path.relpath(path, pack)
        text = open(path, encoding="utf-8", errors="replace").read()

        cats, span = load_config(path)
        if cats:
            problems += check_token_collisions(cats, rel)
        problems += check_config_drift(canonical, path, rel)

        if min_body_px is not None:
            problems += check_font_floor(text, rel, min_body_px, min_svg_px)
        else:
            warnings.append("typography.minFontSizePx is unset — font-size floor check skipped")

        bar_hits = check_left_bars(text, rel, rule_on)
        (problems if rule_on else warnings).extend(bar_hits)

        all_hex_hits += find_hex_hits(text, rel, owned, span)

    warnings += check_hex_census(all_hex_hits)

    result = {"pack": pack, "files_scanned": len(targets),
              "problems": problems, "warnings": warnings}

    print(f"pack: {pack}")
    print(f"files scanned: {len(targets)}")
    print(f"drift: {len(problems)} problem(s), {len(warnings)} warning(s)")
    for p in problems:
        print(f"  PROBLEM  {p}")
    for w in warnings:
        print(f"  warn     {w}")

    if args.json:
        print(json.dumps(result, indent=2))

    if problems:
        print(f"\n{len(problems)} drift issue(s) found — these are the consumers an amendment "
              f"likely missed, or a pre-existing inconsistency worth fixing while you're in here.")
    else:
        print("\nNo drift found. Templates agree with tailwind.config.js and no token collisions "
              "or off-token colours were seen.")
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
