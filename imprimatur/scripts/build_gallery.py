#!/usr/bin/env python3
"""Regenerate the active design system's gallery.html — a thumbnail grid of every template.

Run after adding, renaming, or archiving any template:
    python3 scripts/build_gallery.py

Each card embeds the template in a full-size iframe scaled to card width, so the
template's own scaler computes r=1 and renders pixel-exact.

The page chrome is drawn in the pack's own tokens where it declares them (accent, ink,
body, surface, rule), falling back to neutral grays — so the gallery looks like the
design system it is showing without this script knowing which one that is.
"""
import argparse
import glob
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ds_config import load  # noqa: E402

# Token roles the chrome wants, in preference order per role. A pack that names its
# tokens differently simply gets the fallback — the gallery is a dev tool, not a
# deliverable, so a missing role is not worth failing over.
ROLE_CANDIDATES = {
    'accent':  ['blue', 'primary', 'accent', 'brand'],
    'ink':     ['text', 'ink', 'heading'],
    'body':    ['body', 'text-body'],
    'muted':   ['muted', 'muted-soft', 'subtle'],
    'surface': ['soft', 'surface', 'background'],
    'rule':    ['rule-gray', 'rule', 'border'],
}
# Achromatic by design — see the note in svgkit/presets.py. These stand in only when a
# pack leaves a role unfilled, and a grey placeholder is honest about that where a
# plausible blue would quietly look like a brand decision.
FALLBACKS = {'accent': '#1A1A1A', 'ink': '#1A1A1A', 'body': '#3D3D3D',
             'muted': '#6A6A6A', 'surface': '#F5F5F5', 'rule': '#D0D0D0'}


def resolve_roles(ds):
    """Map the chrome's semantic roles onto whatever the pack actually named its tokens."""
    try:
        cfg = open(ds.config_file, encoding='utf-8').read()
    except OSError:
        return dict(FALLBACKS)
    prefix = ds.token_prefix
    tokens = dict(re.findall(r"'" + re.escape(prefix) + r"-([\w-]+)':\s*'(#[0-9A-Fa-f]{6})'", cfg))
    return {role: next((tokens[n] for n in names if n in tokens), FALLBACKS[role])
            for role, names in ROLE_CANDIDATES.items()}


def main():
    # This script writes a file in the pack. Without a parser it did that on ANY
    # invocation — `--help` silently regenerated gallery.html — so the flags come first
    # and nothing is written until they parse.
    ap = argparse.ArgumentParser(
        description="Regenerate the active design system's gallery.html.")
    ap.add_argument("--out", default=None,
                    help="Where to write (default: the pack's docs.gallery path)")
    ap.add_argument("--dry-run", action="store_true",
                    help="Report what would be written without touching the pack")
    args = ap.parse_args()

    ds = load()
    c = resolve_roles(ds)
    cw, ch = ds.canvas
    font = ds.get('typography.familyLabel', 'system-ui')
    files = sorted(os.path.basename(f) for f in glob.glob(os.path.join(ds.templates_dir, '*.html')))
    templates_dirname = os.path.basename(ds.templates_dir)

    html = f'''<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8">
<title>{ds.name} — Template Gallery</title>
<style>
  *{{box-sizing:border-box;margin:0;padding:0}}
  body{{background:{c['surface']};font-family:"{font}",system-ui,sans-serif;padding:32px}}
  h1{{font-weight:300;font-size:28px;color:{c['ink']};margin-bottom:4px}}
  p.sub{{color:{c['muted']};font-size:13px;margin-bottom:28px}}
  #grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(420px,1fr));gap:24px}}
  .card{{background:#fff;border:1px solid {c['rule']};border-radius:8px;overflow:hidden;cursor:pointer;transition:box-shadow .15s}}
  .card:hover{{box-shadow:0 4px 16px {c['accent']}26}}
  .thumb{{position:relative;width:100%;aspect-ratio:{cw}/{ch};overflow:hidden;background:#fff}}
  .thumb iframe{{width:{cw}px;height:{ch}px;border:none;transform-origin:top left;pointer-events:none;position:absolute;top:0;left:0}}
  .label{{padding:10px 14px;font-size:13px;color:{c['body']};border-top:1px solid {c['rule']}}}
  .label b{{color:{c['accent']}}}
</style></head><body>
<h1>{ds.name} — Template Gallery</h1>
<p class="sub">{len(files)} templates · click a card to open full-size · regenerate with scripts/build_gallery.py</p>
<div id="grid"></div>
<script>
const files = {json.dumps(files)};
const dir = {json.dumps(templates_dirname)};
const CANVAS_W = {cw};
const grid = document.getElementById('grid');
for (const f of files) {{
  const card = document.createElement('div'); card.className='card';
  card.innerHTML = `<div class="thumb"><iframe loading="lazy" src="${{dir}}/${{f}}"></iframe></div>
    <div class="label"><b>${{f.match(/^\\d+/)?.[0] ?? ''}}</b> ${{f.replace(/^\\d+-/,'').replace('.html','')}}</div>`;
  card.onclick = () => window.open(dir+'/'+f, '_blank');
  grid.appendChild(card);
}}
function rescale() {{
  document.querySelectorAll('.thumb').forEach(t => {{
    const s = t.clientWidth / CANVAS_W;
    t.querySelector('iframe').style.transform = `scale(${{s}})`;
  }});
}}
window.addEventListener('resize', rescale);
window.addEventListener('load', rescale);
rescale();
</script></body></html>'''

    out = args.out or ds.path(ds.get('docs.gallery', 'gallery.html'))
    if args.dry_run:
        print(f"would write {out} ({len(cards)} templates) [{ds.name}]")
        return
    open(out, 'w', encoding='utf-8').write(html)
    print(f"{os.path.basename(out)} written ({len(files)} templates) [{ds.name}]")


if __name__ == '__main__':
    main()
