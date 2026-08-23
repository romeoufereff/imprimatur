---
name: deck-review
description: |
  Visual element-level review harness for an assembled deck, plus the refine loop that acts
  on it. Generates a browser page where the reviewer clicks any element on a rendered slide
  and either comments on it or edits it directly — type step, weight, colour, gradient,
  spacing, radius, drag-to-move, resize — offering only values the active design system
  declares. Comments and edits both land in annotations.json; this skill reads them back,
  folds each into the real slide source, re-audits, and regenerates the harness for another
  round. It is the quality gate before export: nothing ships while a comment is open.

  Trigger on: "let me review the slides", "I want to comment on the slides", "open the review
  page", "refine the slides from my comments", "apply my annotations", "let me move things
  around myself", "can I resize that", or when an assembled deck reaches its review round.
license: MIT for the pipeline logic; the design-system pack it drives carries its own terms — see LICENSE.md
metadata:
  author: Roman Iuferev
---

# Deck Review

You run the **visual review and refinement** step. The user looks at the rendered slides,
clicks elements, and writes what to improve. You turn those comments into precise edits, keep
the deck brand-compliant, and loop until the user is happy — and only then is the deck allowed
to move to PDF export.

This replaces vague "looks good / flag issues" acceptance with **element-anchored feedback**.

```
assembled deck ──▶ generate slide-review.html ──┬─▶ comment on an element ─┐
                                                │                          ├─▶ annotations.json
                                                └─▶ EDIT it directly ──────┘         │
                                                    (staged → apply_edits.py)        │
                                                                                     │
        regenerate harness ◀── re-audit ◀── refine / promote ◀────────────────────────┘
                                                                                     │
                                             (zero open items + user accepts) ──▶ PDF export
```

---

## 1 · Generate the review harness

Run the bundled generator over the assembled deck folder. **Prefer the served mode** — it makes
the browser's **Export** write `annotations.json` + `annotations.md` straight into the deck folder
(no Downloads detour, nothing for the user to move):

```bash
python "{PLUGIN}/skills/deck-review/scripts/build_review.py" --deck-dir "<deck folder>" --serve --title "<Deck Title>"
# serves http://127.0.0.1:8765/ and opens the browser; Ctrl+C to stop
```

It reads the `NN-*.html` slides and serves one harness page. Each slide renders in a same-origin
`srcdoc` iframe so the harness can both **render** the slide and **read** its DOM to compute
selectors and place comment badges.

Hand it to the user: *"This opened a review page in your browser. In **Comment** mode, click any
element you want changed and type what to improve. In **Edit** mode you can change it yourself —
type size, colour, gradient, spacing, or just drag and resize it — and I'll fold whatever you do
into the slides properly. Everything saves as you go; tell me when you're done."*

Both modes write to the same `annotations.json`, so there is nothing for the user to export or
move. See §2 for what Edit mode can author and how to promote what comes back.

As soon as the harness is handed over, set `"review": { "offered": true }` in the deck's
`deck-state.json` (create the key if absent). The export hook blocks any export from a deck
with no `annotations.json` and no `review.offered` / `review.fast_track` record — this flag
is the proof the review round happened.

**Standalone fallback:** without `--serve` the generator writes a self-contained
`<deck folder>/slide-review.html` the user can double-click; there, Export downloads to
`~/Downloads` instead (the user then moves it, or tells you the path). Use this only if a local
server can't run. Note `localStorage` is per-origin, so comments made in the `file://` standalone
page do **not** carry over to the `http://` served page — pick one mode per review round.

**Do not hand-build this HTML.** The generator already handles the one thing that breaks naive
versions: slide HTML contains its own `<script>…</script>` (Tailwind, the canvas scaler, ECharts),
so it escapes `</`→`<\/` before embedding. A hand-rolled inline version will corrupt on the first
embedded `</script>`.

**The harness is a SNAPSHOT — restart after every slide edit.** Slides are embedded into the
page at generation time, so edits to slide files are invisible until the server process is
stopped and started again (regenerating on startup). Two gotchas from live use:
- If your preview tooling reports `reused: true` when "starting" the server, it did NOT
  regenerate — stop it first, then start fresh.
- The user's browser tab also caches: tell them to hard-refresh after you restart.

---

## 2 · Edit mode — direct manipulation

The harness has two modes. **Comment** is unchanged: click an element, write what to
improve. **Edit** lets the reviewer change the element themselves — and the change comes
back to you as a precise instruction rather than a description.

An edit is **not** a rival editing path. It is an annotation with a diff attached:
`"make this bigger"` arrives as `font-size: 37px → 46px (ds-h2)`. You still do the
real work in the slide source.

### What the reviewer can change

Everything in the properties panel is built from the **active design system**, read through
`../{PLUGIN}/scripts/ds_config.py` (`editor_vocabulary()`), never hardcoded:

| Control | Vocabulary | Source |
|---|---|---|
| Type step | the pack's whole type ramp, sorted large→small | `fontSize` in the pack's Tailwind config |
| Weight | `typography.allowedWeights` only | `design-system.json` |
| Text / background colour | the pack's full token palette | `tokens()` |
| Gradient | only the pack's named gradients, fill **or** text | `backgroundImage` + `editor.gradients` |
| Align, padding, gap, radius | the pack's spacing steps and radii | `spacing`, `borderRadius`, `editor.spacingSteps` |
| Move / resize | drag + 8 handles, snapped to `editor.gridPx` (Alt = off-grid) | `design-system.json` |

**A value the pack does not declare is a value the panel cannot author.** That is the point:
direct manipulation can't produce the off-brand styling `validate.py` exists to reject.
Gradients carry the pack's own usage rules — decoration gradients are offered as washes but
their **text** treatment is disabled, and a gradient-text run past `maxTextWords` warns.

Two things Edit mode refuses on purpose:
- An element the slide already transforms (rotated chevrons, scaled art) can't be moved —
  our `translate` would clobber the slide's own transform. The panel says so and points at
  a comment instead.
- An element whose CSS path isn't unique is recorded with `selector_matches ≠ 1` and
  **skipped** by `apply_edits.py`, which reports it. Take those as comments.

### Where edits go

Nothing in the harness writes a slide file. Each change is a selector → declaration patch
stored as a `kind: "edit"` annotation in the same `annotations.json` as the comments — one
status lifecycle, one autosave, one export gate — and projected to `edits.json` / `edits.css`
for readability.

```bash
python3 "{PLUGIN}/skills/deck-review/scripts/apply_edits.py" --deck-dir "<deck>"          # materialise
python3 "{PLUGIN}/skills/deck-review/scripts/apply_edits.py" --deck-dir "<deck>" --check  # exit 1 if stale
python3 "{PLUGIN}/skills/deck-review/scripts/apply_edits.py" --deck-dir "<deck>" --strip  # remove entirely
```

`apply_edits.py` writes ONE `<style id="deck-review-edits">` block into each affected slide's
`<head>` — insert, replace, or remove wholesale, so every run is idempotent and the diff is
readable. No DOM rewriting, no external stylesheet (relative paths don't resolve in the
harness's `srcdoc` iframes or under `file://`). Because `extract_ir.py` reads
`getComputedStyle` at the native canvas size and `pdf-export` screenshots the rendered slide,
an override flows correctly into **both** exports — so a deck can be shown to the client
mid-review without the edits going missing.

**Run `apply_edits.py` after every review round**, before you render, screenshot, or export
anything. Until you do, the slide files still show the pre-edit design and you will report
on the wrong thing.

### Promoting an edit — the rule that keeps the deck on-brand

> **The override block is a staging area, never a destination.** Only `open` edits are
> written; resolving one means you PROMOTED it into the slide's real markup.

For each open edit:

1. Read its `decl` and `intent`. `intent` says what the reviewer meant in the pack's own
   language (`type step -> ds-h2`, `gradient text -> ds-brand`, `moved -24px x / 16px y`).
2. Make the change **properly in the source**: a token class (`text-ds-h2`,
   `bg-ds-brand`), a grid or flex correction for a move, a real width — never by pasting
   the override's `!important` declarations into the markup. A `translate` is the reviewer
   showing you where the element belongs; the fix is usually the layout, not a transform.
3. Run **brand-audit** on the slide. An edit that can only be satisfied off-brand is
   `declined` with a reason, exactly like a comment.
4. Mark it resolved, with a note on stdin saying what you folded in:
   ```bash
   echo "promoted to text-ds-h2 on the subhead" | python3 \
     "{PLUGIN}/skills/deck-review/scripts/annotations.py" \
     --file "<deck>/annotations.json" resolve <id>
   ```
5. Re-run `apply_edits.py` — the promoted rule drops out of the block on its own, and the
   block disappears when the last one goes.

Never resolve an edit you have not actually folded into the markup: the override vanishes
with it and the reviewer's change is silently lost.

### The gate

`export_gate.py` already blocks any export while an annotation is `open`, and a staged edit
is open until promoted — so the deck cannot reach PDF or PPTX carrying an override block.
Before declaring a deck review-clean, `apply_edits.py --check` must exit 0.

---

## 3 · The annotations.json contract

The harness exports this shape. It is the only thing you need to refine against:

```json
{
  "deck": "<deck folder name>",
  "created": "<ISO timestamp>",
  "annotations": [
    {
      "id": "a1",
      "slide_file": "03-problem.html",
      "slide_index": 3,
      "scope": "element",
      "selector": "#slide > div.col-left > ul > li:nth-of-type(2)",
      "tag": "li",
      "classes": "text-<prefix>-ink ...",
      "text_snippet": "Batch refresh: once per night (22:00)",
      "comment": "make this the hero stat — it's buried",
      "status": "open"
    }
  ]
}
```

An **edit** is the same shape plus three fields:

```json
{
  "id": "e1", "kind": "edit",
  "slide_file": "03-problem.html", "slide_index": 3,
  "selector": "#hero", "selector_matches": 1,
  "tag": "h2", "text_snippet": "Batch refresh runs once per night",
  "decl": { "font-size": "46px", "line-height": "1.15" },
  "intent": [{ "prop": "font-size", "was": "37px", "now": "46px",
               "note": "type step -> ds-h2 (37px -> 46px)" }],
  "comment": "Direct edit — type step -> ds-h2 (37px -> 46px)",
  "status": "open"
}
```

- **`decl`** is the CSS currently overriding the slide — what you must reproduce properly in
  source. **`intent`** says the same thing in the pack's language and is the better guide.
  **`selector_matches`** is how many elements the selector hit when it was recorded; anything
  but `1` is skipped by `apply_edits.py` and should be treated as a comment.
- **`comment`** is generated from `intent`, so an edit reads like a comment to every downstream
  consumer — `annotations.py`, `annotations.md`, and the export gate all work unchanged.

- **`text_snippet` is your primary anchor** — it's the visible text of the clicked element, so
  you can locate the exact spot in `slide_file` by searching for it. **`selector`** disambiguates
  when the snippet repeats. `scope: "slide"` means a whole-slide comment (no element).
- **`status`**: `open` → `resolved` (you applied it) or `declined` (you chose not to, with reason).

---

## 4 · Refine — the hybrid loop

For each `open` annotation, first **classify** the ask, then act. Always honor the deck's taste
dials and anti-slop tells (`{PLUGIN}/skills/imprimatur/references/taste-dials.md`,
`{PLUGIN}/skills/imprimatur/references/anti-slop-tells.md`) and
read `deck-brief.md` for the deck's voice and anti-references.

### Targeted asks → direct edit + brand-audit re-check
Re-wording, resizing within the type scale, recoloring to a token, moving/removing an element,
fixing a number, tightening copy, swapping an icon. These touch one element and don't change the
slide's structure.

1. Open `slide_file` and find the element. **`text_snippet` is whitespace-normalized** (the
   harness collapses runs of whitespace to single spaces), so don't expect it to match the raw
   source verbatim — the HTML has line breaks, indentation, and sometimes inline tags (`<span>`,
   `<br>`) splitting the text. Search for a **distinctive 3–6 word fragment** of the snippet rather
   than the whole string, then confirm you have the right node using `tag`, the `classes`, and the
   `selector` path (e.g. `selector` ending in `li:nth-of-type(2)` tells you which sibling). If a
   fragment is ambiguous, walk the `selector` structurally.
2. Make the **minimal** edit that satisfies the comment. Stay inside the design system — tokens
   only, weights 300/400/700, body ≥20px, gradient ≤3 accent words, etc.
3. Run **brand-audit** on that slide (its `validate.py` pre-pass + the checklist). It must
   pass before you mark the annotation `resolved`. If the edit pushed density over the dial budget
   or broke a rule, fix it now — don't ship a regression to satisfy a comment.

### Structural asks → route through deck-designer
"Turn these 4 cards into a 2-column AS-IS/TO-BE", "split this into two slides", "this should be a
chart / a bespoke diagram", "reorder the slide", "this needs a different template". These change
layout or visual mode.

1. Treat the comment as a **brief delta** for that slide and hand it to **deck-designer** (which
   re-selects a template or authors a bespoke SVG), then run **brand-audit** → **design-crit**
   per the normal revision loop. If the requested visual is (or becomes) a donut / pie / gauge /
   **cycle / ring** / hub-spoke / funnel / pyramid / chevron-process / matrix / venn / roadmap
   shape, deck-designer must delegate to `{PLUGIN}/skills/svg-reconstruct/` per its Bespoke SVG rules —
   it computes node positions, arc gaps, and **arrowhead landings** by trigonometry. This applies
   mid-review too: a hand-tuned ring cost a real deck 3 revision rounds (triangle → guide ring →
   arrowhead geometry) because this routing was skipped while deck-review was the active context.
2. Mark `resolved` once the new version passes both audits.

### When you won't apply a comment
If a comment conflicts with a brand rule, the audience, or the deck brief (e.g. "make the body
text 10px", "use red for emphasis everywhere"), mark it `declined` with a one-line reason and
surface it to the orchestrator/user rather than silently dropping it.

**Record what you did.** For every annotation, set `status` and add a short `resolution` note
("reworded title to assertion", "split into 03a/03b", "declined: 12px below the 14px floor").
Write the updated annotations back so the next harness shows the resolved badges (green).

**Use the bundled CLI — never write ad-hoc scripts for this.** `scripts/annotations.py`
handles the whole lifecycle in one Bash call per operation, with the note read from stdin
so apostrophes and quotes in prose never fight shell escaping:

```bash
python3 "{PLUGIN}/skills/deck-review/scripts/annotations.py" --file "<deck>/annotations.json" list --open
python3 "{PLUGIN}/skills/deck-review/scripts/annotations.py" --file "<deck>/annotations.json" show a7
echo "Reworded title to an assertion; re-audited, passes." | \
  python3 "{PLUGIN}/skills/deck-review/scripts/annotations.py" --file "<deck>/annotations.json" resolve a7
echo "12px is below the 14px floor — kept at 14px." | \
  python3 "{PLUGIN}/skills/deck-review/scripts/annotations.py" --file "<deck>/annotations.json" decline a8
```

(A prior review cycle burned ~6k tokens writing nine one-off Python scripts for exactly
this — the CLI exists so that never happens again.)

### Proof standard — measure, don't eyeball

Spacing and alignment comments ("center X against Y", "reduce the gap", "these don't line up")
are closed with **numbers, not impressions**. Use `scripts/render.py` — don't re-type inline
Playwright snippets:

```bash
# WebKit screenshot (Safari engine — catches SVG/gradient bugs Chromium tolerates):
python3 "{PLUGIN}/skills/deck-review/scripts/render.py" "<deck>/02-slide.html" --out /tmp/s.png
# Zoomed crop for connector/arrowhead geometry:
python3 "{PLUGIN}/skills/deck-review/scripts/render.py" "<deck>/02-slide.html" --out /tmp/zoom.png \
  --crop 680,280,580,340 --zoom 3
# Pixel-sample a column to PROVE a stroke/gap exists (this caught the Safari
# zero-width-bbox gradient bug — see design-system references/known-issues.md §5):
python3 "{PLUGIN}/skills/deck-review/scripts/render.py" "<deck>/02-slide.html" \
  --sample-column 960 --sample-range 500,620
```

1. **Numeric proof:** load the slide in Playwright at 1920×1080 and compare
   `getBoundingClientRect()` values of the paired elements — for "center A against B" the
   vertical-center diff must be **0px**. If two columns must share row alignment, restructure
   into one shared grid (design-system SKILL.md § Layout rules) instead of nudging margins
   until it "looks close".
2. **Visual artifact:** render just that slide to PDF (pdf-export, single-file glob), then
   `qlmanage -t -s 1400 -o <dir> <pdf>` for a thumbnail you can show the user. The macOS
   Quick Look thumbnail is the reliable render; browser-preview screenshot tools have produced
   wrong-scale captures and must not be the basis of an "it's aligned now" claim.

Never tell the user an alignment fix "looks right" based on squinting at a thumbnail — a real
review caught up to 38px of drift behind a claim like that. Run the measurement, then show
the thumbnail.

### Step-by-step mode (on request)

When the user asks to go comment-by-comment ("do it step by step"), switch cadence:

1. Apply exactly **one** comment.
2. Validate + measure (proof standard above), render that one slide, show the thumbnail.
3. Wait for the user's confirmation before touching the next comment.
4. Live-chat follow-ups during a step ("now make it 36px", "also move that box down") belong
   to the same annotation — fold them into its `resolution` note rather than minting new IDs.

---

## 5 · Re-review and the PDF gate

After a refine round:

1. **Re-run `apply_edits.py`** (§2) so promoted edits drop out of the override block and any new
   ones are materialised, then **regenerate** `slide-review.html` (step 1) so the user sees the
   updated slides with resolved comments marked. Ask them to review again — they may close out comments, reopen some, or add new.
2. **Loop** until there are **no `open` annotations** and the user explicitly accepts.
3. Only then is the deck cleared for **pdf-export**. The orchestrator owns the actual gate; your
   job is to report the deck as "review-clean" (zero open) or "still has N open comments".

Never let a deck go to PDF with open comments — the whole point of this step is that the printed
deck reflects the user's markups. And never let one go to PDF still carrying a
`<style id="deck-review-edits">` block: `apply_edits.py --check` must exit 0, which it does only
once every staged edit has been promoted into real source.

---

## Your place in the pipeline

```
orchestrator (assembles deck, owns the gate)
  └─▶ §8 HTML preview (orchestrator, inline)
       └─▶ YOU: deck-review (generate harness → read annotations → refine → re-review)
            ├─▶ brand-audit        (re-check every touched slide)
            └─▶ deck-designer → audits  (structural asks only)
                 └─▶ [zero open + accepted] ──▶ pdf-export
```

You don't decide the deck is done — the user does, by clearing their comments. You make their
comments real, keep the deck on-brand, and hold the line on the PDF gate.
