# Designer — the ten frameworks

The `deck-designer` agent enforces these while editing a slide's content; `design-crit`
checks the same ten afterwards. Read this once per spawn only if you need the reasoning
behind a rule — the per-slide procedure in `agents/deck-designer.md` already encodes the
checks that matter at write time.

| Framework | What it means | How the designer enforces it |
|---|---|---|
| 1. **Visual Hierarchy** | One focal point per slide; the eye lands there first | Name the focal point before editing (it is the `--focal` value you log); size/colour/position must make it win |
| 2. **Typography** | Modular scale, vertical rhythm, optical sizing, measure | Keep the template's type steps; never add a size the pack scale lacks; line length ≤ 65ch |
| 3. **Colour & A11y** | WCAG AA contrast (4.5:1 body, 3:1 large); 60-30-10 distribution | Pack token classes only; the batch `qa.py` computes the real ratios |
| 4. **Whitespace & Grid** | 8-point grid; ≥ 30 % of the slide empty | Do not add padding/margins the template lacks; if content needs more room, it is a density problem (escalate), not a spacing problem |
| 5. **Composition** | Rule of thirds, intentional asymmetry | Keep the template's split; centered layouts only where the template is centered (divider, closing) |
| 6. **Information Design** | Chart title = insight, not topic; high data-ink ratio | Chart titles state the takeaway; never re-add gridlines, 3-D, redundant legends |
| 7. **Cognitive Load** | Atomic items within the DENSITY dial (sparse ≤ 8 / balanced ≤ 12 / dense ≤ 14) | Count headings + bullets + KV rows + cards + chart bars + people + labelled SVG nodes; over budget → escalate, never shrink type |
| 8. **Brand Systems** | All values from tokens; template-mapped | Byte-copied template head + `data-template`; the static check FAILs anything else |
| 9. **Accessibility** | Type-scale floors; acronyms expanded on first use; no flashing | Expand acronyms in copy; never go below the pack's `minFontSizePx` |
| 10. **Presentation Narrative** | Slide title = complete assertion (not a label) | The brief's `Message:` line is the title; if it reads as a label, flag it in the report rather than rewriting the narrative yourself |

**Check during generation, not after.** If a brief's content and the locked template
cannot satisfy a framework together (five equal-weight messages and no focal point; 14
items on a `sparse` deck), that is an escalation trigger — say so in the report and stop
at that slide rather than shipping a compromise.

## Escalation rules (designer → orchestrator)

Raise these in your batch report — and if one blocks the slides after it, stop and report
early rather than guessing:

- **Content exceeds the DENSITY budget** — "6 bullets + 3 cards + 2 metrics = 11 items against
  a sparse budget of 8. Which matter most?"
- **No single focal point** — "three equal-weight messages; which leads?"
- **Locked template cannot hold the shape** — "plan says `08-product-cards`; the brief is a
  5-step sequence — propose `12-process-flow-diagram`."
- **Ambiguous or contradictory data** — "Emphasis says 37 %, key data leads with €300k."
- **Audience mismatch** — "content reads technical; brief says executive."

Never ask the user directly; the orchestrator owns intake.
