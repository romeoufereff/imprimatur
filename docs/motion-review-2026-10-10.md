# Motion design review for imprimatur — 2026-10-10

What five public motion-design repositories teach, measured against imprimatur 1.5.9's
deck-motion module (`choreograph.py`, `motion/motion.js`, `motion/viewer.js`, the motion
director, `references/motion.md`). Every finding names the code it is about, the source it
comes from, the proposed change, its effort, and how it is verified. Section 5 is a release
plan; section 4 says what not to adopt and why.

## 0. Status — shipped as 1.6.0 on 2026-10-10

All twelve proposals are implemented in one release (Roman: one release, not three). Bench:
a 17-slide client deck on the EPAM pack (copied to the scratchpad, never the
original) re-choreographed with the new engine.

| Check | Before (1.5.9) | After (1.6.0) |
|---|---|---|
| `qa.py` motion row, 17 slides | MAE 0, 0 fails | MAE 0, 0 fails (follow-through, lines-mask, aria in play) |
| `motion_probe` rest-state change, slides 01 / 15 / 16 | 0.036 / 0.000 / 0.000 | 0.033 / 0.000 / 0.000 |
| Curves used deck-wide (arrival + hero) | 6 (`power2/3/4.out`, `circ`, `sine`, `expo`) | 2 (`power3.out`, `power4.out`) + `power2.inOut` for moves |
| Six KPI counters on slide 16 | all six running together | one after another, 0.9 s each |
| Slide 09 (table), elements moving at the peak | 6 of 7 | 3 of 7 |
| Emphasis start | 0.8 × the last beat's duration (over the arrival) | after the last landing + 300 ms hold |
| Title on slide 15 during the build | dimmed to 55 % for 2 s (pre-existing `lift` from-state) | full ink from arrival; `lift` is position-only |
| "Flicker at the end of the motion" (Roman) | the `settle` emphasis scaled the focal text 103 % → 100 % for 0.6 s, re-rasterising it every frame; a frame-exact probe showed the restore moment itself never snaps (0.000 before and after) — the shimmer was the scale | corporate and premium never scale text: `settle`/`pop` are an 8 px lift, counters do not grow, springs on text-bearing cards rise without scale; `motion_probe` now reports a FOCAL line and `scratchpad/end_snap.py` measures the three end frames exactly |
| Slide 16, card 6 (highlighted, different class) | on stage from frame one (not in the sibling group) | joins the card group |
| Slide 16, numbers 2–5 | appear, vanish, reappear at the end (owned by two tweens) | ride with their card |
| Cut between content slides | zoom-blur on every cut | crossfade; zoom only for `proof` links and template overrides |

**Second review (Roman, same evening, twelve slides)** — "still zoom in / out", "moves up / shakes at
the end", "icons appear at the end", "a card appears before its connector", "make yourself a visual
harness instead of eyeballing". The harness came first: `scripts/motion_harness.py` seeks every
slide in 50 ms steps and compares every animated element's box against the resting slide, so a
finding names the element and the moment. Its first run reproduced every item on the list and
found two more. Root causes, all fixed: every emphasis gesture was a from-to tween that re-applied
its start state to an element that had already landed (the shake, the jump up, the zoom at the end
on nine slides) — the corporate personality now has NO emphasis gesture, the focal element lands
last after a hold; the director's `pulse` scaled or dimmed cards (slide 6 "cards moving up and
down") — no-op in corporate; a tweened `scale: 1` and even a plain x/y tween drop the native scale
of an SVG `<g transform="translate() scale()">` (slide 13's icon parked 44 MAE off until the
restore) — such nodes arrive by opacity alone; word splits used inline-block spans that reflowed
the title (why 1.5.x kept the split until the slide was left) — inline spans moved through `top`
render pixel-identical, and the markup is restored at completion; wipe reveals ended with a clip
that cut shadows and strokes (slide 12's headers, slide 14's foundation line matched only after
the restore) — the resting clip is now −25 %; a highlighted card with a different class was never
grouped (sat on stage from frame one); ordinal numbers were owned by two tweens; slide 13's scene
had its docs and lineage rays swapped (a director error the harness now catches as BEFORE ITS
CONNECTOR). Blur-in is off text roles in the EPAM pack. The harness is the gate after §7b.

Also fixed on the way: `motion_probe.py` had lost its imports; the 1/3-rule loosening initially
went the wrong way (a smaller overlap factor means more overlap). Rejected ideas stay in §4.

## 1. The sources

| Repo | What it is | Worth taking |
|---|---|---|
| `iart-ai/motion-skills` | Index of 17 skill packs (54 skills) by iart.ai; the hub repo holds only a README and a verify toolkit. The substance is in the packs: `motion-design-skills` (art direction, animation principles, shot composition), `kinetic-typography-skills`, `data-animation-skills` (presentation-video, chart-animation, infographic), `web-animation-skills` (gsap-web, 60fps, svg, accessible). | The **motion-language spec** (one ease family, one base unit, one transition family, hold discipline), the per-shot **direction notes**, the consistency checklist, the deliver-and-verify loop (`?t=N` seek harness, contact sheets). |
| `lottiefiles/motion-design-skill` | A principles-only Claude skill (no scripts): four motion personalities, Disney's 12 principles adapted to UI, three motion layers, the 1/3 rules, timing and easing tables, a severity-graded quality checklist. | The **quality rubric** with CRITICAL/HIGH/MEDIUM tiers, the ambient budgets, the follow-through numbers, context adaptation (dark mode, reduced motion). |
| `howseen-ai/claude-motion-design` | One founder's video pipeline: HTML `seek(t)` engine, Playwright frame render, ffmpeg, beat-synced audio, a "remake" mode. Video-centric and personal. | Process rules, not code: the **anti-"AI motion" list**, the **critique loop** (score, fix ≤7, leave 9+), **judge ≠ builder**, "the next shot enters already moving in the exit's direction", targeted blur only, deterministic Chromium flags. |
| `github.com/topics/motion-graphics-ai` | Two zero-star repositories (an After Effects rotoscoping suite, a Manim narrated-graphics skill). | Nothing. |
| `motiondivision/motion` | The Motion library (ex Framer Motion) and its `ai-kit` skill. | The **performance tier list** (compositor-only S-tier → layout-thrashing F-tier), the `filter: blur()` cost warning, the MotionScore audit idea. Not the library itself (see §4). |

## 2. Already in imprimatur (nothing to do)

The 1.5.x craft pass already covers most of what these sources insist on: out-eases only and
no bounce; at most two identical eases per slide; speed as weight (hero 0.5–0.8 s, details
0.15–0.3); group build ≤ 0.5 s; directions rotating per slide; kinetic word titles with a
masked variant for long titles; count-ups 1.2–1.6 s with tabular numerals; draws overlapping
75 %; a 0.15 s start offset; one ambient per slide; a blur dial; arcs on travel legs; the
static predicate; end state == static DOM proven by QA; the filmstrip and the flicker probe;
director scenes with a scene graph; `prefers-reduced-motion` → static. The sources confirm
these choices rather than contradict them.

## 3. Findings and proposals, ranked

### P1 · One motion language per deck; variety in gesture, not in curve
**Source:** iart motion-art-direction ("consistency reads as confidence; variety reads as
noise; two eases maximum, one in, one out"); LottieFiles brand motion identity (one signature
easing for 80 %, a three-step duration palette, one entrance pattern).
**Gap:** `choreograph.py` `pick_ease` draws from four pools (`power2/3/4.out`, `circ.out`,
`sine.out`, `expo.out`) plus the fixed eases of `whip`, `slam`, `snap`, `rise-rotate`. A deck
ends up using six or seven curves. The ≤ 2 rule is enforced per slide, not per deck. The EPAM
pack also still declares `easing.emphasis: "back.out(1.4)"`; `motion.js:573` reads it into
`cfg.easeEmphasis` and nothing uses it, so the pack contradicts its own "never bounce" rule.
**Proposal:** add `motion.personality` to the pack (`corporate` for EPAM; `premium`,
`playful`, `energetic` for forged packs) that fixes **one signature ease** (corporate:
`power3.out`), **one hero ease** (`power4.out`), a **base unit** (0.4 s; every duration a
multiple of 0.1 s of it), overshoot 0, hold 0.3 s, stagger rhythm 60 ms. `pick_ease` draws
from those two only; variety stays where Roman asked for it (effect, direction, stagger
origin). `--summary` gains a deck line: eases used, base-unit conformity, stagger rhythms.
The forge maps brand adjectives to a personality with iart's brand → motion table. Remove the
dead `easing.emphasis` key.
**Effort:** small (pack schema + ~30 lines). **Verify:** summary line shows ≤ 2 eases
deck-wide; `test_motion.py` asserts it on the fixture deck.

### P2 · A reading beat before the point
**Source:** iart hold discipline ("≥ 0.3 s stillness after each beat"; "numbers hold ≥ 0.5 s";
"caption lands after the count completes, not during"); LottieFiles 100–200 ms breathing room
before resolution.
**Gap:** the auto plan starts the emphasis at `last.at + last.dur * 0.8`
(`choreograph.py` build_spec), i.e. before the last beat has landed. Director scenes already
have `emphasisGap` 0.35 s; the auto plan does not.
**Proposal:** emphasis at `last_landing + personality.holdMs`; a KPI's caption (the text
directly under a counted number) lands after the count settles; nothing moves after the
emphasis. **Effort:** trivial. **Verify:** filmstrip shows a still frame before the emphasis;
`motion_probe` reports no change between landing and emphasis.

### P3 · The entrance plays under the transition
**Source:** LottieFiles entrance–exit continuity (100–150 ms overlap, no more); howseen "the
next shot enters already moving in the exit's direction".
**Gap:** `viewer.js:144–145` posts `play` to the incoming slide and then runs the stage
transition. With `zoom-blur` at 650 ms the first 0.65 s of the entrance (the hero is meant to
be on screen by 0.5 s) plays while the stage is still scaling and blurred. The direction
scheme of the slide (`DIRECTION_SCHEMES`) is chosen by slide number, unrelated to the
transition that brought the slide in, so a push to the left can be followed by cards entering
from the left.
**Proposal:** post `play` when the transition is ~70 % done (one `setTimeout` on the
transition promise), so the hero lands as the stage settles; pick the direction scheme from
the transition type (push → enter along the push, whip-pan → enter from the pan side,
zoom-blur / push-depth → scale-settle entrances). **Effort:** small. **Verify:**
`motion_probe` frame diffs over the first 800 ms of a navigated slide; filmstrip from the
viewer.

### P4 · Simultaneity: the 1/3 rule and one counter at a time
**Source:** LottieFiles 1/3 rule (with 3+ elements, at most a third in motion at once);
iart infographic reference ("only one counter runs at a time: the eye is never asked to read
two moving numbers"); howseen "one thing moves at a time".
**Gap:** same-tier beats overlap at 35 % of the previous span, so three 1.4 s count-ups start
0.49 s apart and run together; a six-card group with 60 ms stagger is fully in flight while the
title waterfall is still landing. Nothing measures concurrency.
**Proposal:** `choreograph.py` computes a concurrency profile (elements in motion per 50 ms)
and prints the peak in `--summary`; KPI counters sequence (`next.at = prev.at + 0.6 × cdur`,
or `cdur` shrinks to 0.9 s when n ≥ 3); the budget fitter uses the concurrency peak as a second
constraint (lower overlap before shortening durations). **Effort:** medium (~60 lines).
**Verify:** peak concurrency ≤ ⅓ of animated elements on the fixture deck; filmstrip.

### P5 · Follow-through inside cards (the missing secondary layer)
**Source:** LottieFiles three layers ("primary-only feels flat"), Disney follow-through
(children trail the container by 50–150 ms), the Premium card recipe (content fades in
100 ms after the card lands).
**Gap:** the classifier takes a card as one block and skips its children (`insideTaken`), so a
card arrives stamped: heading, body and icon move as one bitmap.
**Proposal:** on `card` / `svg-card` beats in the cinematic level, the runtime adds a trailing
fade-up (8 px, 0.25 s, signature ease) on the card's direct heading/body/icon children, offset
80 ms after the container, still `fromTo` so the end state is unchanged. Opt-out per pack
(`motion.followThrough: false`). **Effort:** small (~25 lines in `addBeat`). **Verify:**
`check_motion` MAE stays 0; filmstrip shows the content settling after the card.

### P6 · Line-mask titles and accessible splits
**Source:** iart kinetic-typography ("by line is the calmest, most premium reveal"; mask reveal
is the industry-standard headline; `aria-label` on the container and `aria-hidden` on
fragments); GSAP 3.13+ SplitText `mask: "lines"`.
**Gap:** titles have `words` and `words-mask` (per word). Long titles fall back to
`words-mask`, which still pops word by word. `splitWords` sets no `aria-*`, so during the
presentation the title is a list of spans to assistive tech.
**Proposal:** a `lines-mask` effect: split words, bucket spans by rendered line
(`getBoundingClientRect().top`), lift each line through a clip window with an 80 ms stagger,
0.6 s hero ease; make it the choice for titles > 8 words and the default hero-title gesture of
a `premium` personality. Set `aria-hidden` on fragments and `aria-label` on the container at
split time (both restored on leave by the existing innerHTML snapshot). Keep the custom
splitter (it handles gradient-text units, which SplitText does not). **Effort:** small-medium.
**Verify:** filmstrip; `check_motion` MAE 0 (the keepSplits rule already covers reflow).

### P7 · Transitions that carry the argument
**Source:** iart presentation-video ("the cut between slides answers 'so what's next?': quiet
fade for 'and also', a bigger push for a new act; a transition that doesn't mark a logical step
is decoration").
**Gap:** `transition_in` comes only from `templateOverrides` by template stem. Two consecutive
content slides always get the deck default regardless of whether the second one contradicts,
proves, or merely continues the first.
**Proposal:** deck-narrative writes one connective per slide brief (`Link: and-also |
therefore | but | proof | new-act`); `choreograph.py` maps it (crossfade · push · whip-pan ·
zoom-blur · push-depth) with the template override as fallback and writes it into
`window.__DECK.transitions` as today. **Effort:** small (narrative template + a dict).
**Verify:** `--summary` `in=` column; `test_motion.py` fixture with the five links.

### P8 · Performance guardrails from the tier list
**Source:** Motion performance docs and tier list (`transform`/`opacity` compositor-only;
`filter: blur()` is accelerated but "90 % of performance issues are a big blur", warning above
10 px; SVG attribute and text writes repaint every frame); iart 60fps skill (animate the
presence of a filter by opacity, not its radius).
**Gap:** at `motion.blur: full` the runtime reaches 16 px (`slam`), 14 px (`snap`); the
`zoom-blur` viewer transition blurs the entire 1920×1080 stage; `drift` translates and rotates
`[data-decor-bleed]` washes, which are themselves filtered gradients (see the
Chromium re-raster memory), for 9 s × 4; `count-up` writes `textContent` every frame (layout).
Nothing reports the cost of a spec.
**Proposal:** clamp any runtime blur to 10 px regardless of dial; cap the stage transition blur
at 4 px (or drop it to scale + opacity); for drift, promote the wash just-in-time
(`will-change: transform` set at idle start, removed at `toEnd`) and measure frame interval
with `motion_probe` before keeping it; add a **motion cost** row to `check_motion.py`:
number of filter tweens, max blur px, largest filtered area, count-up count, with WARN
thresholds. **Effort:** small for the clamps, medium for the cost row. **Verify:**
`motion_probe` frame spacing (today ~80 ms per screenshot; add a pure timing mode) and the new
QA row on the 17-slide deck.

### P9 · A motion critic, separate from the builder, with a frozen-frame harness
**Source:** howseen critique loop ("score 1–10, write the three worst problems with
timestamps, fix ≤ 7, don't touch 9+", "judge ≠ builder: a fresh agent restates the message
from the frames alone"); iart deliver-and-verify (`?t=N` harness, contact sheets); LottieFiles
severity-tiered checklist.
**Gap:** design-crit and brand-audit judge the static deck. Motion is judged by the
orchestrator reading `--summary` and by the director looking at its own strips. There is no
independent pass, no rubric, and no way to freeze a slide at a given time without
`motion_strip.py`.
**Proposal:** (a) `?t=1.25` in `motion.js`: build, `tl.pause()`, `tl.seek(t)`, no veil — any
agent or Playwright call can screenshot an exact moment; (b) deterministic Chromium flags in
`motion_strip.py` / `motion_probe.py` (`--deterministic-mode
--run-all-compositor-stages-before-draw --disable-threaded-animation
--font-render-hinting=none --force-color-profile=srgb`) so MAE numbers are reproducible;
(c) `agents/motion-crit.md`, read-only, spawned at §8 next to design-crit when motion is on:
samples five slides (cover, densest, one directed scene, a divider, closing), runs strip +
probe, scores each on hook ≤ 0.5 s · one hero per frame · readability during the build ·
rhythm (stillness before the point) · variety across the deck · cost (P8 row) · and, for
directed scenes, the **one-sentence test** (restate the story from the strip alone; if it
cannot, the scene fails). Reports ≤ 15 lines, the fix per failing slide, default reject under 8.
**Effort:** medium (agent prompt + ~40 lines of runtime/tooling). **Verify:** run on the
17-slide deck; the critic's findings should reproduce the three flicker causes already fixed
as "no finding".

### P10 · Ambient tuning
**Source:** LottieFiles ambient patterns (amplitude 10–20 % of primary; layered floating uses
different durations per element so nothing syncs; dark mode: reduce intensity 10–20 %).
**Gap:** both drift targets share one 9 s duration with alternating sign, so they move in
lockstep; dark slides get the same distances and blur as light ones.
**Proposal:** per-target duration × {1, 1.35, 0.8} and a 30 % phase offset; on dark slides
(background luminance already measured by `qa.py`) scale travel and blur by 0.85.
**Effort:** trivial. **Verify:** filmstrip of a wash slide; probe idle diff unchanged (still
≈ 0 on text).

### P11 · Grid-aware and distance-based stagger
**Source:** LottieFiles grid-card recipe (+20 ms per new row), iart distance-based stagger
("constant feel regardless of count").
**Gap:** `orderIndex` offers start / center / edges / end over a flat index; a 2×3 card grid
staggers in index order, so the second row starts exactly where the first ended.
**Proposal:** `from: "grid"` (row × (stagger + 20 ms) + col × stagger) using the boxes the
classifier already measures, and `from: "distance"` for groups > 8 (delay ∝ distance from the
focal element). **Effort:** small. **Verify:** filmstrip on a card-grid template.

### P12 · Craft rules to add to `references/motion.md` and the director
From howseen's anti-"AI motion" list and iart's restraint pass, the lines not yet written
down: one accent colour moves; one thing moves at a time inside a journey; transformations
over cuts; no particles, glow, rainbow gradients; "don't animate the entire frame at once,
hold an anchor so the eye has a home"; one "wow" per deck (a second cancels the first; today
the EPAM pack allows `slam`/`snap`/`rise-rotate` on every divider); and the silent
one-sentence test as the director's acceptance criterion. Effort: documentation only.

## 4. Not adopting, and why

- **Remotion / MP4 / audio pipelines** (iart data-animation, howseen): Roman's decision is
  slides only, no video export. The hyperframes contract (one paused seekable timeline) is
  kept so a later export stays possible; nothing more.
- **Rewriting the runtime as a pure `seek(t)` engine** (howseen): GSAP timelines are already
  seek-safe (`fromTo`, no clocks, no randomness); `?t=` from P9 gives the same determinism.
- **Switching GSAP for Motion**: Motion's advantage is off-main-thread WAAPI animation when
  the main thread is busy. A slide has nothing else on its main thread; MotionPathPlugin,
  stagger origins and the restore logic are GSAP-specific; GSAP is free since Webflow. Keep
  GSAP; take only Motion's performance rules (P8).
- **Playful / energetic personalities for EPAM**: overshoot and squash read as toy-like on
  financial and delivery content (iart, LottieFiles agree). They exist only as forge options.
- **"Always three layers" taken literally** (LottieFiles): on text slides the ambient layer
  was measured as shimmer (camera off, 2026-10-04). Ambient stays limited to washes.
- **Mesh gradients, particles, sparkles, border beams** (iart backgrounds, howseen
  component ports): on howseen's own banned list for serious content, and on the EPAM pack's.
- **The topic page**: nothing reusable.

## 5. Release plan — one release, 1.6.0

All twelve ship together as 1.6.0. Only the build order matters:

1. P1 personality and the deck-wide ease language (P5 and P6 take their eases from it); remove the dead `easing.emphasis` key.
2. P9a the `?t=` seek harness and the deterministic Chromium flags, so every later change is judged by frozen frames.
3. P2 reading beat · P3 play after the transition and direction continuity · P10 ambient · P11 grid stagger.
4. P4 concurrency profile and sequential counters · P5 card follow-through · P6 lines-mask and aria · P7 transitions from the narrative's connective.
5. P8 blur clamps and the motion cost row · P9c the motion-crit agent · P12 the written rules.
6. One before/after run of the 17-slide deck through `choreograph.py`, `qa.py`, `motion_probe.py` and a filmstrip; the numbers go in the commit message.
