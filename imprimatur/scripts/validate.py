#!/usr/bin/env python3
"""
Slide validator — mechanical, design-system agnostic.

Checks every template (and any generated slide) against the rules the ACTIVE design
system declares in its design-system.json. Nothing here knows which brand it is
auditing: token prefix, palette, fonts, weights, footer string, gradient canon and
every on/off rule come from the manifest, so replacing the design-system folder
re-points the whole check suite at the new brand.

Run after editing any template, and before promoting a new template or variant.

Usage:
    python3 scripts/validate.py            # validate the active pack's whole template set
    python3 scripts/validate.py FILE...    # validate specific HTML files (e.g. deck slides)

Exit code 0 = all checks pass; 1 = at least one FAIL. WARNs never fail the run.

brand-audit runs this for its deterministic checks instead of eyeballing: token values
(color AND gradient), font-size floors, footer/scaler/config presence, gradient canon,
AND the brand firewall
— Tailwind default-palette classes, hexes outside the pack's palette census, off-scale
font weights, off-brand font declarations, emoji, drop-shadow classes, decorative
left-accent bars, and a mandatory data-template attribute (proof the slide was copied
from a template rather than generated from the model's own default aesthetic).

Note on render-level overflow: a pack may sanction templates that intentionally bleed
ONE decorative element past the canvas edge (clipped by #slide's overflow:hidden) via
exemptions.decorBleedAllowlist or the data-decor-bleed="ok" attribute. That is
check_overflow.py's business, not this script's.
"""

import glob
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _targets  # noqa: E402
from ds_config import load  # noqa: E402

# ── brand-independent patterns ────────────────────────────────────────────
# These describe things that are off-brand for ANY design system (Tailwind's stock
# palette, emoji, structural shadows), or engine conventions (the canonical scaler).
# Values that differ per brand are read from the manifest instead.

TW_PALETTE_RE = re.compile(
    r'\b(?:bg|text|border|from|via|to|fill|stroke|ring|divide|outline|decoration|accent|caret)'
    r'-(?:slate|gray|zinc|neutral|stone|red|orange|amber|yellow|lime|green|emerald|teal|cyan'
    r'|sky|blue|indigo|violet|purple|fuchsia|pink|rose)-\d{2,3}\b')

# @font-face blocks REGISTER available weight files; they don't use weights. Stripped
# before the weight scan so a pack may ship files it never sets as a class.
FONTFACE_RE = re.compile(r'@font-face\s*\{[^}]*\}')

FONT_CLASS_RE = re.compile(r'\bfont-(?:serif|mono|sans)\b')  # resolve to system stacks
CSS_FONTFAMILY_RE = re.compile(r'font-family\s*:\s*([^;}]+)')
SVG_FONTFAMILY_RE = re.compile(r'font-family="([^"]+)"')

# Typographic arrows (U+2190–U+21FF: → ↑ ⇢) are legitimate and deliberately excluded.
EMOJI_RE = re.compile('[\U0001F000-\U0001FAFF☀-➿⭐⭕️]')

SHADOW_RE = re.compile(r'\bshadow-(?:sm|md|lg|xl|2xl|inner)\b|\bdrop-shadow-\w+')

# Decorative LEFT accent bars. A thick coloured stripe down the side of a card is the
# most-reported "generic AI dashboard" tell; a rule that lives only in prose keeps
# coming back, which is why it is mechanical here.
#   Banned:   border-l-2 / -4 / -8 / -[3px]   — a decorative stripe on a card
#   Allowed:  border-l                        — a 1px rule divider
# Scope is the LEFT edge only. Two escape hatches for genuinely functional lines:
#   • data-accent-bar="ok" on the element (mirrors data-decor-bleed="ok")
#   • a CSS rule that also sets width:0 — line-DRAWING, not a card accent
ACCENT_BAR_TAG_RE = re.compile(r'<[^>]*\bborder-l-(?:2|4|8|\[[^\]]+\])(?![\w-])[^>]*>')
ACCENT_BAR_CLASS_RE = re.compile(r'\bborder-l-(?:2|4|8|\[[^\]]+\])(?![\w-])')
ACCENT_BAR_OK_RE = re.compile(r'data-accent-bar\s*=\s*("|\')ok\1')
CSS_RULE_RE = re.compile(r'\{([^{}]*)\}')
CSS_LEFT_BAR_RE = re.compile(r'border-left\s*:\s*(\d+(?:\.\d+)?)px')
CSS_ZERO_WIDTH_RE = re.compile(r'\bwidth\s*:\s*0\b')

HEX_RE = re.compile(r'#([0-9A-Fa-f]{6}|[0-9A-Fa-f]{3})\b')

# A slide's inline `tailwind.config = {...}</script>` block. Every template carries one,
# and it is meant to be a verbatim copy of the pack's config — so it can only ever
# restate hexes the config already sanctions. It is excluded from the palette CENSUS
# (see allowed_hexes) while still being checked like any other markup.
INLINE_CONFIG_RE = re.compile(r'tailwind\.config\s*=.*?</script>', re.S)

# A co-branded deck carries the client's own brand colors in the client's logo, and
# that mark may not be recolored. An <svg> marked data-client-logo="ok" is excluded
# from the palette census only, so the firewall keeps its teeth everywhere else.
CLIENT_LOGO_SVG_RE = re.compile(
    r'<svg\b[^>]*\bdata-client-logo\s*=\s*("|\')ok\1.*?</svg>', re.S)

# Canonical scaler: #slide keeps its fixed canvas box and is fitted to the viewport with
# transform:scale. Resizing the element's own width/height causes REAL re-layout (text
# re-wraps at every viewport, and exports diverge from the HTML preview).
SCALER_TRANSFORM_RE = re.compile(r"\.style\.transform\s*=\s*['\`]scale\(")

# ── head-identity check (WP2) ───────────────────────────────────────────────
# "Copy the template verbatim" turned out, in every observed transcript, to mean
# "retype 7-24K tokens of identical boilerplate from memory" — half of every slide
# write, and the actual mechanism behind brand drift (a retyped hex, a dropped
# @font-face rule, a subtly wrong scaler). new_slide.py (WP2) now does the copy in
# a script instead, so this check turns "was it actually copied" into a diff
# instead of a heuristic: a deck slide's <head> must match its OWN claimed source
# template's <head>, not the model's memory of what EPAM slides tend to look like.
#
# Deliberately NOT compared against the pack's slide-base.html: that file's head is
# NOT byte-identical to the templates' heads in this pack today (different
# minification, different comments) — a real, pre-existing inconsistency, confirmed
# against all 70 shipped templates. Comparing against the file's OWN declared
# data-template source is what a byte-for-byte copy actually promises, and it is
# what new_slide.py always produces regardless of which template family it copied.
#
# The comparison is a NORMALIZED SUPERSET check, not raw byte equality, for two
# reasons found in real decks (STADA fixture, 2026-09):
#   1. Whitespace/comment reflow: the pack's template files have been reformatted
#      (blank lines, `// comment` additions) since some already-shipped deck slides
#      were copied from an earlier version of the same template. Title text also
#      legitimately differs (deck slide title vs. the template's generic title).
#   2. Sanctioned additions: a slide may deliberately extend its <style> block with
#      one extra rule (e.g. `.gradient-border-featured`) documented in
#      design-decisions.md. That is composition, not drift — the check must not
#      penalize an addition that changes nothing the template already declared.
# What it still catches: a wrong token value, a dropped @font-face block, a
# retyped scaler, or a head assembled from memory that only resembles the
# original — none of those survive as a literal (whitespace/comment-insensitive)
# substring of the template's own head text.
_HEAD_TITLE_RE = re.compile(r'<title\b[^>]*>.*?</title>', re.S | re.I)
_HEAD_HTML_COMMENT_RE = re.compile(r'<!--.*?-->', re.S)
# Strips a `// comment` to end-of-line, whether it's the whole line (a template
# reformat added several, e.g. "// eyebrows/captions/sub-labels — WCAG-safe") or
# trailing after code. The `(?<!:)` negative lookbehind is what keeps this from
# corrupting `https://cdn.tailwindcss.com` — a URL's "//" is always preceded by
# ':', a comment's never is.
_HEAD_LINE_COMMENT_RE = re.compile(r'(?<!:)//[^\n]*')
_HEAD_BLOCK_COMMENT_RE = re.compile(r'/\*.*?\*/', re.S)
DATA_TEMPLATE_RE = re.compile(r'data-template="([^"]+)"')


def extract_head(html_text):
    m = re.search(r'^(.*?)</head\s*>', html_text, re.S | re.I)
    return m.group(1) if m else html_text


def normalize_head(head_text):
    """Whitespace/comment-insensitive, title-excluded form for the superset check."""
    t = _HEAD_TITLE_RE.sub('', head_text)
    t = _HEAD_HTML_COMMENT_RE.sub('', t)
    t = _HEAD_LINE_COMMENT_RE.sub('', t)
    t = _HEAD_BLOCK_COMMENT_RE.sub('', t)
    return re.sub(r'\s+', ' ', t).strip()


def head_identity_check(path, s, ds, template_stems):
    """Returns a FAIL message, or None if the slide's head matches (or has no
    checkable claim on) its declared source template."""
    name = os.path.basename(path)
    if name == os.path.basename(ds.base_file):
        return None
    # Only meaningful for an actual DECK SLIDE (an `NN-slug.html` file living
    # OUTSIDE the pack) claiming to be a byte-copy. ANY file under the pack root
    # — templates/, snippets/, charts/, evals/ (seeded off-brand fixtures,
    # audit-eval targets), fonts/, references/ — is excluded wholesale, not just
    # templates/snippets/charts individually: a sweep over snippets/*.html once
    # flagged bar-chart.html and donut-chart.html this way (they name
    # "42-data-chart" as a related template via data-template for provenance,
    # without being a byte-copy of it), and the pack's evals/stage-brand-audit
    # seeded fixtures carry deliberately-wrong data-template claims by design —
    # this check has no business running on either.
    abspath = os.path.abspath(path)
    try:
        if os.path.commonpath([abspath, os.path.abspath(ds.root)]) == os.path.abspath(ds.root):
            return None
    except ValueError:
        pass
    m = DATA_TEMPLATE_RE.search(s)
    if not m or template_stems is None or m.group(1) not in template_stems:
        return None  # requireDataTemplate (if on) already reports a missing/bad attribute
    stem = m.group(1)
    template_path = os.path.join(ds.templates_dir, stem + '.html')
    try:
        template_text = open(template_path, encoding='utf-8').read()
    except OSError:
        return None
    slide_norm = normalize_head(extract_head(s))
    template_norm = normalize_head(extract_head(template_text))
    if not template_norm:
        return None

    # Not a plain substring test: a sanctioned addition can land in the MIDDLE of
    # the template's content (e.g. one extra CSS rule inserted before </style>),
    # which splits the template's own text into a prefix and a suffix around it —
    # still fully present, just no longer contiguous. difflib's opcodes give the
    # real invariant: every piece of the template must appear in the slide
    # ('equal'), and the ONLY difference allowed is the slide having MORE text
    # ('insert') — never 'delete' (something from the template is missing) or
    # 'replace' (something from the template was changed).
    import difflib
    sm = difflib.SequenceMatcher(None, template_norm, slide_norm, autojunk=False)
    bad_ops = [op for op in sm.get_opcodes() if op[0] in ('delete', 'replace')]
    if bad_ops:
        # Report the largest offending template span so the message points at
        # something concrete instead of just "it's different."
        tag, i1, i2, j1, j2 = max(bad_ops, key=lambda op: op[2] - op[1])
        snippet = template_norm[i1:i2][:80]
        return (f'head block does not match its declared template "{stem}" — the slide is '
                f'missing or has altered: "{snippet}"{"…" if i2 - i1 > 80 else ""}. It may have '
                f'been retyped from memory instead of copied byte-for-byte. Use '
                f'scripts/new_slide.py to (re)create it, or diff the two <head> blocks by hand '
                f'if this is a deliberate, documented head change.')
    return None


def _norm_hex(h):
    """Normalize a 3- or 6-digit hex (without '#') to uppercase 6-digit."""
    if len(h) == 3:
        h = ''.join(c * 2 for c in h)
    return h.upper()


def token_re(prefix):
    """Matches a `'<prefix>-token': '#RRGGBB'` pair in a Tailwind config block."""
    return re.compile(r"'(" + re.escape(prefix) + r"-[\w-]+)':\s*'(#[0-9A-Fa-f]{6})'")


def gradient_token_re(prefix):
    """Matches a `'<prefix>-token': '<...gradient(...)...>'` pair — Tailwind backgroundImage.

    Gradient-valued tokens are single-hex-shaped nowhere, so token_re never saw them.
    That blind spot let an `ds-section` token drift to an entirely different palette
    in 46 of 63 templates while every mechanical check reported clean.

    Kept in its own map rather than merged with the color tokens because one token NAME
    may legitimately appear in several config sections — this pack declares 'ds-section'
    in both fontSize and backgroundImage. Array-valued fontSize entries match neither
    regex, so the two maps never collide.
    """
    return re.compile(r"'(" + re.escape(prefix) + r"-[\w-]+)':\s*'([^']*gradient\([^']*)'")


def norm_gradient(value):
    """Whitespace- and case-insensitive form, so a reflowed declaration is not drift."""
    return re.sub(r'\s+', '', value).upper()


def weight_patterns(allowed):
    """Build the off-scale-weight matchers from the pack's allowed weight list.

    Tailwind's named weight classes map to numbers; only the ones the pack does not
    sanction are banned, so a pack that legitimately uses 500 simply lists it.
    """
    named = {100: 'thin', 200: 'extralight', 300: 'light', 400: 'normal', 500: 'medium',
             600: 'semibold', 700: 'bold', 800: 'extrabold', 900: 'black'}
    banned_nums = [n for n in named if n not in allowed]
    banned_names = [named[n] for n in banned_nums]
    tw = re.compile(r'\bfont-(?:' + '|'.join(banned_names) + r')\b') if banned_names else None
    nums = '|'.join(str(n) for n in banned_nums)
    css = re.compile(r'font-weight\s*:\s*(?:' + nums + r')\b') if banned_nums else None
    svg = re.compile(r'font-weight="(?:' + nums + r')"') if banned_nums else None
    return tw, css, svg


def canonical_tokens(ds):
    """Parse the pack's tokens from its Tailwind config — the single source of truth.

    Returns (colors, gradients): `'<tok>': '#RRGGBB'` pairs and `'<tok>': '<gradient>'`
    pairs, keyed separately because the two live in different config sections.
    """
    try:
        cfg = open(ds.config_file, encoding='utf-8').read()
    except OSError:
        return {}, {}
    return (dict(token_re(ds.token_prefix).findall(cfg)),
            dict(gradient_token_re(ds.token_prefix).findall(cfg)))


def allowed_hexes(ds):
    """The sanctioned palette = every hex appearing in the pack's own curated files.
    Any hex outside this census is off-brand by definition.

    Template INLINE CONFIG BLOCKS are excluded (palette.censusExcludesInlineConfig).
    A template's config block is a verbatim copy of the pack's config, so it can only
    restate hexes tailwind.config.js already sanctions — but counting it as a census
    source meant a mistyped token value legitimised its own hexes, and the census
    vouched for the very drift it exists to catch. Template BODY markup still counts:
    bespoke gradient stops and tints there are per-template art, not token declarations.
    """
    drop_inline = bool(ds.get('palette.censusExcludesInlineConfig', True))
    hexes = set()
    for pattern in ds.get('palette.censusSources', []) or []:
        for p in sorted(glob.glob(ds.path(pattern))):
            try:
                text = open(p, encoding='utf-8').read()
            except OSError:
                continue
            if drop_inline:
                text = INLINE_CONFIG_RE.sub(' ', text)
            hexes.update(_norm_hex(h) for h in HEX_RE.findall(text))
    return hexes


def check_file(path, ds, tokens, gradients=None, palette=None, template_stems=None):
    name = os.path.basename(path)
    s = open(path, encoding='utf-8').read()
    fails, warns = [], []

    base_name = os.path.basename(ds.base_file)
    is_base = name == base_name
    canvas_w, _ = ds.canvas
    min_px = float(ds.get('typography.minFontSizePx', 14))
    prefix = ds.token_prefix

    # --- structure ---
    if ds.rule('requireSlideCanvas') and 'id="slide"' not in s:
        fails.append('missing id="slide" canvas')
    if ds.rule('requireInlineTailwindConfig') and 'tailwind.config' not in s:
        fails.append('missing inline tailwind.config block')
    footer = ds.get('footer.requiredText')
    if ds.rule('requireFooterText') and footer and footer not in s and not is_base:
        fails.append(f'missing "{ds.get("footer.label", footer)}" footer')
    marker = ds.get('typography.familyMarker')
    if ds.rule('requireFontMarker') and marker and marker not in s:
        fails.append(f'missing {ds.get("typography.familyLabel", marker)} font stack')

    if ds.rule('requireCanonicalScaler'):
        fixed_w = re.search(r"\.style\.width\s*=\s*'" + str(canvas_w) + r"px'", s)
        ratio = re.search(r"(?:window\.)?innerWidth\s*/\s*" + str(canvas_w), s)
        legacy = re.search(r"\.style\.width\s*=\s*(?:w\b|\(?\s*" + str(canvas_w) + r"\s*\*)", s)
        if legacy:
            fails.append(f'legacy width-resize scaler (s.style.width=computed px) — must use '
                         f'transform:scale with a fixed {canvas_w}px box')
        elif not (fixed_w and SCALER_TRANSFORM_RE.search(s) and ratio):
            fails.append(f'missing canonical transform:scale scaler '
                         f'(fixed {canvas_w}px width + transform=scale(r))')

    # --- font-size floor (Tailwind arbitrary classes, inline styles, SVG attrs) ---
    # Decimals must not slip the floor — a 13.5px and a 12.5px shipped in real
    # templates because an integer-only regex missed them.
    if ds.rule('enforceFontSizeFloor'):
        for n in re.findall(r'text-\[(\d+(?:\.\d+)?)px\]', s):
            if float(n) < min_px:
                fails.append(f'text-[{n}px] below {min_px:g}px floor')
        # Text drawn INSIDE an <svg> is diagram labelling, not slide prose: it sits in
        # fixed geometry (boxes, circles, chevrons) that does not grow with the type
        # scale, so raising it to the prose floor pushes labels out of their shapes.
        # The pack declares its own diagram floors under svg.*; use those here.
        svg_floor = float(ds.get('svg.minCaptionPx', min_px) or min_px)
        svg_regions = re.findall(r'<svg\b.*?</svg>', s, re.S)
        in_svg = ''.join(svg_regions)
        outside = s
        for r in svg_regions:
            outside = outside.replace(r, '', 1)
        for n in re.findall(r'font-size:\s*(\d+(?:\.\d+)?)px', outside):
            if float(n) < min_px:
                fails.append(f'font-size:{n}px below {min_px:g}px floor')
        for n in re.findall(r'font-size:\s*(\d+(?:\.\d+)?)px', in_svg):
            if float(n) < svg_floor:
                fails.append(f'SVG font-size:{n}px below {svg_floor:g}px diagram floor')
        for n in re.findall(r'font-size="(\d+(?:\.\d+)?)"', s):
            if float(n) < svg_floor:
                fails.append(f'SVG font-size="{n}" below {svg_floor:g}px diagram floor')

    # --- inline token values must match the pack's config ---
    # Both shapes a token can take are compared: single hexes (colors, borderColor…)
    # and whole gradient strings (backgroundImage). Checking only the first is what let
    # a wrong section gradient ship in 46 templates.
    if ds.rule('enforceTokenValues'):
        cfg_name = os.path.basename(ds.config_file)
        for tok, val in token_re(prefix).findall(s):
            canon = tokens.get(tok)
            if canon and canon.upper() != val.upper():
                fails.append(f'token {tok} = {val}, canonical is {canon}')
            elif canon is None:
                warns.append(f'token {tok} not in {cfg_name} — add it there or remove it here')
        for tok, val in gradient_token_re(prefix).findall(s):
            canon = (gradients or {}).get(tok)
            if canon and norm_gradient(canon) != norm_gradient(val):
                fails.append(f'gradient token {tok} = {val}, canonical is {canon}')
            elif canon is None:
                warns.append(f'gradient token {tok} not in {cfg_name} — add it there '
                             f'or remove it here')

    # --- brand gradient canon ---
    if ds.rule('enforceGradientCanon'):
        markers = ds.get('gradients.brandHexMarkers', []) or []
        canon_set = {g.replace(' ', '') for g in (ds.get('gradients.canonical', []) or [])}
        if not markers or not canon_set:
            # The rule is ON but its data is missing. Skipping silently would report a
            # clean pass for a check that never ran — the failure mode this whole file
            # exists to prevent. Name the missing key instead.
            missing = ' and '.join(k for k, v in (('gradients.brandHexMarkers', markers),
                                                  ('gradients.canonical', canon_set)) if not v)
            fails.append(f'rule enforceGradientCanon is on but {missing} is empty in '
                         f'design-system.json — the check cannot run')
        else:
            probe = re.compile(r'linear-gradient\([^)]*'
                               + r'[^)]*'.join(re.escape(m) for m in markers) + r'[^)]*\)')
            for g in set(probe.findall(s)):
                if g.replace(' ', '') not in canon_set:
                    warns.append(f'non-canonical brand gradient variant: {g[:70]}')

    # --- brand firewall: off-brand styling is a FAIL, not a taste question ---
    # The checks above verify the PRESENCE of brand markers; these verify the ABSENCE
    # of non-brand styling. Without them a slide styled in the model's own default
    # aesthetic (cream backgrounds, serif display type, indigo→purple gradients,
    # slate-900 cards, emoji icons) passes clean — proven with a test slide.
    stripped = FONTFACE_RE.sub('', s)

    if ds.rule('banTailwindDefaultPalette'):
        note = ds.note('banTailwindDefaultPalette')
        for m in sorted(set(TW_PALETTE_RE.findall(s))):
            article = 'an' if ds.token_prefix[:1].lower() in 'aeiou' else 'a'
            fails.append(f'Tailwind default-palette class "{m}" — use {article} '
                         f'{ds.token_class_example()} token class instead')
        # The pack's note explains the rule once, not once per violation: repeating it on
        # every line restated one example class ("bg-slate-900") regardless of what was
        # actually found, which read as a mismatch between the finding and its explanation.
        if note and TW_PALETTE_RE.search(s):
            warns.append(note)

    if ds.rule('banOffScaleFontWeights'):
        allowed = [int(w) for w in (ds.get('typography.allowedWeights', []) or [])]
        tw_w, css_w, svg_w = weight_patterns(allowed)
        found = set()
        for rx in (tw_w, css_w, svg_w):
            if rx:
                found |= set(rx.findall(stripped))
        for m in sorted(found):
            fails.append(f'forbidden font weight "{m}" — allowed weights are '
                         f'{"/".join(str(w) for w in sorted(allowed))} only')

    if ds.rule('banRawFontSizes'):
        # The 2026-07 scale raise changed the TOKENS and nothing else, so templates that
        # hardcoded text-[Npx] never picked it up and the library drifted back to
        # 7-8pt-equivalent type. Size belongs to the scale; this is what keeps it there.
        note = ds.note('banRawFontSizes')
        exempt_at = 100  # one-off display numerals (ghost figures, hero stats)
        raw = set()
        for m in re.finditer(r'text-\[(\d+(?:\.\d+)?)px\]', stripped):
            if float(m.group(1)) < exempt_at:
                raw.add(m.group(0))
        for m in sorted(raw):
            msg = f'hardcoded font size "{m}" — use a {prefix}-* type token'
            fails.append(msg + (f'. {note}' if note else ''))

    if ds.rule('banOffBrandFontFamilies'):
        util = ds.get('typography.fontUtilityClass', '')
        label = ds.get('typography.familyLabel', '')
        ok_re = re.compile(ds.get('typography.familyRequiredPattern', '.'))
        for m in sorted(set(FONT_CLASS_RE.findall(s))):
            fails.append(f'off-brand font class "{m}" — slides use {util} ({label} stack)')
        for decl in set(CSS_FONTFAMILY_RE.findall(stripped)) | set(SVG_FONTFAMILY_RE.findall(stripped)):
            if not ok_re.search(decl):
                fails.append(f'font-family without the {label} stack: "{decl.strip()[:60]}"')

    if ds.rule('banEmoji'):
        emo = set(EMOJI_RE.findall(s))
        if emo:
            fails.append(f'emoji found ({" ".join(sorted(emo))}) — icons are '
                         f'{ds.get("iconPolicy", "vector SVG only")}')

    if ds.rule('banStructuralShadows'):
        for m in sorted(set(SHADOW_RE.findall(s))):
            fails.append(f'drop-shadow class "{m or "drop-shadow"}" — no shadows on structural '
                         f'boxes (SVG <feDropShadow> in <defs> is the only sanctioned shadow)')

    if ds.rule('banLeftAccentBars'):
        note = ds.note('banLeftAccentBars')
        for tag in ACCENT_BAR_TAG_RE.findall(s):
            if ACCENT_BAR_OK_RE.search(tag):
                continue
            cls = ACCENT_BAR_CLASS_RE.search(tag)
            fails.append(f'decorative left-accent bar "{cls.group(0)}" — {note}')
        for block in CSS_RULE_RE.findall(s):
            m = CSS_LEFT_BAR_RE.search(block)
            if m and float(m.group(1)) >= 2 and not CSS_ZERO_WIDTH_RE.search(block):
                fails.append(f'decorative left-accent bar "border-left:{m.group(1)}px" — {note} '
                             f'(a zero-width line-drawing rule is exempt)')

    if ds.rule('enforcePaletteCensus') and not palette:
        # Same reasoning as the gradient canon above, and this one matters more: the
        # census is the strongest rule in the brand firewall. An empty one usually means
        # palette.censusSources has a typo or its globs match nothing after a file move.
        fails.append('rule enforcePaletteCensus is on but the palette census is empty — '
                     'check palette.censusSources in design-system.json; its globs are '
                     'resolved relative to the pack root and currently match no files')
    elif ds.rule('enforcePaletteCensus'):
        off = sorted('#' + h for h in
                     {_norm_hex(h) for h in HEX_RE.findall(CLIENT_LOGO_SVG_RE.sub(' ', s))} - palette)
        if off:
            fails.append(f'hex color(s) outside the {ds.name} palette: {", ".join(off)} '
                         f'(palette = union of tokens + design-system files). '
                         + ds.note('enforcePaletteCensus'))

    if ds.rule('requireDataTemplate') and template_stems is not None and not is_base:
        mt = re.search(r'data-template="([^"]+)"', s)
        if not mt:
            fails.append('missing data-template attribute on #slide — copy a template verbatim '
                         '(all templates carry it); a slide without it was likely generated '
                         'from memory')
        elif mt.group(1) not in template_stems:
            fails.append(f'data-template="{mt.group(1)}" does not match any file in '
                         f'{os.path.basename(ds.templates_dir)}/')

    # --- head identity: was this slide actually copied from its claimed template? ---
    # Unconditional (not gated behind a pack rule) — this is an engine-side integrity
    # check on the copy-then-edit promise (WP2), not a brand rule the pack declares.
    head_msg = head_identity_check(path, s, ds, template_stems)
    if head_msg:
        fails.append(head_msg)

    lib = ds.get('charts.library')
    if lib and lib in s and (ds.get('charts.requiredMarker') or '') not in s:
        warns.append(ds.get('charts.message', f'{lib} present without brand color config'))

    # --- font paths: must actually resolve from the file's own location ---
    # A font URL that 404s makes the browser fall back to system fonts with different
    # metrics — text overflows and gradient text clips (the "blue rectangle" artifact).
    if ds.rule('checkFontUrlsResolve'):
        fonts_dirname = os.path.basename(ds.fonts_dir)
        file_dir = os.path.dirname(os.path.abspath(path))
        for fp in set(re.findall(r"url\(\s*['\"]?([^'\")]+\.(?:ttf|woff2?|otf))['\"]?\s*\)", s)):
            if fp.startswith(('http://', 'https://', 'data:')):
                continue
            resolved = fp[7:] if fp.startswith('file://') else fp
            if not os.path.isabs(resolved):
                resolved = os.path.normpath(os.path.join(file_dir, resolved))
            if not os.path.isfile(resolved):
                fails.append(f'font URL does not resolve: {fp} '
                             f'(run scripts/fix_font_paths.py --deck-dir on deck slides)')
            elif f'{fonts_dirname}/' not in fp:
                warns.append(f'unexpected font path: {fp} (expected a {fonts_dirname}/ dir reference)')

    return fails, warns


def main():
    ds = load()
    tokens, gradients = canonical_tokens(ds)
    palette = allowed_hexes(ds)
    template_stems = {os.path.splitext(os.path.basename(p))[0]
                      for p in glob.glob(os.path.join(ds.templates_dir, '*.html'))}
    _, targets = _targets.parse(
        'Validate slides against the active design system\'s declared rules.',
        ds.templates_dir)
    if targets == sorted(glob.glob(os.path.join(ds.templates_dir, '*.html'))):
        # A full sweep covers everything deck-designer is told to copy from, not just
        # templates/. Leaving charts/ and snippets/ ungated is how a stale token value and
        # a whole pre-2026-07 type scale survived in them indefinitely, reproduced faithfully
        # into every deck that used them, with no gate ever firing (known-issues.md §10).
        for key, default in (('tokens.snippetsDir', 'snippets'),
                             ('tokens.chartsDir', 'charts')):
            extra = ds.path(ds.get(key, default))
            if os.path.isdir(extra):
                targets += sorted(glob.glob(os.path.join(extra, '*.html')))
        targets = targets + [ds.base_file]

    total_fails = 0
    for path in targets:
        fails, warns = check_file(path, ds, tokens, gradients, palette, template_stems)
        if fails or warns:
            print(os.path.basename(path))
            for f in fails:
                print(f'  FAIL  {f}')
            for w in warns:
                print(f'  warn  {w}')
        total_fails += len(fails)

    n = len(targets)
    if total_fails:
        print(f'\n{total_fails} failure(s) across {n} file(s). [{ds.name}]')
        sys.exit(1)
    print(f'All {n} file(s) pass. [{ds.name}]')


if __name__ == '__main__':
    main()
