# Design-crit — frameworks in detail, with examples

Companion to `agents/design-crit.md`. The agent definition carries the procedure and the
report format; this file carries the reasoning behind each framework and worked example
observations. Read it when a slide's verdict is unclear, not per slide.

## The ten frameworks

### 1. Visual hierarchy — is there one focal point?
The eye should land on one thing first, and it should match the message.
- ✅ "Focal point is the 87 % metric (largest, blue, top-centre). Eye lands there first."
- ❌ "Headline, sidebar metric and chart compete at equal weight. Which is the hero?"
- ⚠️ "Focal point (big metric) does not match the title (which is about timeline)."

### 2. Typography hierarchy — does size/weight guide the reader?
Display (largest, lightest) → body (regular) → detail (smallest, heavier for emphasis).
- ✅ "56px light → 24px bold → 20px regular. Easy to scan."
- ❌ "All text 20px. No hierarchy."
- ⚠️ "16px bold labels read heavier than 20px regular body — weight hierarchy inverted."
- Refinement pattern: "that footnote carries content, not chrome — lift it from 14px caption to a 16px label."

### 3. Whitespace and density — is the slide breathing?
≥ 30 % of the slide empty; macro whitespace between sections, micro between elements.
- ✅ "~35 % empty; room around each element."
- ❌ "~15 % whitespace; packed. Split into two slides?"
- ⚠️ "Whitespace all at the bottom; top half dense. Redistribute?"

### 4. Assertion-evidence — is the title a complete thought?
| ❌ Label | ✅ Assertion |
|---|---|
| Current State | SAP BW cannot scale to real-time demand |
| Budget | Migration costs offset by 18-month savings |
| Timeline | Phase 1 delivers business value by Q3 2026 |
| Risks | Data governance complexity requires executive sponsorship |
- ⚠️ "Title asserts 'Risk 1: Data Quality' but the content is about timeline — one of them must change."

### 5. Composition — is the layout intentional?
Asymmetric splits (1/3–2/3) feel dynamic; centred is for dividers and closings.
- ❌ "Centred title, content and footer on a content slide — reads static. This is a pitch."
- ⚠️ "Asymmetric, but a large empty block on the right creates imbalance."

### 6. Information design — does the chart tell a story?
| ❌ Topic title | ✅ Insight title |
|---|---|
| Revenue by Region | EMEA drove 28 % growth, up from 18 % YoY |
| Budget Status | 65 % of annual budget consumed, 2 months remaining |
- ⚠️ "3-D effect and drop shadows add noise; legend duplicates the axis labels — remove."

### 7. Cognitive load — is it within the DENSITY dial?
Count bullets + metrics + cards + chart bars + named people + labelled SVG nodes against the
deck's dial (`taste-dials.md`: sparse ≤ 8, balanced ≤ 12, dense ≤ 14) — never a flat 12.
- ✅ "4 bullets + 1 metric + 1 callout = 6, budget 8 (sparse)."
- ❌ "8 bullets + 2 metrics + 3 cards = 13 on a balanced deck. Split or move 4 bullets to appendix."
- ⚠️ "7 of 8, but bullets 4–6 are low priority — stronger with the top 3?"

### 8. Colour distribution — does 60-30-10 hold?
~60 % dominant (light surface), 30 % text, 10 % accent.
- ❌ "~40 % blue. Dial the accent back to 10–15 %."
- ⚠️ "Gradient text across the whole title is heavy — last 2–3 words only."

### 9. Accessibility and plain language
- ❌ "'MQTT data ingestion pipeline' unexplained for an executive room. Try 'real-time sensor data collection (MQTT)'."
- ⚠️ "'The downstream orchestration layer's scalability constraints impose a ceiling on throughput' → 'Current system can't handle peak load.'"

### 10. Narrative flow — does the slide move the story?
Role in the arc (problem / solution / proof / risk), title aligned to that role, pacing
(a breather after 3+ dense slides).
- ❌ "Introduces a new capability before the problem/solution arc closes. Reorder, or appendix?"
- ⚠️ "Slides 3–6 dense, slide 7 is an architecture diagram — good breather."

## Bespoke SVG visuals are sanctioned

Critique them on their merits, never as a deviation from templates: metaphor clarity (could a
viewer guess the point before reading labels?), visual grammar (the pack's shapes,
connectors, gradient fills, muted sub-labels — or pasted from another deck?), focal
discipline (the SVG *is* the focal point; flag competing cards). The opposite failure matters
more: a spatial message flattened into bullet cards — "this would land better as a bespoke
visual" is valid critique and routes back through narrative.

## Named tells (anti-slop lens)

Run `anti-slop-tells.md` as a checklist and **name** the tell — "this is *card-in-card*"
gives the designer a shared target. Most valuable: card-in-card · hero-less slide ·
centered-everything · symmetric-grid crutch · gradient overuse · decorative-only icons ·
template-monotony / wall-of-cards (deck-level) · brand-drift tells (cream canvas, serif
display, terracotta, indigo-purple cards, dark panels, soft-shadow stacks, emoji — these are
hard flags: the fix is re-copying the template, not adjusting the element). A tell is an
observation, not an auto-fail; do not flag taste ("feels corporate"), only tells you can name.

## Worked example — the compact per-slide entry

```
| 03 | REVISE | Title is a label ("Challenges and Implications") — assertion-evidence | Title → "Batch-processing bottleneck creates operational and competitive risk" |
| 05 | PASS | — | — |
| 07 | REVISE | card-in-card: metric card nested in a bordered card | Drop the outer border; let whitespace group |
```

One row per slide; the top finding only. A second finding on the same slide goes in the
same cell separated by `;` only if it is independent and cheap. Everything else the designer
could fix on its own is noise at this stage.

## Tone

Specific ("the callout label uses `muted-soft` at the label step — below 18px that role is
decorative-only; use `muted`"), non-prescriptive on judgment calls ("consider"), deferential
(the orchestrator and designer decide). Not: "This title is terrible. Fix it."

## Common pitfalls, in the words to use

| Pitfall | What to say |
|---|---|
| Cramped slide | "Split without losing coherence — which content is lowest priority?" |
| Centred content slide | "Reads formal/static; an asymmetric split would feel more dynamic." |
| Label title | "Names the topic ('Budget'). Assertion: 'Migration costs recover in 18 months.'" |
| Vague chart title | "Says 'Revenue'; state the insight: 'EMEA outpaced forecast by 12 %.'" |
| Competing focal points | "Metric and chart compete — which is the hero?" |
| Jargon | "First use of 'MQTT' — 'MQTT (real-time sensor protocol)'." |
| Inconsistent spacing across slides | "16px title gap on some slides, 24px on others — one value." |
| Card-in-card | "One level of container is enough; whitespace can group." |
| Decorative-only icons | "Swap any two and nothing changes — make them informative or drop them." |
| Template monotony | "Third content-bullets slide running — a `-focal` variant or a different shape." |
| Wall-of-cards (deck) | "No visual slide yet on a high-variance pitch — add a chart/pipeline/bespoke and a breather." |

## When unsure

Name the ambiguity ("unclear whether this slide establishes the problem or proposes the
solution"), offer the two readings and what each implies, and defer — the orchestrator
clarifies intent with narrative.
