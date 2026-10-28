# Amendment patterns: how a correct-looking change still breaks a pack

Every pattern below was found by hand, in a real pack, after a change that looked right in
isolation. None of them are exotic — they are what happens when a Tailwind-Play-CDN-plus-flat-
HTML-files pack (the shape this skill's packs take) accumulates enough templates that "change
the token" and "the change actually reaches every template" stop being the same fact. Read this
before a nontrivial amendment; `scripts/audit_pack.py` automates the mechanical half of several
of these, but the reasoning is worth having independently of the tool.

Written brand-agnostic: `{prefix}` stands for the pack's token prefix (e.g. `acme-`), and
example class names are illustrative, not any one brand's actual tokens.

- [Token & config](#token--config)
  - [Token name collisions across Tailwind categories](#token-name-collisions-across-tailwind-categories)
  - [Token-only change: the fix that never reaches templates](#token-only-change)
  - [Editing an inline config block: brace-match, don't anchor on a pattern](#editing-an-inline-config-block)
- [Layout](#layout)
  - [flex-1 inside `min-height: auto`](#flex-1-inside-min-height-auto)
  - [flex-1 on a list pools slack into one visible hole](#flex-1-on-a-list-pools-slack-into-one-visible-hole)
- [SVG](#svg)
  - [height:100% resolves against content-box, not border-box](#svg-height100-and-the-content-box)
  - [WebKit won't paint objectBoundingBox gradients on straight lines](#webkit-gradient-trap)
  - [Paint order: all boxes first, all connectors last](#svg-paint-order)
- [Typography](#typography)
  - [A type scale is for prose — diagrams and chrome need their own tiers](#type-scale-is-for-prose)
  - [Fixed-offset markers de-align after a scale change](#marker-realignment)
- [Accessibility](#accessibility)
  - [Chip/tag contrast: colour goes in the tint, not the text](#chip-contrast)
- [Assets](#assets)
  - [Raster images: data URIs, not file paths](#raster-images)
- [Decoration](#decoration)
  - [Left-accent bars and their two legitimate escape hatches](#left-accent-bars)

## Token & config

### Token name collisions across Tailwind categories

**Symptom:** an element authored as `text-[14px] {prefix}-body` (or any explicit size paired
with a colour utility of the same name) silently renders at the WRONG size or weight, with no
error anywhere.

**Root cause:** Tailwind's `theme.extend` lets a pack define, say, `colors['{prefix}-body']`
*and* `fontSize['{prefix}-body']` — a designer reaches for a memorable name and doesn't notice
it's already used one category over. Both generate a real CSS rule for `text-{prefix}-body`
(colour utilities and font-size utilities share that class prefix), and whichever rule Tailwind
emits last in the stylesheet wins the cascade — regardless of source order in the config, and
regardless of any explicit size class the author also wrote.

**The general rule:** a token name is only safe to reuse across categories that generate
*different* utility prefixes. `colors` overlaps with `fontSize` and `backgroundImage` (both
`text-*`/`bg-*` respectively also come from `colors`); `letterSpacing` (`tracking-*`) and
`borderRadius` (`rounded-*`) don't overlap with either. `audit_pack.py`'s collision check
encodes exactly this — it only flags a shared name when the categories involved actually
produce the same class.

**Fix:** rename one of the colliding tokens, or (if truly unified) remove the duplicate
definition and let the surviving category own the name. Never re-introduce a name that once
collided without checking the category-prefix table above.

### Token-only change

**Symptom:** reviewers keep saying slides look sparse or the type feels too small; raising the
values in `tailwind.config.js` doesn't fix it, and months later the same feedback returns.

**Root cause:** the templates never *used* the token. A census across one real pack found over
1,400 hardcoded `text-[Npx]` sizes, most of them below the token floor — the config had been
raised "after a full review," but that pass changed the tokens and nothing else, so every
template that hardcoded its own pixel value never picked up the change. The config was correct.
Almost nothing downstream read it.

**Why this matters more than it looks like it should:** a design system's whole value
proposition is that changing one number in one file changes the deck. A pack where most
templates bypass the token system with literal values doesn't have that property, even though
`design-system.json` and `tailwind.config.js` look perfectly correct on inspection — the defect
is invisible unless you look at what the *templates* actually contain, not what the config says
they should contain.

**Fix, in order:**
1. Raise the token, progressively — a flat multiplier makes a large display size ridiculous and
   a small caption negligible; scale each step by how much headroom it actually needs.
2. Migrate every template onto the token — grep for raw `text-[Npx]` and replace with the
   class. This is the tedious part and the part that actually matters.
3. Add (or verify) a rule that fails on raw `text-[Npx]` below some size floor, so the census
   can't quietly regress again. Nothing else stops a third round of "we raised the numbers and
   nothing changed."

**Absorbing a scale increase:** bigger type overflows crowded slides. Tighten leading and
padding first, cut copy second, and only drop a size rung for a genuinely dense diagram — never
shrink prose below the floor to make it fit.

### Editing an inline config block

**Symptom:** after a scripted find/replace across many templates, `validate.py` (or any
mechanical check) still passes, but the deck looks subtly wrong — canvas size drifted, a
gradient disappeared, letter-spacing reset.

**Root cause:** a regex anchored on a specific closing-brace pattern (`\n      },\n`, say)
assumes every file indents its inline config identically. A file indented two spaces deeper than
the others has its *later* closing brace matched instead, and the replacement silently deletes
everything between — an entire category block gone, invisibly, because most validators only
check tokens that are *present*; a deleted block is invisible to a check that never looks for
absence.

**Fix:** parse with actual brace-matching (count `{`/`}`, don't pattern-match a specific
whitespace shape), or edit through a real script that reports its own brace-balance before and
after. Whatever the method, diff `{` and `}` counts pre/post-edit as a cheap independent check —
that alone would have caught the failure described above.

## Layout

### flex-1 inside min-height:auto

**Symptom:** a `flex-1` child that should cap its height to the available space instead grows to
fit its own content and overflows the slide canvas — clipped silently by an `overflow:hidden`
wrapper, no console error, content just vanishes past the canvas edge.

**Root cause:** CSS flexbox's default `min-height: auto` resolves to the element's min-content
size, which overrides `flex-1`'s shrink behaviour. This isn't fixed by touching the one
overflowing element — **every** flex container between it and the row meant to constrain it
needs `min-height: 0` (Tailwind: `min-h-0`), not just the innermost wrapper. Fixing only the
deepest one leaves its parent still relying on `auto`.

**Fix:** when a `flex-1` element isn't actually capping height, add `min-h-0` to every `flex`
ancestor in the chain, not just the element itself.

### flex-1 on a list pools slack into one visible hole

**Symptom:** a slide passes every mechanical gate — tokens, contrast, overflow, collisions — and
still looks unfinished: a large empty band between the last list item and something pinned
below it, or trailing space after the last row of content.

**Root cause:** a full-height `flex flex-col` column with a `flex-1` list inside makes that ONE
child absorb all the column's surplus height. A list renders top-packed, so the absorbed surplus
becomes visible empty space at the bottom. Nothing about this trips a mechanical gate — nothing
overflows, nothing collides, nothing is off-brand. **No mechanical check measures emptiness.**

**Fix, roughly in this order:**
1. Is the content genuinely too thin for the canvas? Redistribution can't remove surplus, only
   move it — bring the content to a realistic density instead.
2. Is the list top-packed with real content below it? Add `justify-between` beside the `flex-1`
   so items distribute down the column.
3. Is the surplus inside a fixed-height card? Wrap the card's *body*, not its header, in
   `flex-1 flex flex-col justify-center`.
4. Is a diagram or table simply too small for its space? Scale the element, not the whitespace.

**What not to do:** `justify-center` on a list sitting above something bottom-pinned just splits
one hole into two smaller ones — same total slack, no real fix. And beware false positives: a
centred side panel, a corner-quadrant layout with a diagram in the middle, or a deliberately airy
breather slide (a cover, a pull-quote) are *supposed* to have empty space — measure whether the
region is also empty of rendered ink before calling it a defect, not just whether text runs stop
short.

## SVG

### SVG height:100% and the content-box

**Symptom:** an `<svg class="w-full h-full">` inside a padded flex wrapper renders shorter than
expected, and `preserveAspectRatio="xMidYMid meet"` letterboxes the width away even though the
viewBox aspect ratio looks right.

**Root cause:** CSS percentage heights resolve against the containing block's **content box**,
not its border box. If the wrapper has its own padding, that padding is silently subtracted from
the height available to a `height:100%` child — a viewBox tuned against the wrapper's own
measured height will be wrong by exactly the padding amount.

**Fix:** when computing a viewBox aspect ratio, measure the rendered `<svg>` element's *own* box
(the browser has already done the content-box subtraction for you), not the wrapper's. Also
check the wrapper isn't using `items-center`, which overrides the default `stretch` and stops a
`h-full` child from stretching at all.

### WebKit gradient trap

**Symptom:** a connector line styled `stroke="url(#grad)"` renders fine in Chromium but is
**invisible in Safari** — only a solid-fill arrowhead shows. Screenshots taken in a Chromium
harness all pass; a user opening the same file in Safari reports the line missing.

**Root cause:** a perfectly vertical or horizontal path has a zero-width (or zero-height)
bounding box. SVG gradients default to `gradientUnits="objectBoundingBox"`, which is undefined
on a degenerate bbox — WebKit paints nothing; Chromium paints anyway, leniently. This is a real,
measured divergence between engines, not a hypothetical one.

**Fix:** give any gradient used on an axis-aligned path absolute coordinates —
`gradientUnits="userSpaceOnUse"` with explicit `x1/y1/x2/y2` — rather than leaving the default.
Bonus: a multi-stop gradient then reads consistently across every path using it instead of
restarting per segment. **Verify bespoke SVG in WebKit specifically**, not only Chromium; this
class of bug is invisible in the more permissive engine.

### SVG paint order

**Symptom:** connector arrowheads look clipped or half-missing where they meet a destination
node.

**Root cause:** SVG has no z-index — document order is paint order. Interleaving box, connector,
box, connector means each destination box paints *after* the connector reaching it, covering the
arrowhead where it touches the border.

**Fix pattern:** structure a diagram's SVG as `<defs>` → every node (rect/text) → every connector
path → every arrowhead. For anything sideways-fanning within a short vertical drop, a rounded
right-angle elbow (`L … Q … L`) enters its target box straight-on; a smooth bezier fanning
sideways strikes at an angle instead. Independent arrowhead `<polygon>`s (rather than
`marker-end`) keep the line-to-triangle gap independently tunable.

## Typography

### Type scale is for prose

**Symptom (typically surfaces right after a scale raise):** SVG labels sit "outside the shapes"
that used to contain them, numerals spill past their circles, and legends render bigger than the
content they annotate.

**Two distinct causes, one shared mistake — applying one type ladder to everything:**

**(a) SVG text doesn't live in a flow box.** It sits in fixed geometry (rects, circles, rings)
that does not grow with the type scale. Raising an SVG `font-size` attribute without re-fitting
the geometry around it pushes labels straight out of their shapes.

> **Rule:** diagram text is not slide prose. Give it its own, lower floor from the pack's
> `typography.minFontSizePx`, and re-fit the surrounding shape rather than shrinking the label
> back down when it no longer fits.

**(b) Chrome must not outrank its content.** Legends, source notes, and tag pills annotate the
content next to them — if they render larger, the eye lands in the wrong place first.

> **Rule:** chrome sits at or below the body size of whatever it annotates. Check the *rendered*
> size, not the class name — a legend at 28px next to 18px grid cells is wrong even if both
> "look like tokens."

Also worth keeping: a gradient spanning both an HTML element and an SVG shape has to match
stops in **both** places. A mismatched mid-stop between a card's CSS gradient and its SVG
counterpart produces a visible seam exactly where the two meet, read as an unintended border.
Sample pixels across the join to confirm the delta is actually zero; don't eyeball it.

### Marker realignment

**Symptom:** after any type-scale change, bullet dots, tick marks, and number badges all look
slightly high or low against their sibling text — individually it reads as sloppiness, across a
whole library it's one systemic bug.

**Root cause:** markers commonly align to their sibling text's first line with a hand-tuned
`margin-top`, set by eye at the *old* line height. Raising the scale shifts every one of them
out of alignment by roughly half the line-height delta.

**Fix — measure, don't eyeball (the error is a handful of pixels, invisible at a glance):**

```js
const mb = marker.getBoundingClientRect();
const r = document.createRange(); r.selectNodeContents(siblingText);
const first = [...r.getClientRects()][0];
(mb.top + mb.height / 2) - (first.top + first.height / 2)   // want ~0
```

**Rule:** any type-scale change must be followed by a marker-alignment sweep across every
template using that marker pattern — this is systemic, not a one-off fix.

## Accessibility

### Chip contrast

**Symptom:** small coloured text in a status chip or tag reliably lands at 3–4.5:1 against its
background — under the WCAG AA floor for text that size.

**Root cause:** a category/status colour placed directly on 14–16px text is fighting the fact
that most brand accent colours simply aren't dark or light enough, at that weight and size, to
clear 4.5:1 on a light or dark surface without distortion.

**Rule:** in a chip/tag/pill at label sizes, the category or status colour lives in the **tint
background, the border, or a small dot** — the label text itself stays a neutral ink colour.
Colour-as-small-text is the pattern that fails; colour-as-background or colour-as-accent-dot is
the one that doesn't. Reserve an exemption (a documented attribute, checked by whatever
validator the pack's engine runs) for genuinely decorative oversized text — ghost numerals,
watermark quotes — never for content text.

## Assets

### Raster images

**Symptom:** a slide with `<img src="assets/foo.png">` renders fine opened directly, but 404s
inside a served review harness or a `file://` standalone viewer.

**Root cause:** a slide embedded in an iframe or opened as a bare file has no document URL of its
own to resolve a relative path against — there is always at least one pipeline context (a review
harness, a `file://` open, a PDF export) where a file-path image reference cannot resolve.

**Fix:** embed raster images as `data:image/png;base64,…` at generation or amendment time. The
size cost is negligible at slide scale, and the slide becomes genuinely self-contained across
every context it might be opened in.

## Decoration

### Left-accent bars

**Pattern many brands ban outright:** a purely decorative `border-l-2/4/8` on a card or callout,
used to colour-code a category without any real information being drawn. It reads as generic
"AI-dashboard" styling rather than a brand's own visual language, and shows up repeatedly once a
pack starts flagging it.

**What most brands use instead:** colour-coded headers (text colour, not a side bar) for
category grouping; a plain uniform border or a solid tinted fill for card differentiation;
whitespace and grid gaps — or at most a plain top rule — for section separation.

**Two legitimate escape hatches**, because not every left border is decorative:

- A genuinely functional line — a Gantt "now" marker, a milestone rail — is real geometry, not
  decoration. Mark it with an explicit attribute the pack's rules recognise (commonly
  `data-accent-bar="ok"`), or give the CSS rule an accompanying `width:0` (the signature of a
  line being *drawn*, not a box being *decorated*). `audit_pack.py` checks for both.
- A filename-based allowlist for untouched stock templates is fine as a stopgap but doesn't
  survive a copy — a deck slide copied from a sanctioned template under a new name will fail the
  check every time. Prefer the attribute/CSS escape over a filename list wherever the pack's
  validator supports it.
