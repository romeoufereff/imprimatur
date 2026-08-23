# Recipe: Generic / Unrecognized Diagram

## When to use
No specific recipe matches the reference screenshot.

## Approach
1. Decompose the image into primitives svgkit already supports:
   - circles/arcs      -> geometry.arc_segment, geometry.polar
   - rectangles/cards   -> geometry.rounded_rect
   - curves/lines       -> geometry.smooth_line, geometry.elbow_connector
   - text (any)         -> text.label / multiline / curved
   - icons              -> icons.place (built-in Lucide set)
   - fills              -> gradients.linear / radial, or presets.* for design-system tokens
2. Build a config as a flat "elements" list; write an inline builder OR
   propose a NEW recipe if the pattern will recur.
3. Run the render+diff loop (render.verify_loop) as usual.

## When to graduate to a real recipe
If you reconstruct the same layout family 2+ times, create
recipes/<type>.md + <type>_builder.py and register it in registry.py.
Do not keep reconstructing ad hoc — that's how the same donut math gets
re-derived by hand three times in one session.
