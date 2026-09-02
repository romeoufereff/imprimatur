#!/usr/bin/env python3
"""
Boot-sequence essentials for the active design-system pack (WP6) — replaces
reading `design-system.json` (14KB) + the pack's `SKILL.md` (24-27KB) +
`tailwind.config.js` (6-7KB) + `slide-base.html` (14-16KB) in full for every
template-slide spawn (designer, brand-audit, design-crit). Those four files
together were 65-90K tokens of boot context per agent, almost entirely
re-stating the same handful of facts: what prefix, what palette, what type
scale, what footer string, what logo rule.

Everything here comes from `design-system.json` (structured, via `ds_config`)
plus a best-effort scan of the pack's `SKILL.md` for a few sections
(`## Logo`, `## Template library`, an `Eyebrow:` line, `### The brand
gradient`) that design-system.json does not carry as structured data. A
section SKILL.md doesn't declare is printed as "(not declared by this pack)"
rather than guessed — the same "an empty answer is a real answer" principle
`pack_inventory.py` already uses.

`design-craft.md` (or whatever reference the pack ships for bespoke-SVG rules)
is intentionally NOT summarized here — WP6: read it only when a brief says
`Visual: bespoke`/`chart`, not on every boot.

Usage:
    pack_brief.py [--design-system PATH]
"""
import argparse
import glob
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ds_config import load  # noqa: E402


def extract_section(text, heading, max_lines=8):
    """Content of a `## <heading>` (or `### <heading>`) section, case-insensitive,
    word-bounded so '## Logo' doesn't also match '## Logo library'."""
    if not text:
        return None
    pat = re.compile(
        r"^#{2,3}\s+" + re.escape(heading) + r"\s*$(.*?)(?=^#{1,3}\s|\Z)",
        re.M | re.S | re.I,
    )
    m = pat.search(text)
    if not m:
        return None
    lines = [l for l in m.group(1).splitlines() if l.strip()]
    return "\n".join(lines[:max_lines])


def extract_line(text, prefix):
    """First line (anywhere) starting with `prefix`, case-insensitive."""
    if not text:
        return None
    for line in text.splitlines():
        s = line.strip().lstrip("-").strip()
        if s.lower().startswith(prefix.lower()):
            return s
    return None


def main():
    ap = argparse.ArgumentParser(description=__doc__.strip().split("\n")[0])
    ap.add_argument("--design-system", default=None)
    args = ap.parse_args()

    ds = load(args.design_system)
    skill_path = os.path.join(ds.root, "SKILL.md")
    skill_text = open(skill_path, encoding="utf-8").read() if os.path.isfile(skill_path) else None

    lines = []
    lines.append(f"# {ds.name} — pack brief  (id={ds.id}, prefix={ds.token_prefix})")
    lines.append(f"root: {ds.root}")
    lines.append(f"canvas: {ds.canvas[0]}x{ds.canvas[1]}")
    lines.append("")

    # Palette roles (engine-facing roles -> resolved hex, not raw token dumps)
    roles = ds.get("roles", {}) or {}
    tokens = ds.tokens()
    lines.append("## Palette roles")
    if roles:
        for role, tok in roles.items():
            if role.startswith("$"):  # manifest comment keys, not real roles
                continue
            if isinstance(tok, list):
                hexes = ds.palette(role)
                lines.append(f"  {role}: [{', '.join(hexes)}]")
            elif isinstance(tok, str):
                lines.append(f"  {role}: {tok} = {tokens.get(tok, '?')}")
    else:
        lines.append("  (not declared)")
    lines.append("")

    # Type scale + floors + weights
    lines.append("## Type scale")
    scale = ds.type_scale()
    min_px = ds.get("typography.minFontSizePx", 14)
    weights = ds.get("typography.allowedWeights", []) or []
    lines.append(f"  floor: {min_px}px  |  allowed weights: {', '.join(str(w) for w in weights)}")
    for name, step in sorted(scale.items(), key=lambda kv: -float(re.sub(r"[^\d.]", "", kv[1].get("size", "0")) or 0)):
        lines.append(f"  {ds.token_prefix}-{name}: {step.get('size')} "
                     f"(w{step.get('fontWeight', '?')}, lh{step.get('lineHeight', '?')})")
    lines.append("")

    # Footer
    lines.append("## Footer")
    lines.append(f"  required text: {ds.get('footer.requiredText') or '(not declared)'}")
    lines.append(f"  label: {ds.get('footer.label') or '(not declared)'}")
    lines.append("")

    # Eyebrow
    eyebrow = extract_line(skill_text, "eyebrow:") or extract_line(skill_text, "- eyebrow")
    lines.append("## Eyebrow")
    lines.append(f"  {eyebrow or '(not declared by this pack SKILL.md)'}")
    lines.append("")

    # Logo
    logo = extract_section(skill_text, "Logo", max_lines=6)
    lines.append("## Logo")
    lines.append(logo or "  (not declared by this pack SKILL.md)")
    lines.append("")

    # Gradient rule
    lines.append("## Gradients")
    canonical = ds.get("gradients.canonical", []) or []
    if canonical:
        lines.append(f"  canonical ({len(canonical)}): " + " | ".join(canonical[:4])
                     + (" ..." if len(canonical) > 4 else ""))
    brand_note = extract_section(skill_text, "The brand gradient", max_lines=4)
    if brand_note:
        lines.append(brand_note)
    if not canonical and not brand_note:
        lines.append("  (not declared)")
    lines.append("")

    # Template index — one-liners, from the pack's own SKILL.md table when present,
    # else generated from pack_inventory (filenames only, no description).
    lines.append("## Templates")
    tmpl_table = extract_section(skill_text, "Template library", max_lines=200)
    if tmpl_table:
        for line in tmpl_table.splitlines():
            if line.strip().startswith("|") and not set(line.replace("|", "").strip()) <= {"-"}:
                lines.append("  " + line.strip())
    else:
        for p in sorted(glob.glob(os.path.join(ds.templates_dir, "*.html"))):
            lines.append(f"  {os.path.splitext(os.path.basename(p))[0]}")

    out = "\n".join(lines)
    print(out)
    print(f"\n# ({len(out)} bytes)", file=sys.stderr)


if __name__ == "__main__":
    main()
