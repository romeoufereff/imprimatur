# Deck Brief Template

The orchestrator writes a filled copy of this as `deck-brief.md` into the deck folder
once intake is locked, **before** handing off to narrative. It is the single
human- and agent-readable source of truth for *this deck's* intent — the per-deck
companion to the brand-level `design-system/SKILL.md`.

**Why a file and not just chat:** every sub-skill (narrative, designer, design-crit)
otherwise re-derives audience/tone/constraints from the conversation, drifting as the run
gets long. A short markdown brief in the deck folder means each skill reads the same
locked intent on every invocation. It also captures two things the old intake dropped on
the floor: **anti-references** (what the deck must *not* look or sound like) and a
**per-deck voice** note (the brand voice, narrowed to this audience).

Keep it short — one screen. It records decisions, not prose. `deck-metadata.json` holds
the machine fields (paths, slide count) and links back to this file.

---

```markdown
# Deck Brief — <Deck Title>

## Intake
- **Audience:** <executive | mixed | technical>
- **Outcome:** <pitch | status update | capability brief | Executive Readout | proposal | case study>
- **Length:** <N slides>
- **Context:** <client / engagement / your role / key constraint>
- **Must-haves:**
  1. <non-negotiable 1>
  2. <non-negotiable 2>
  3. <…>

## Taste dials  (see references/taste-dials.md)
- **Density:** <sparse | balanced | dense>   — default for this audience: <…>
- **Variance:** <low | medium | high>        — default for this outcome: <…>
- **Override note:** <why the user changed a default, or "defaults accepted">

## Anti-references  (what this deck must NOT be)
- Visual: <e.g. "not a wall of identical cards", "no stock-photo hero", "avoid the busy
  consulting-matrix look">
- Tonal: <e.g. "not salesy / hypey", "no jargon the steering committee won't know">
- Comparable to avoid: <e.g. "don't make it look like a generic SaaS pitch template">

## Voice  (brand voice, narrowed to this audience)
- <1–3 lines: how this deck should sound. e.g. "Confident and specific; lead with the
  business outcome, then the how. Plain language — CFO is in the room. No hedging.">
```

---

## Filled example

```markdown
# Deck Brief — SAP BW Modernization

## Intake
- **Audience:** executive
- **Outcome:** pitch
- **Length:** 10 slides
- **Context:** Data-modernization pitch to PharmaCore Inc.; I'm the delivery lead;
  €2M engagement; C-suite + steering committee in the room.
- **Must-haves:**
  1. SAP BW batch-processing bottleneck
  2. Snowflake + Databricks target architecture
  3. 18-month ROI proof
  4. Risk mitigation (data governance, change management)

## Taste dials
- **Density:** sparse   — default for executive audience
- **Variance:** high    — default for pitch outcome
- **Override note:** defaults accepted

## Anti-references
- Visual: not a wall of cards; at least one bespoke architecture visual and one big-number moment.
- Tonal: not hypey; this is a steering committee, not a sales floor.
- Comparable to avoid: generic "digital transformation" template deck.

## Voice
- Confident, specific, outcome-first. Open each slide with the business "so what," then the how.
  Plain language — expand every acronym on first use. No hedging, no filler bullets.
```
