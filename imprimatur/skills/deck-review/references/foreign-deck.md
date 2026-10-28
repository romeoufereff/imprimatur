# Foreign decks — design review and restyle of a deck that is not an imprimatur folder

A **foreign deck** is one HTML file holding every slide, built by someone else with its own
slide engine (a colleague's interactive presentation, a client's export). It has no
`deck-state.json`, no `NN-*.html` files and no `#slide` canvas per file, so `qa.py`,
`plan_check.py` and the click-to-comment harness do not apply. What does apply is the same
design judgment and the same measurements, run on renders and on the live file.

The loop below is the one that took two such decks (28 slides and an 11-slide exec cut)
through a full designer cycle on 2026-10-26: three critique passes, owner rulings, two
revision rounds, an in-browser QA script.

## The loop

1. **Render every slide, fully revealed.**

   ```bash
   python3 "$PLUGIN/skills/deck-review/scripts/render_deck.py" deck.html review/r1 \
     --prefix full --hash '#slide={n}' --reveal '.reveal:shown' --chunk 14
   ```

   Navigation comes from the deck: a hash route (`--hash '#slide={n}'`, reveal.js
   `'#/{i}'`), else the active class is toggled (`--slide`, `--active-class`). Build steps
   are shown at once with `--reveal SEL:CLASSES` (reveal.js: `'.fragment:visible'`).
   `chunks.txt` lists the PNGs in groups of at most 14.

2. **Critique in parallel, from the PNGs only.** One `design-crit` per chunk, all spawned
   together. The prompt opens with `FOREIGN DECK`, names the pack the deck is being moved
   to and lists that chunk's PNG paths. No `plan_check.py`, no `qa.py`, no deck HTML. Each
   critic returns per-slide verdicts (`REDESIGN` / `POLISH` / `PASS`, severity 1–5) and the
   global patterns it saw.

3. **Merge into one findings file** next to the build (`review/design-crit-<date>.md`):
   the weakest slides (REDESIGN, then POLISH ≥ 3), the **global patterns, one fix each**
   (most findings repeat across slides: connector colours, an accent with no single
   meaning, box fills that ignore the legend, too many box styles, clearance to the footer,
   orphans, decorative marks), and the concrete asks per REDESIGN slide. Where critics
   disagree, say so; that disagreement becomes a ruling.

4. **Ask the owner for at most four rulings**, recommended option first:
   - **depth**: global rules only · global rules + rebuild the worst slides · everything;
   - **colour meaning**: what the accent means (the critics will disagree on it);
   - **copy**: layout only, or wording changes allowed (a colleague's deck is usually layout only);
   - **cover**: an exec cut often opens on its densest diagram and needs a cover.

5. **Rebuild in a separate per-slide stylesheet.** Global rules go into the restyle (the
   skin); every per-slide layout rebuild goes into its own stylesheet appended last, one
   commented block per slide (`/* full 08: … */`), so the colleague's source stays theirs and
   a new version of their file takes the same rebuild. Apply the diagram vocabulary
   (`agents/design-crit.md` § Diagram vocabulary): cards built exactly like the pack's card
   templates (fill, border, radius, padding — copy them, do not invent a "systematic" card;
   the 3px top-stripe card invented on 2026-10-26 passed two critique rounds and the owner
   rejected it), one meaning per colour, at most three box styles, fills that follow the
   legend, one connector colour with dashed `muted` exception paths, flow text top-aligned,
   no stripes, decorative marks or shadows. Check type density too: a wider brand font in
   the original sizes reads crowded (known issue 4).

6. **Re-critique once**, on fresh renders of the rebuilt slides plus a spot check of the
   rest. Fix what it finds.

7. **Then QA, by script:**

   ```bash
   python3 "$PLUGIN/skills/deck-review/scripts/qa_deck.py" deck.html \
     --hash '#slide={n}' --reveal '.reveal:shown' --footer '.footer-row' --allow review/known.txt
   ```

   Zero findings, or each one accepted in `known.txt` with its reason (a verified false
   positive, a deliberate choice). The text floor defaults to the pack's floor scaled to the
   deck's stage width. Then show the owner the renders: the critics are not the last word on
   whether the deck looks like the pack.

## The tools

| Tool | What it does |
|---|---|
| `scripts/render_deck.py` | PNG per slide, fully revealed and frozen; waits two frames + `--capture-delay` before each capture; `--chunk N` writes `chunks.txt` |
| `scripts/qa_deck.py` | Headless run of `qa_deck.js` over every slide; `--json`, `--allow`, `--slides 4-7` |
| `scripts/qa_deck.js` | The checks (`fit`, `svg`, `bars` = accent stripes, `rows` = one short card, `pad` = text cramped against a rounded card, `minfont`), also usable in the browser console while rebuilding: `__qa.outline()` (every box on the slide with stage geometry, the input to a layout rebuild), `__qa.spillers(root, label)` (each spilling text with the largest size that fits), `__qa.typeScale(root, 0.82)` (try one body-text factor live), `__qa.setCss(css)` (try a rebuild live), `__qa.cats(result)` (findings grouped by shape) |

Every check states its rule at the top of `qa_deck.js`. The same lessons run on imprimatur
slides through `scripts/check_diagram.py` (in `qa.py`).

## Known issues when restyling someone else's CSS

Each of these cost a revision round on 2026-10-26.

1. **Id-keyed rules beat your class overrides.** A colleague's `#slide-7 .run-check { … }`
   outranks any `.run-check` rule you add, `!important` or not, once theirs is
   `!important` too. Prefix per-slide rebuilds with `:is(#slide-N, .alias-N)`: the id gives
   the specificity, and the alias class covers copies of the slide elsewhere (an exec cut's
   backup copies carry a different id).
2. **`:not()` and `:has()` add specificity.** `.flow .node:not(.dark):has(.mode-u)` is
   (0,4,0). A later, plainer "focal tint" rule silently loses to an earlier generic
   white-card rule built with `:not()`. Give the focal rule the same `:not()` chain, or
   measure the computed style instead of trusting source order.
3. **A latent `gap` switches on.** A `gap` on a `display:block` element does nothing until
   you make that element a grid or flex box; then the old value spaces your new layout.
   Set `gap` explicitly in the rebuild.
4. **A wider brand font overflows fixed geometry and reads dense.** Swapping the deck's font
   for the pack's (a wider face at the same size) overflows fixed-height boxes, and even
   where it fits, 20–24 px body text in a wider face reads crowded. Per box, measure the size
   that fits (`__qa.spillers`) and accept 1–2 px rather than cutting the owner's copy. For
   the whole deck, one factor for all slide-body text (0.82 on 2026-10-26; titles, legend
   and footer row unchanged), applied at load, floored at the pack minimum, SVG `<text>`
   included or the labels end up oversized. Read every original size first, then write, so
   nothing is scaled twice (`__qa.typeScale` does exactly this; bake the same logic into the
   restyle).
5. **Copy the pack's cover, not the deck's.** Adapting a `clip-path` notch from the
   original cover produced a stepped "stairs" panel; the pack cover is a clean full-height
   image panel. Covers carry no page number.
6. **Strip whole class tokens only.** A build step that removed the word "slide" from class
   names glued the rest together (`slide-header` → `-header`). Split the class attribute
   into tokens and drop the token, never a substring.
7. **Insert before the LAST `</body>`.** The deck's own JavaScript held four `'</body>'`
   string literals; `str.replace('</body>', …, 1)` injected the script into one of them.
   Use `rfind` and check a `</html>` follows.
8. **A pipeline hides a failing step.** `python skin.py … | tail -1 && cp …` copies a stale
   file when the script fails, because the pipeline's status is `tail`'s. Run build chains
   with `set -o pipefail`, or without the pipe.
9. **One short card.** In a grid row, the grid stretched each wrapper `div` but not the card
   inside it, so one card ended higher than its neighbours. Give the card `height:100%`
   (border-box) or make the card itself the grid item; `qa_deck.js rows` finds it.
10. **New cards need padding.** Text that sat in a plain block keeps its zero padding when the
   block becomes a card; `qa_deck.js pad` flags text within 8 stage px of a rounded card's edge.
11. **Measurement pitfalls** (all handled by `qa_deck.js`; listed so a hand-written probe does
   not repeat them): a "box" needs a fill or borders on 3+ sides; screen-reader-only text
   is excluded (by class, or by the 1 px clip pattern); the freeze needs a selector strong
   enough to beat the deck's own `!important` transitions, or you measure mid-fade; open
   every `<details>`; check text against the footer row and the slide edge; test connectors
   at every point including their ends, with no inset on the glyph band; arrow tips buried,
   floating, or deliberately exiting; connector strokes ≥ 3:1; the smallest rendered text
   through SVG and CSS transforms; and wait two frames before a screenshot after a style
   change, or the capture can show the previous frame.
