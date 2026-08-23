# Provenance — Minimalist Slide Deck System (Outline)

**Authored, not extracted.** No brand artefact was probed; every token below is a design decision made by whoever wrote this pack. Treat it as a starting point to be replaced by a real brand, not as a record of one.

| token | hex |
|---|---|
| `out-primary` | #201e1d |
| `out-primary-mid` | #605d5d |
| `out-accent` | #ae1800 |
| `out-deep` | #2d2b2b |
| `out-support-1` | #7d7979 |
| `out-support-2` | #9b9797 |
| `out-ink` | #201e1d |
| `out-body` | #444141 |
| `out-muted` | #605d5d |
| `out-muted-soft` | #7d7979 |
| `out-rule` | #d7d3d3 |
| `out-tint` | #f8f4f4 |
| `out-surface` | #eae9e9 |
| `out-white` | #ffffff |
| `out-neutral-400` | #bab6b6 |
| `out-accent-600` | #dd2b0f |

Dropped as noise during probing: 0 colour cluster(s).

## Probe notes

- Pack was authored, not extracted. Every value here is a design decision, so the usual question 'is this really the brand's?' is answered by whoever wrote it, not by a source file.

## Amendments

### v1.1 — audited for the left-accent-bar pattern; added 11 templates

**Audited for the decorative left-accent-bar pattern** (the same fix applied to the sibling
`game-studio` pack). Grepped every template for `border-l-*`, narrow `w-[Npx]` rounded bar
divs, and top accent stripes: **none found**. The only `border-l` hit in the whole pack is
`05-two-column.html`'s plain 1px `border-l border-out-rule` column divider — the sanctioned
pattern, not the banned one. No fix was needed; recorded here so the audit itself is on the
record rather than the absence of a change being ambiguous later.

**Added 11 templates**, designed natively for this system's own restraint rather than adapting
`game-studio`'s card-and-icon-heavy style: `10-team-roster.html`, `11-timeline.html`,
`12-comparison-table.html`, `13-three-column.html`, `14-big-stat.html`,
`15-process-steps.html`, `16-quote-grid.html`, `17-checklist.html`, `18-definitions.html`,
`19-breakdown.html`, `20-org-simple.html`. Every new template holds to the manifest's own
`ruleNotes.enforceTokenValues`: accent marks exactly one emphasised value per slide (the
current timeline milestone, the largest funding category, the active process step) and never
decorates a fill, a card, or a bar that doesn't need singling out. `19-breakdown.html` uses the
pack's declared `viz` ramp (`body → support-1 → neutral-400 → accent`) rather than four
arbitrary colours, for the same reason. `20-org-simple.html` deliberately uses no bordered
boxes at all — a reporting structure drawn in 1–2px rule lines and type weight, since bordered
cards aren't a pattern this pack uses anywhere else.

Two real mistakes were caught and fixed before this counted as done, both from carrying a
`game-studio` habit over without checking this pack's own manifest first:

- `11-timeline.html` and `19-breakdown.html` initially set `font-family:'IBM Plex Mono'` on
  numeric labels — `game-studio` allows that family, this pack's
  `typography.familyRequiredPattern` is `"Archivo"` only. The real installed validator caught
  it (`font-family without the Archivo stack`); both were reverted to the default stack.
- `20-org-simple.html`'s parent label wrapper was sized too narrow (300px) for "Founder &
  Creative Director" at `text-out-subhead`, so it wrapped to two lines and the trunk connector
  line (positioned for one line) drew straight through the second line of text. Caught by
  measuring `offsetHeight` in-browser (62px instead of the expected 31px for one line), not by
  eye — the screenshot alone was ambiguous at reduced scale. Fixed by widening the wrapper to
  500px with `white-space:nowrap`; the connector's `gap` from text bottom to trunk top measures
  exactly 0 after the fix.

`11-timeline.html`'s tick alignment and `20-org-simple.html`'s three-child centring were both
verified with `getBoundingClientRect()`/`offsetLeft` measurements in-browser, not eyeballed —
offsets came back at 0px and centres at exactly 340/640/940 as constructed.

Verified: `audit_pack.py` clean (0 problems, 0 warnings) across all 22 files; `verify_pack.py`
ACCEPTED — all 21 templates pass against the installed orchestrator, fixture still fails on all
13 rules it always has. This pack's own `SKILL.md` template table was also stale before this
amendment (six generic filenames matching nothing in `templates/`) and is corrected to the
actual 21 files.
