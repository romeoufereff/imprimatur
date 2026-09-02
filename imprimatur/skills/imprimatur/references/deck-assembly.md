# Deck Assembly Guide

How to assemble the final deck from approved slides, including folder structure, HTML viewer template, and metadata.

---

## Step 1: Organize Slide Files

Create a deck folder with sequential numbering:

```
deck/
├── 01-cover.html
├── 02-big-idea.html
├── 03-problem.html
├── 04-solution.html
├── 05-architecture.html
├── 06-proof.html
├── 07-risks.html
├── 08-next-steps.html
├── fonts/              ← Deck-local font copies (populated by new_slide.py per slide; slides reference fonts/<file>)
├── Input/source-notes.md ← Extracted source facts (Explore subagent at intake), if sources were given
├── deck-brief.md        ← Written by orchestrator at intake (dials, anti-refs, voice)
├── design-decisions.md  ← Design plan (orchestrator, 4a) + per-slide log (log_slide.py)
├── narrative-outline.md ← Outline + SLIDE BRIEFs, written by deck-narrative
├── deck-state.json      ← Progress + the slide list of record (references/state-tracking.md)
├── _archive/<date>/     ← Stale NN-*.html moved here before designers are spawned
├── index.html          ← Written by scripts/assemble_deck.py (from templates/index-html-template.md)
├── deck-metadata.json  ← Written by scripts/assemble_deck.py (fields below)
├── slide-review.html   ← Generated at §9 by deck-review (click-to-comment harness)
└── annotations.json    ← Exported by the user from the harness; refined against, then review-clean
```

`slide-review.html` and `annotations.json` appear during the §9 Visual Review & Refine step
(see deck-review), not at assembly. PDF export is gated on `annotations.json` having zero `open`
comments.

`deck-brief.md` is created at intake (before narrative), not at assembly — just confirm
it's present in the folder here. It's the per-deck source of truth every sub-skill reads;
see `templates/deck-brief-template.md`.

**Naming convention:**
- Prefix: 2-digit slide number (01, 02, ... 99)
- Separator: hyphen (-)
- Suffix: descriptive slide title in kebab-case (lowercase, hyphens)
- Extension: .html

**Example:** `03-problem-statement.html`, `05-technical-architecture.html`

---

## Step 2: Create index.html

**Normally you do not do this by hand:** `python3 {PLUGIN}/scripts/assemble_deck.py --deck-dir D`
writes `index.html` from the template below with the `slides` array taken from
`deck-state.json`, and `deck-metadata.json` (Step 3) in the same call. The manual steps
stay here as the reference for what the script produces and for repairing a viewer by hand.

The index.html file provides:
- Slide viewer (displays HTML slides in an iframe)
- Navigation buttons (prev/next)
- Slide counter (current / total)
- Keyboard shortcuts (arrow keys to navigate)

**Full template:** See `templates/index-html-template.md`

**To create index.html:**

1. Copy the template from `templates/index-html-template.md`
2. Update the `slides` array with your actual filenames:
   ```javascript
   const slides = [
     '01-cover.html',
     '02-big-idea.html',
     '03-problem.html',
     '04-solution.html',
     '05-architecture.html',
     '06-proof.html',
     '07-risks.html',
     '08-next-steps.html'
   ];
   ```
3. Save as `index.html` in the deck folder
4. Test: Open index.html in a browser, verify:
   - [ ] All slides load without errors
   - [ ] Navigation buttons work (prev/next)
   - [ ] Slide counter shows correct total
   - [ ] Keyboard arrows work (↑↓←→)

---

## Step 3: Create Metadata File

Create `deck-metadata.json` to track deck info for the render step:

```json
{
  "title": "SAP BW Modernization: From Batch to Real-Time",
  "client": "PharmaCore Inc.",
  "engagement": "Data Platform Modernization",
  "project_id": "ENG-2026-001",
  "audience": "executive",
  "deck_type": "pitch",
  "slide_count": 8,
  "deck_path": "/path/to/deck/",
  "deck_url": "file:///path/to/deck/index.html",
  "deck_brief": "deck-brief.md",
  "dials": { "density": "sparse", "variance": "high" },
  "created_at": "2026-05-21T10:30:00Z",
  "completed_at": "2026-05-21T15:30:00Z",
  "version": "1.0",
  "status": "ready_for_render"
}
```

**Required fields:**
- `title`: Deck title from cover slide
- `client`: Client name (from brief)
- `engagement`: Engagement/project name (from brief)
- `slide_count`: Total slides in deck
- `deck_path`: Full path to deck folder
- `status`: Set to "ready_for_render"

**Optional fields:**
- `exports`: written at §10 — `{ "pdf": "<file>", "pptx": "<file>" }`, whichever the user chose
- `project_id`: Engagement ID (from brief context)
- `audience`: Target audience type
- `deck_type`: Pitch / status-update / capability-brief / etc.
- `version`: Version number if tracking revisions
- `created_at` / `completed_at`: Timestamps for tracking

---

## Assembly Checklist

- [ ] All N slide HTML files present in deck folder (01-, 02-, ... NN-)
- [ ] `deck-brief.md` present in deck folder (written at intake)
- [ ] Slide filenames use kebab-case naming (lowercase, hyphens)
- [ ] index.html created with correct `slides` array
- [ ] Tested index.html in browser (all slides load, nav works, keyboard works)
- [ ] deck-metadata.json created with required fields
- [ ] Metadata title matches deck title
- [ ] Metadata slide_count matches actual slide count
- [ ] All filepaths are absolute (not relative) in metadata
- [ ] Ready for §8 HTML preview

---

## Troubleshooting

**Problem:** Index.html opens but slides don't load

**Solution:** Check slide filenames match the `slides` array exactly (case-sensitive, no spaces, correct extension)

**Problem:** Navigation buttons don't work

**Solution:** Check browser console for JavaScript errors. Verify slides array is properly formatted JSON.

**Problem:** Keyboard navigation doesn't work

**Solution:** Make sure index.html window has focus (click on the slide first). Some browsers require this.

**Problem:** Slide counter shows wrong total

**Solution:** Count items in `slides` array — must match actual slide files in folder.

---

## Next Steps

Once assembly is complete and tested, move to §8 HTML preview with:
- Full path to deck folder
- Metadata JSON object
- Expected output format (PDF, PPTX, HTML, etc.)

See SKILL.md section 8 (RENDER HANDOFF) for handoff format.
