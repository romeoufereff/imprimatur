# Anti-Slop Tells

A named catalog of the patterns that make an AI-generated deck read as *generic* even
when every slide is brand-compliant. Brand-audit checks whether a slide obeys the design
system's rules (tokens, contrast, logo, weights); it cannot tell whether a slide is
*interesting*.
These are the tells that survive compliance, so they live with **design-crit**
(judgment) and the **deck-designer** pre-flight (avoid them while generating).

**Scope — two failure families.** The layout/hierarchy/variety tells below are the
dimensions the brand leaves open and where slop creeps in even on brand-compliant slides.
The **brand-drift tells** (last section) are different: they are the model's own default
aesthetic showing through instead of the installed design system's. They are written
against *roles* (primary, accent, tint, rule) rather than one brand's token names —
resolve each role through `design-system/design-system.json`. An earlier version of this file excluded
brand-level tells on the assumption that brand-audit mechanically catches them — it did
not (a fully model-styled slide passed every check), so they are now named here *and*
enforced by `validate.py`'s brand firewall. If you can name a brand-drift tell that the
script somehow missed, it is a hard flag, not an observation.

**How to use it:**
- **Designer:** before submitting a slide, scan the slide (and your running deck) against
  this list; fixing a tell at generation time is far cheaper than a revision loop.
- **Design-crit:** treat these as a checklist lens. Naming the tell ("this is
  *card-in-card*") gives the designer a concrete, shared target instead of a vague "feels
  generic."
- A tell is an **observation, not an automatic fail** — some are occasionally the right
  call (a genuinely symmetric comparison, a deliberate centered closing). Name it, say
  why it's likely weakening the slide, and suggest the on-brand alternative.

Several tells are tuned by the [taste dials](taste-dials.md): `template-monotony` and
`wall-of-cards` are exactly what the **VARIANCE** dial sets thresholds for.

---

## Slide-level tells

| Tell | How to spot it | On-brand alternative |
|---|---|---|
| **card-in-card** | A bordered/filled card nested inside another bordered/filled card; boxes wrapping boxes for no structural reason | One level of container. Use whitespace and type hierarchy to group, not nested borders. Cards sit *on* the slide, not inside each other. |
| **hero-less slide** | Squint and nothing jumps out — every element is the same size/weight/color; no focal point | Name one focal element and make it bigger/lighter-display/accented. Every slide answers "where does the eye land first?" (Framework 1). |
| **centered-everything** | Title, body, and footer all centered; symmetric margins on a content slide | Asymmetric 1/3–2/3 split (Framework 5). Centered is reserved for dividers, big-stat, and closing. |
| **symmetric-grid crutch** | A 2×2 / 3×3 grid of equal cards used because it's easy, not because the content is genuinely parallel | If the items aren't truly co-equal, give them a hierarchy: a featured item + supporting ones, or a left-narrative + right-grid split. Reach for `-featured` / `-focal` template variants. |
| **gradient overuse** | The brand gradient on whole sentences, multiple elements, or every title | Gradient text = the last ≤3 accent words of *one* title per slide. It's a spotlight, not a coat of paint. |
| **decorative-only icons** | An icon sits next to every label but encodes no meaning — swap any two and nothing changes | Either the icon carries information (status, category, step) or it's removed. No icon-as-garnish. Lucide outline only. |
| **filler bullets** | Bullets padded to "look complete" — restating the title, or generic ("Scalable, Secure, Reliable") | Cut to the bullets that carry a fact or a claim. Fewer, load-bearing bullets beat a tidy list of nothing. |
| **label title** | Title names the topic ("Architecture", "Budget", "Risks") instead of asserting | Assertion-evidence (Framework 4): "Snowflake decouples compute from storage so analytics scale independently." Cross-ref the assertion-evidence framework. |
| **flattened spatial message** | A message that is inherently spatial (flow, layers, scope, journey, before/after) forced into bullet columns | Author a bespoke SVG (designer's sanctioned exception). "This would land better as a visual" is valid crit. |

## Deck-level tells

| Tell | How to spot it | On-brand alternative |
|---|---|---|
| **template-monotony** | The same template repeats beyond the VARIANCE threshold (`low` ≤3×, `medium`/`high` ≤2×; `high` also forbids adjacent repeats) | Vary templates; use `-asymmetric` / `-focal` / `-compact` variants to break sameness even within one content shape. |
| **wall-of-cards** | The whole deck is card/bullet slides — fewer visual slides than the VARIANCE min, no charts/pipelines/bespoke SVGs, no breathers | Hit the min-visual-slides count for the dial; insert breathers (divider / big-idea / big-stat / pull-quote) on the cadence the dial sets. The single most common slop signature. |
| **no typographic hero moment** | No slide uses a 72–96px display title, a big number, or a large quote anywhere in a 6+ slide deck | Give the deck at least one moment of scale — it sets rhythm and signals intent. |

---

## Brand-drift tells (the model's own aesthetic leaking through)

These are not "generic deck" patterns — they are the default visual language an AI model
falls back to when it stops copying the design system's templates and starts generating
from memory. Any
one of them appearing on a slide means the generation process drifted; the fix is almost
never "adjust the element" but "re-copy the template and re-apply the content."
`validate.py` FAILs most of these mechanically; this list exists so design-crit can name
the residue the regexes can't see.

| Tell | How to spot it | On-brand alternative |
|---|---|---|
| **cream-canvas** | Warm off-white/beige/ivory slide background (`#F5F1E8`-family, `stone`/`amber` washes) instead of the design system's canvas | The pack's canvas (white in most systems) or its canonical cover/section gradients. Nothing warm-neutral that the pack didn't declare. |
| **serif-display** | A serif or humanist display face on titles; any `font-serif` | The pack's declared font stack everywhere, at its lightest display weight. A face the pack didn't declare is drift by definition. |
| **terracotta-accent** | Coral/terracotta/burnt-orange accent color (`#D97757`-family, `orange`/`amber` classes) on text, buttons, or highlights | The brand gradient's accent stop, or the pack's `primary` role. Warm hues exist only where the pack lists them (status dots/pills). |
| **indigo-purple-card** | Cards or heroes filled with an indigo→violet/purple gradient (`from-indigo-500 to-purple-600`) | The pack's canonical brand gradient, on the sanctioned surfaces only (icon badges, chart bars, SVG boxes). |
| **dark-mode-card** | A charcoal/slate-900 card or panel dropped onto a light slide | If the pack's canvas is light, emphasis comes from its `tint` cards, gradient badges, or the type scale — never an undeclared dark panel. |
| **soft-shadow-stack** | `rounded-2xl` + `shadow-lg/xl` floating-card styling | Cards sit flat: the pack's medium radius, a 1px `rule`-role border, or a `tint` fill. The only sanctioned shadow is SVG `<feDropShadow>`. |
| **emoji-icons** | Emoji standing in for icons (📊 🚀 💡) anywhere, including inside SVG | Lucide outline icons, 1.5–2px stroke. No exceptions — the rule survived three prose files but shipped in a snippet once; now it's a validate.py FAIL. |

---

## What this is **not**

Not a taste tribunal. Don't flag a slide because you'd personally lay it out differently,
because it "feels corporate," or because you prefer another color — that's aesthetic
opinion, and the brand already decides color/font/gradient. Flag a tell only when you can
name it from this list and explain how it weakens hierarchy, variety, or message.
