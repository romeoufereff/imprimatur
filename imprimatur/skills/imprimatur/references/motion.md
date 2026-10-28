# deck-motion — §7b Choreography (reference)

How a slide constructs itself when it opens, and how the deck moves between slides. Read on
entering §7b; nothing here applies to a deck that answered **no** to the §1 motion question.

## The decision is made once, at intake

| Where | Value | Effect |
|---|---|---|
| `deck-brief.md` → `- **Motion:** no` / `yes · crossfade · auto` | human record | read by everyone, fallback for the state field |
| `deck-state.json` → `"motion": {"enabled": true, "transition": "crossfade", "steps": false}` | the switch | `assemble_deck.py` picks the two-stage viewer; `choreograph.py` runs; `qa.py` gains the motion row |
| absent / `{"enabled": false}` | default | plain viewer byte-for-byte, `choreograph.py` exits 0 without a browser, zero motion tokens |

A pack without a `motion` block cannot say how its brand moves; `ds_config.py` prints
`motion: off` and the §1 question is not asked.

## What runs, in order

```
§7  assemble_deck.py --deck-dir D                 # two-stage viewer + motion/viewer.js (when enabled)
§7b choreograph.py   --deck-dir D                 # one browser launch: read structure → spec → inject
    choreograph.py   --deck-dir D --summary       # ≤ 3 KB, one line per slide — the only thing you read
§7b motion_harness.py D                           # every element, every 50 ms, against the resting slide — exit 1 on a finding
§8  qa.py --deck-dir D --json                     # + motion row: end state == static, pixel for pixel
```

`choreograph.py` loads each slide static, classifies regions with the pack's
`motion.roleSelectors` (eyebrow, title, subtitle, kpi, bar, arc, connector, chartBlock,
image; `never` = logo, footer strip, decorative washes), detects structural **groups**
(≥ 2 siblings with the same tag + class signature under a flex/grid parent → cards, columns,
list items), measures boxes and orders the beats **hierarchy-first**:

```
eyebrow → title → subtitle → containers (cards, columns) → details (text, list items, images)
→ connectors (arrows draw) → numbers (kpi count-up, bars grow, arcs draw) → EMPHASIS (pop)
```

within a tier top-to-bottom then left-to-right; a group staggers so `items × stagger ≤
staggerCapMs`; the whole entrance fits `entranceBudgetMs` (1600 by default; `templateOverrides`
give the cover more and the divider less). The **emphasis** is the last beat: the brief's
`Emphasis:` sentence matched against region text (`narrative-outline.md`), else a
`data-motion="emphasis"` element, else the loudest number on the slide.

### Vocabulary and variety

| Effect | What moves | Typical role |
|---|---|---|
| `fade` / `fade-up` / `fade-left` | opacity, 24 px travel | eyebrow, text, lists |
| `rise` | opacity + 36 px travel + a 1.5 % scale settle | cards |
| `blur-in` | opacity + blur 10 px → 0 | titles, subtitles, images |
| `wipe-right` / `wipe-up` | clip-path reveal | eyebrows, titles, rows, cards |
| `words` | the title's words arrive one by one (plain-text titles only; accent spans fall back to `fade-up`) | titles |
| `lines-mask` | each rendered line of the title lifts through a clip window, lines ~80 ms apart — the calmest headline reveal; what long titles (> 8 words) take | titles |
| `grow-y` / `grow-x` | scale from the baseline / left edge | bars |
| `draw` | stroke-dash reveal | connectors, arcs |
| `count-up` | the numeric part counts from 0; prefix/suffix stay | kpi |
| `spring` | scale from nothing with `power3.out` and a small rise, never an overshoot | cards, icons, boxes |
| `whip` | an 80 ms appearance + a whip from below (`power4.out`, 0.13–0.2 s) — the waterfall arrival (the hyperframes original is binary; on a projector that reads as flicker) | list items, rows, labels |
| `slam` / `snap` / `rise-rotate` | hero statements: scale 1.5 → 1 with the blur clearing · side-snap with a motion-blur streak (`expo.out`) · rise with a 6° settle (`circ.out`) | cover, divider and closing titles |
| `focus-pull` | depth of field: everything already on stage blurs and dims for a beat while the focal element stays sharp, then refocuses | emphasis |
| `lift` / `settle` | emphasis — only where the personality lets text scale (a nudge out of rest and back). In `corporate` / `premium` the emphasis is NO gesture: the focal element arrives last, after a hold of stillness (titles keep their place; their point is the hold). Any movement of a landed element reads as a shake | emphasis |

**Blur dial** — `motion.blur`: `none` · `subtle` (default, ≈ 40 % of the full amounts) · `full`.
Every defocus in the vocabulary (`blur-in`, the slam and snap streaks, the `focus-pull`, the
zoom-blur and whip-pan transitions) scales with it; at `none` they fall back to blur-free
gestures (`blur-in` → a short rise, `focus-pull` → a settle). Depth of field is a director's
tool for one moment, never the automatic emphasis (Roman, 2026-10-04: "too much blur");
`motion.focusPull: off` turns every focus-pull into a settle on the focal element.

**One motion language per deck (1.6.0).** The pack's `motion.personality` (`corporate` ·
`premium` · `playful` · `energetic`; explicit `motion.language` keys override it) fixes ONE
arrival ease, ONE hero ease (title-card gestures, kinetic text) and ONE move ease (on-screen
travel) for the whole deck, plus the base unit, the hold before the point and the group stagger
rhythm (`corporate` = `power3.out` / `power4.out` / `power2.inOut`, 400 ms, 300 ms, 60 ms). No
beat, scene or slide asks for its own curve: variety lives in the gesture — effect, direction,
stagger origin — never in the curve. The `--summary` opens with the `language:` line; a deck
that showed six curves read as noise (review 2026-10-10, iart / LottieFiles).

**Craft rules the choreographer enforces** (distilled 2026-10-04 from the hyperframes motion
library, whose output Roman benchmarked against): arrivals use out-eases only and never bounce;
speed carries weight (hero 0.5–0.8 s, structure 0.3–0.5,
details 0.15–0.3 — slowest ≈ 3× fastest); a group's build window stays under 0.5 s
(`stagger = min(0.06, 0.5/n)`, ordered from start, centre or edges per slide); directions rotate
per slide (`DIRECTION_SCHEMES`) so not everything enters as "y: 30, opacity: 0"; titles are
kinetic word waterfalls with binary opacity and shrinking gaps; counters run 1.2–1.6 s with the
number growing as it counts; draws overlap ~75 %; nothing starts at t = 0 (0.15 s offset); the hero is on screen by 0.5 s; and ONE ambient motion per slide, varied across slides (camera push,
drift, a slower push, stillness). Added in 1.6.0 from the review of iart-ai, LottieFiles and
Motion: **a reading beat** — the emphasis starts `holdMs` after the last beat has LANDED, never
over an arrival (the hold is added to the budget, not squeezed out of it); **the 1/3 rule** — at
most a third of the animated elements move at once (the `moving=peak/total` column; the
waterfall loosens up to three times before anything is shortened); **one counter at a time** —
KPI count-ups run one after another (0.9 s each when three or more) and the caption under a
number lands after the count settles; **follow-through** — a cinematic card's heading, body and
icon settle a beat after the container (`motion.followThrough`, default on); **entrance–exit
continuity** — the cut that brought the slide in decides where its elements come from (a push →
enter along the push); **grid cascades** — a card grid staggers in reading order with a third of
a step added per row, a group over eight by distance from its reading origin; **dark slides**
move 15 % less (travel and defocus); defocus is capped at 10 px whatever the blur dial says, the
viewer's stage blur at 4 px.

**Scale budget (Roman, 2026-10-10: "too much zoom in / zoom out, and at the end of the motion
the element looks like it flickers").** A scaled text element is re-rasterised every frame and
snaps to crisp pixels when the scale ends; the focal-element probe measured that snap at 6–15
MAE in the last 700 ms (0.000 at rest). The personality therefore carries `scaleIn`,
`heroScale` and `textScale`: `corporate` and `premium` never scale text — `settle`/`pop`
become the same 8 px lift, counters do not grow, `rise` has no scale — and shapes settle from
`scaleIn` (94 %) instead of popping from nothing; the hero `slam` starts at `heroScale`
(1.12); the director's `pulse` and the travel visit's acknowledgement are no-ops there, and an SVG
node whose own `transform` carries a scale, rotation or matrix arrives by opacity alone (GSAP
re-serialises such a transform and drops the native scale — slide 13's icon sat 44 MAE off until
the restore). Word splits are inline spans moved through `top`, pixel-identical to the static
title, restored the moment the entrance completes. The EPAM deck default cut is a crossfade; the zoom survives only where it carries
meaning (`proof` links, the template overrides). `motion_probe.py` prints a `FOCAL element`
line (the emphasis target at full resolution) — judge an emphasis by that number, never by the
whole-frame mean, which hid a 14 MAE flicker behind 0.018.

**Groups and ownership (slide 16, 2026-10-10).** A sibling with a different class but the same
tag and a similar box (the highlighted card) joins the card group — alone it never animated and
sat on stage from frame one. An ordinal number inside a card ("1"…"6", "01") rides with the
card's follow-through, never as a late numbers beat; only quantities count up. Follow-through
never touches a child another beat owns (a counting KPI, a bar): two tweens on one opacity made
the number appear, vanish and reappear.

The pack binds each role to one effect **or a list**. With `motion.variety: rotate` (default)
the choreographer turns the list with the slide number and never repeats the previous slide's
choice for the same role, so two consecutive slides construct differently; `fixed` takes the
first entry everywhere (a brand with one gesture). Override per deck with
`deck-state.json` → `motion.variety`. Bespoke SVG diagrams are read too: boxes become
`svg-card` groups (by parent), labels `svg-text`, stroked paths with a marker (own or
inherited) connectors, dashed arcs `arc`; tables give a header beat and one staggered `row`
group. The `--summary` line shows the chosen effect per beat (`card×3:rise`).

### Levels: `auto` and `cinematic`

`motion.level` in the pack (deck override: `deck-state.json` → `motion.level`):

- **auto** — the entrance only: hierarchy-first beats inside `entranceBudgetMs`, then the
  slide rests.
- **cinematic** — what a presentation should feel like. Pacing becomes a waterfall (each beat
  starts well inside the previous one, gestures 25 % slower, budget × `cinematicBudgetFactor`);
  groups get **parallax** depth (members travel different distances, containers further
  than labels); titles may arrive as **masked words**; and while the slide is on screen an
  **idle** timeline runs: a slow **camera** push toward the emphasis (the content wrapper
  scales to `idle.camera.scale` over `idle.camera.durationMs` with its origin on the focal
  element), **drift** on decorative washes (`idle.drift.selectors`, finite yoyo), optionally a
  **breathe** on the hero. The camera push is OFF in the EPAM pack: a slow scale re-rasterises text every frame
  (measured 0.4 MAE/frame of shimmer at rest, 0.000 without) — it reads as flicker on text slides. Idle motion is killed and every attribute restored the moment the
  slide is left (`to-end`), exported, or checked — the resting slide is still the static slide.

Transitions per slide carry the argument. Precedence: a `deck-state.json` slide override →
the brief's **`Link:`** line (the logical step from the previous slide: `and-also` → crossfade,
`therefore` → push, `but` → whip-pan, `proof` → zoom-blur, `new-act` → push-depth; ignored on
slide 1) → `templateOverrides.<stem>.transition_in` (`zoom-blur` between content, `whip-pan`
into a divider, `push-depth` into a quote or big idea, `light-leak` into the close, `none` for
the cover) → the deck default `motion.transition`. They are written into `index.html`'s
`window.__DECK.transitions` by `choreograph.py`; the summary shows `in=<cut>/<link>`. The viewer
sends `play` to the incoming slide when the cut is ~70 % done, so the hero lands as the stage
settles instead of constructing itself behind a zoom.

### Director scenes — motion that tells the slide's story

The auto plan reveals a slide; it cannot know what a diagram *means*. For slides whose visual is
the argument (`Visual: bespoke | pipeline | chart` in the brief) the **motion-director** agent
(`agents/motion-director.md`, spawned once per cinematic deck at §7b) writes
`<deck>/motion/director.json`: per slide, a one-sentence story and a scene — the world appears,
the protagonist arrives (`enter-from`), travels the diagram (`travel`: a token born behind its
source visits each waypoint along arcs, leaving a trace, revealing what each stop means via
`onVisit`), the consequence lands, the point is made (`emphasis`). `choreograph.py` merges a
scene over the auto plan (the `keep` roles stay as the opening; the rest is replaced; the scene
runs on its own clock), resolves its CSS selectors to positional paths, and the same QA proves
the resting slide is the static slide — every token and trace is removed on exit.

`travel` options: `via` (pass-through waypoints), `curve: "ring"` + `center` (follow the circle),
`trail` or `onVisit` + `visitEffect: "spring"` (the island IS the trace — Roman's slide-3 story),
`end: "stay"`. The scene emphasis starts `emphasisGap` (0.35 s) after the last beat lands.

**How a director reads a slide's story** (the question "how do we understand the storyline
behind a slide?" has three answers, in order of reliability): (1) the narrative brief's `Motion:`
line — deck-narrative writes the visual's storyline in one sentence for bespoke/pipeline/chart
slides, so the story is authored upstream, not reverse-engineered; (2) the **scene graph**
(`scripts/scene_graph.py <slide> --deck-dir D`): nodes with labels and positions, edges with the
nodes they join and the direction their arrows point, free labels, cards and text by role, the
implied flow direction and a protagonist candidate, printed next to the brief's Message / Visual /
Emphasis / Motion in ≤ 3 KB — the input a reasoning step needs, instead of raw HTML; (3) the
director's judgement on top: who is the protagonist, where it starts, what changes, what is left
behind. Several directors can work in parallel, each on `motion/director-<x>.json`; the
choreographer merges `director*.json`.

**The harness (1.6.0, after Roman: "make a visual harness for yourself instead of eyeballing").**
`scripts/motion_harness.py <deck> [slides]` seeks every slide's timeline in 50 ms steps, fires
the completion (the restore), and compares the box of every animated element — each beat's
targets, each group member, the emphasis — against the slide at rest. It reports, per element:
MOVES AFTER LANDING (it reached its resting pixels, then changed again: a gesture on a landed
element, two tweens on one element, a scale settle), LANDS AT THE END (hidden by a stray
from-state until the last frames), NEVER LANDS (a restore miss), SNAP AT RESTORE, BEFORE ITS
CONNECTOR (a node visible before the draw that leads to it has finished), VISIBLE FROM FRAME 0
(targeted but never animated). `--trace` prints every element's distance series; a contact
sheet of the offending frames lands in `<deck>/motion/harness/`. It is the gate after
choreography and after any scene edit: zero findings, or the deck is not done. On its first run
it found everything the second review listed and two things it did not (an SVG icon parked off
its native scale, a director's rays wired to the wrong nodes).

**How the classifier reads a slide (rules added 2026-10-11 from a six-slide pitch deck on a client pack).** Groups form
under flex/grid parents, under `ul`/`ol` (an item carries its own marker), and in plain block flow
when ≥ 2 same-tag siblings are card-sized and carry text — even with different classes per
column (a loose signature: tag + width band). A vertical stack always reads top to bottom (the
centre-out / edges-in origins apply to horizontal rows only); a short stack of ≤ 4 cards arrives
one card at a time (0.6 s apart, the extra time added to the budget) with its content trailing
(title, then text — a wrapper without text of its own is opened one level), and its travel is
capped to the gap between cards so nothing rises through its neighbour. Two aligned groups with
the same count (a row of header bars over a row of bodies, no wrapper per column) interleave
column by column: header, body, next column. A filled bar wearing a label class is a block, not
an eyebrow; table cells are never role targets; a block holding only inline text (a node's
digit in a span) is a text block. In a chart: left-aligned bars of varying width are horizontal
and grow from the left, one by one; an outlined box aligned with them is read with them; marker
lines and arrows draw after the bars; a plain stroked line in any diagram draws in instead of
sitting on stage from frame one. A block taller than 150 px reveals downward (`wipe-down`), not
up. The harness's NEVER ANIMATED finding (ink no beat covers) is what surfaces the next gap.

**Flicker is measured, not debated.** `scripts/motion_probe.py <deck> <slide…>` samples the
live slide frame by frame and reports rest-state change, snap-backs and end-of-entrance jumps.
Three sources were found and fixed this way (2026-10-04): a slow camera zoom re-rasterising
text at rest (0.4 per frame → camera off for text packs), binary word and list appearances (now
an 80 ms ramp), and the un-splitting of a word-waterfall title at the entrance end re-flowing
it by a few pixels (kerning is lost across inline-block boundaries; the split markup now stays
until the slide is left). Viewer transitions were verified at 60 fps: monotonic opacity, no
blinks, no black frames.

Look at a scene as a filmstrip, never as a still:
`python3 {PLUGIN}/scripts/motion_strip.py <deck>/NN-slug.html --out /tmp/NN.png` (8 frames,
deterministic seeks, deterministic Chromium flags so a MAE means the same thing every run). One
exact moment: `NN-slug.html?t=2.4` builds the timeline and holds it there (no autoplay). Re-run
`choreograph.py --files` after editing a scene.

**The motion critic (1.6.0).** At §8 the orchestrator spawns `agents/motion-crit.md` once, read-only,
on a motion deck: five sampled slides (cover, densest, a directed scene, a divider, the closing),
filmstrips and the probe, nine rubric rows scored 1–10 (hook by 0.5 s, one hero per frame,
readable while building, stillness before the point, one language, variety across the deck,
cost from `qa.py`'s `cost` row, rest, and the **silent one-sentence test** on directed scenes:
the story must be readable from the build strip alone). Under 8 is a finding; the judge is never
the builder. `qa.py` reports `cost` per slide (defocus beats, max blur px, clip beats, counters,
`peak_moving`/`moving`) and fails only an extreme entrance (> 6 defocus beats or > 6 counters).

### What it writes

- Into each slide's `<head>`, just before `</head>` (insert-only, idempotent, `--strip` removes it):
  ```html
  <script id="imprimatur-motion-spec" type="application/json">{…beats…}</script>
  <script id="imprimatur-motion" src="motion/motion.js" data-gsap="…gsap.min.js"></script>
  ```
  Selectors are `#slide > :nth-child(n)` paths only — no class or hex can appear, so the static
  check's regexes never match them and Edit-mode class changes never break them. The spec
  carries `body_hash`; a body edit after choreography makes it STALE.
- `<deck>/motion/motion.js` (the runtime) and `<deck>/motion/motion.json` (the deck manifest:
  ordered slides, per-slide specs, the transition — the shape a later video export reads).

### What the runtime guarantees

- **Static under automation.** `navigator.webdriver` (every Playwright run: PDF, PPTX IR, QA),
  `?static=1`, `window.__IMPRIMATUR_STATIC`, `prefers-reduced-motion` → the script returns
  before touching the DOM. Exports never see motion and never fetch GSAP.
- **End state = original DOM.** Inline styles are recorded before the first tween and restored
  at the end; count-ups write the original string back. `check_motion.py` proves it: static
  screenshot vs end-of-timeline screenshot, MAE ≤ `motion.qa.maxMae` (0 = pixel-identical).
- **One paused GSAP timeline per slide** at `window.__timelines[file]` (hyperframes contract:
  seek-safe `fromTo`, transforms + opacity only, no clocks, no randomness) — the bridge to an
  MP4 export later.
- Embedded in the viewer, a slide holds its entrance until the viewer sends `play` (so a
  preloaded slide never animates unseen); opened standalone it autoplays.

## Reading the summary

```
02-cards.html        08-product-cards     7 beats  1600 ms  emphasis=brief  [eyebrow,title,card×3,kpi,kpi,kpi]
03-flow.html         12-process-flow      6 beats  1500 ms  emphasis=-      [eyebrow,title,card×2,card×3,connector×3]
```

Look for: an `emphasis=-` on a slide whose brief named one (the sentence did not match any
region text — add `data-motion="emphasis"` to the element, or set `emphasis_sel`); a slide at
exactly its budget with many beats (dense — fine, or merge with a `data-motion="none"` on the
busiest block); a role that is wrong for the slide (a decorative number counting up → mark it
`data-motion="none"`). Everything else is the pack's taste, not yours.

## Overrides (rare; recorded, never improvised)

| Where | Form | Meaning |
|---|---|---|
| slide markup | `data-motion="none"` on any element | never animate it or its descendants |
| slide markup | `data-motion="emphasis"` | this is the last beat |
| `deck-state.json` `slides[]` entry | `"motion": {"enabled": false}` | this slide stays static (block stripped) |
| `deck-state.json` `slides[]` entry | `"motion": {"emphasis_sel": "#slide > …"}` | explicit emphasis target |
| `deck-state.json` top level | `"motion": {"steps": true}` | build-ins: cards / lists / numbers wait for a keypress (`→`) |
| `deck-state.json` top level | `"motion": {"transition": "push"}` | viewer transition override (`crossfade` · `push` · `zoom-through` · `none`) |

After any override or body edit: `choreograph.py --deck-dir D --files <touched>`, then
`qa.py --deck-dir D --files <touched> --json`.

## Presenting

`index.html`: `→ ↓ Space PageDown` next step, then next slide · `← ↑` previous slide (end
state) · `Home`/`End` · digits + `Enter` · `F` fullscreen · `S` motion on/off (persisted) ·
`R` replay the slide · `index.html?static=1` forces the static deck. Serve over HTTP
(`python3 -m http.server 8934 --directory D`) as at §8; `file://` works too.

## Failure modes

| Symptom | Cause | Fix |
|---|---|---|
| `qa.py`: `motion: motion spec is STALE` | body edited after choreography | `choreograph.py --files <slide>` |
| `qa.py`: `end state differs … MAE` | an element the runtime could not restore (rare: a script in the slide also writes inline styles) | `data-motion="none"` on that element; report if it recurs |
| `qa.py`: `selector resolves to nothing` | DOM restructured after choreography (also STALE) | re-run `choreograph.py --files` |
| slide shows blank for a moment, then static | GSAP CDN unreachable | the runtime lifts the veil and gives up gracefully; point `motion.gsapUrl` at a vendored copy under `motion/` for offline decks |
| viewer keys do nothing | focus inside a slide that has no runtime (a static slide in a motion deck) | click the dark background; slides with the block forward keys themselves |

## Never

- Never write or edit a motion spec by hand, and never spawn an agent to "design the
  animation" — the script reads the structure; your job is the summary and the rare override.
- Never give a slide its own curve, a bounce, or an overshoot; never move the whole frame at once
  (the eye needs an anchor); never animate text the viewer is reading; no particles, glow or
  rainbow gradients; one "wow" per deck. Rules distilled 2026-10-10 from howseen's anti-"AI
  motion" list and iart's restraint pass.
- Never run §7b before the audits are clear, and never on a deck that said no at §1.
- Never add `<script>`s or inline styles to slides to achieve motion; everything the runtime
  needs is in the pack's `motion` block.
