# Phase 10 — Export (detail)

## Gate check first

Do not proceed unless §9 is clear: a review round is on record (`review.offered` or
`review.fast_track` in `deck-state.json`), the latest `annotations.json` (if any) has zero
`open` annotations, `apply_edits.py --check` exits 0, and the user has accepted. If a
comment is still open, return to §9; if no review round is recorded, §9 has not happened —
run it. `export_gate.py` enforces the first two mechanically, but reaching the hook with the
gate unclear means the workflow already went wrong.

## Ask the format — never assume PDF

> *"How do you want the deck delivered — **PDF** (pixel-perfect, presentation-grade, not
> editable), **PPTX** (fully editable in PowerPoint — text, shapes, diagrams — with minor
> rendering approximations), or **both**?"*

Recommendation: presenting or distributing read-only → PDF (the fidelity reference);
client/account team will edit or reuse → PPTX (+ PDF as reference); in doubt → both.

## PDF (`pdf-export`)

```bash
python "{PLUGIN}/skills/pdf-export/scripts/batch_convert.py" \
  --deck-dir "<deck>/" --output "<deck>/<Title>-YYYY-MM-DD.pdf" \
  --slide-selector "#slide" --glob "[0-9]*.html"
```

Playwright element screenshots, not `page.pdf()`, so no print-media relayout (the cause of
gradient-text clipping, font substitution and wrap breakage). The slide list comes from
`deck-state.json` when present; the explicit glob is the fallback that keeps `index.html`
and `slide-review.html` out. Output: one merged PDF, 20in × 11.25in pages at 192 DPI, matching
the browser preview. Non-standard selector → pass it to `--slide-selector`. Verify: page
count == `slide_count`; spot-check first + last page with `qlmanage -t -s 1400`.

## PPTX (`pptx-export`)

```bash
python3 "{PLUGIN}/skills/pptx-export/scripts/html2pptx.py" \
  --deck-dir "<deck>/" --output "<deck>/<Title>-YYYY-MM-DD.pptx"
```

Text stays editable at exact positions with the browser's line breaks; cards are shapes;
SVG diagrams become native grouped shapes; gradient covers are native fills. Flags:
`--native-charts`, `--svg-blip`, `--raster-fallback`. Verify with the checklist in
`pptx-export/SKILL.md` (content-MAE loop + slide count); the final judgment is the user
opening it in PowerPoint. Tell them: machines without the pack's font family substitute
fonts (layout holds, glyphs differ); the PDF remains the fidelity reference when both exist.

## Record the artifacts

`deck-metadata.json` → `"exports": { "pdf": "<file>", "pptx": "<file>" }`, whichever were produced.

## Register the deck in the user's deck index — only if they keep one

Some setups file decks into a knowledge base (an Obsidian vault MOC, a Confluence index, a
shared register). This is an environment convention, not a pipeline requirement: do it when
the user has such an index and told you about it, skip it silently otherwise — never invent
one, never write outside the deck folder unasked. When it applies (the vault convention this
pipeline was built against uses `<Slides folder>/🖼️ <Area> Slides MOC.md`, e.g.
`Work/<Client>/Slides/🖼️ <Client> Slides MOC.md`):

1. If the MOC does not exist (new area's first deck), create it by copying an existing
   area's Slides MOC structure (frontmatter, `## Decks` table, `## Legacy` if needed,
   `🤖 LLM Context` block, footer link up to the area MOC) and add a down-link from the area MOC.
2. Upsert one row in `## Decks`, sourced only from `deck-metadata.json`: title (linked as
   `[[<deck_path>/deck-brief|<title>]]`), client/engagement, audience → outcome, slide count,
   date, status (which exports are current vs stale if there is a revision history). An
   existing row is updated, not duplicated.
3. Confirm `deck-brief.md` carries a footer backlink to the Slides MOC
   (`*→ [[<Slides folder>/🖼️ <Area> Slides MOC]]*`) — add it on first export.
4. Read the MOC back to confirm the row persisted — never trust the write.

## Done when

- [ ] Format(s) chosen; each chosen export ran
- [ ] PDF: page count == `slide_count`, first/last page spot-checked, `Title-YYYY-MM-DD.pdf`
- [ ] PPTX: slide count == `slide_count`, verification checklist run, user opened it, `Title-YYYY-MM-DD.pptx`
- [ ] `deck-metadata.json` → `exports` recorded
- [ ] Deck index updated and read back (only if the user keeps one)
- [ ] User confirms the deliverable(s) are ready
