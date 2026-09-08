# svgkit

Reusable parametric SVG reconstruction for the deck-designer flow.
See `SKILL.md` for the orchestrator-facing contract (when to invoke this,
what it returns) and `CLAUDE.md`-equivalent workflow section inside
`SKILL.md` for the agent's step-by-step process. This file is the
package-level technical reference.

## Why this exists

Hand-authoring SVG paths for radial/segmented diagrams (donuts, gauges,
cycles, hub-and-spoke) from a reference screenshot is where reconstructions
break: angles get eyeballed instead of computed, gradients get flattened to
solid fills, curved labels get faked with a straight rotation, icons get
simplified into placeholder shapes. `svgkit` exists so none of that has to
be re-derived by hand every time — the geometry is trigonometry in one
tested module, not path strings improvised per slide.

## Install

```bash
pip install -e .                    # Playwright-based render/verify (default)
pip install -e ".[cairosvg]"        # optional alternate renderer
pip install -e ".[test]"            # pytest, for the fixture smoke tests
playwright install chromium         # if not already installed for this repo
```

## Quick start

```python
from recipes.registry import get_builder
from svgkit import render

build = get_builder("donut")
svg_path = build("configs/example_donut.json", "out/donut.svg")

# Verify against a reference screenshot:
history = render.verify_loop(
    build, "configs/example_donut.json",
    original_png="reference_screenshot.png",
    out_dir="out/verify",
    width=1180, height=1150,
)
print(history[-1])  # {"mae": ..., "worst_quadrant": ..., "stop_reason": ...}
```

## Layers (do not cross)

```
svgkit/    reusable math/render/text/icons/presets — never edited per-image
recipes/   per-diagram-type knowledge (.md) + builders (.py) — edited when
           adding a new diagram TYPE, not per reconstruction
configs/   per-image data (JSON) — one new file per reconstruction, never
           edit recipes/ or svgkit/ to fix one image
```

If a reconstruction needs a value that isn't in the config schema, add the
field to the config (and the recipe's builder to consume it) — never hand-
patch a one-off path string into a generated SVG.

## Extending

- **New diagram type**: copy the pattern in any `recipes/<type>_builder.py`
  (all share the signature `build(config_path, out_svg_path=None) -> svg_path`),
  write `recipes/<type>.md` (when to use, config schema, build steps,
  failure checks — mirror the existing files), register it in
  `recipes/registry.py`, add `configs/example_<type>.json`.
- **New shape math**: add to `svgkit/geometry.py` — it's shared by every
  recipe, so a new primitive there benefits all 20 types at once.
- **New icon**: add a real Lucide outline path to `svgkit/icons.py._ICONS`.
  Never substitute a placeholder shape (a `<rect>` or generic circle) for
  a missing icon in a final deliverable — that's exactly the icon-fidelity
  failure this skill is meant to prevent. Placeholders are fine only in
  `tests/test_fixtures.py`'s stub resolver, which checks build-doesn't-crash,
  not visual fidelity.

## Testing

```bash
pytest tests/ -v
```

`test_geometry.py` checks the math in isolation (including a regression
test for a real bug caught during development: `arc_segment` dividing by
zero on `r_inner=0` pie slices, and `label_rotation`'s angle convention —
verify empirically with `python3 -c "..."` before trusting hand-derived
rotation formulas, they are easy to get backwards).

`test_fixtures.py` builds every `configs/example_*.json` through its registered
recipe and confirms the output is well-formed XML with a viewBox, carries no NaN
coordinates (which render as nothing, silently), and has no unresolved f-string
placeholder — that last one caught a real bug where a role substitution landed on
a plain string literal and `fill="{presets.PRIMARY}"` shipped verbatim. It also
confirms every icon name referenced anywhere in the fixtures exists in the
built-in Lucide set, and that builders are deterministic (the render-diff verify
loop depends on it).

## Rendering engine: Playwright, not cairosvg

`svgkit/render.py` defaults to headless Chromium via Playwright — already
a dependency of this repo's `scripts/check_overflow.py`
— rather than `cairosvg`. Two reasons: cairosvg isn't installed in this
environment and pulls in a system Cairo dependency, and more importantly,
the actual shipped artifact (an HTML slide, exported to PDF via a
headless-Chromium element screenshot per `pdf-export/SKILL.md`) is
Chromium-rendered — verifying a reconstruction against Chromium's own
rendering (fonts, `<textPath>` support, gradients) checks against the real
target, not a second renderer with different SVG2/CSS support.
