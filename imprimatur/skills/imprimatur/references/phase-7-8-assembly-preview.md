# Phases 7–8 — Assembly and HTML preview (detail)

## Phase 7 — assembly is one script

```bash
python3 {PLUGIN}/scripts/assemble_deck.py --deck-dir D
```

writes `index.html` (the viewer, from `templates/index-html-template.md`, `slides` array
from `deck-state.json`) and `deck-metadata.json` (title, client, engagement, slide_count,
deck_path, `dials`, `deck_brief: "deck-brief.md"`, timestamps — sourced from
`deck-brief.md` + `deck-state.json`). Field reference and folder layout:
`deck-assembly.md`. The designer never builds the viewer; if a stray `index.html` exists
from an older run, the script overwrites it.

Read `deck-metadata.json` back: `slide_count` must equal the number of `NN-*.html` files
(the `deck_consistency.py` hook flags drift on every write of this file).

### Adding or removing a slide later (review feedback, scope cut)

Every item, every time:

1. Add (`new_slide.py`) or archive (`_archive/<date>/`) the `NN-slug.html` file; update
   `deck-state.json` (`log_slide.py` for an added slide; remove the entry for an archived one).
2. If numbering shifted, renumber the affected files and their footer page numbers
   (`new_slide.py --page N` on re-created slides; an `Edit` on the footer otherwise).
3. Re-run `assemble_deck.py` — it regenerates the `slides` array and `slide_count`.
4. `qa.py --deck-dir D --files <touched> --json`; at export, PDF page count must equal `slide_count`.

## Phase 8 — preview is a server and one summary, not a re-verification

```bash
python3 {PLUGIN}/scripts/qa.py --deck-dir D --json     # one browser launch; the whole deck
python3 -m http.server 8934 --directory "<deck>/"      # then http://localhost:8934/index.html
```

Prefer HTTP over `file://` so relative `@font-face` paths behave as they will at export.
The scaler fits the fixed 1920×1080 canvas to any window via `transform: scale(r)`; the
layout never re-flows, so what the user sees is what the PDF will contain.

Hand over the URL with the `qa.py` summary line (N slides, all PASS / which FAIL). Do **not**
screenshot slides yourself to re-verify them — the designer rendered the bespoke ones,
design-crit reviewed the bodies, and `qa.py` measured geometry; eighteen orchestrator
screenshots on a real deck added minutes and found nothing new. If a `qa.py` FAIL appears
here, it is a revision (`phase-5-6-audit-revision.md`), not a preview problem.

Things the user may notice that no script measures — say so if you see them in the one
look you take at the served index: fonts falling back to a system family (compare a bold
heading; the family label is `typography.familyLabel` in the pack manifest), gradient text
showing blue-rectangle artifacts (fonts 404 → `new_slide.py` did not localise them — re-run
it with `--force` on that slide), a broken image.

**Hand the preview over as a look-ahead, not an approval request.** Do not ask "does this
look good?" here — that question belongs to §9, after the harness is offered. Say: *"The
preview is up — next I'll open the review page so you can mark up anything you want changed."*
An acceptance given at the preview is feedback on the preview, not the review gate.

**Done when:** `index.html` + `deck-metadata.json` written by `assemble_deck.py` and read
back · whole-deck `qa.py` PASS · preview served · no sign-off question asked.
