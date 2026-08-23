# Extraction: what each source can tell you

- [PPTX / POTX](#pptx--potx)
- [PDF](#pdf)
- [Measured: the same deck, both ways](#measured-the-same-deck-both-ways)
- [When the source lies](#when-the-source-lies)

## PPTX / POTX

The good case. `ppt/theme/theme1.xml` holds a **declared** design system: twelve named colour
slots (`dk1`, `lt1`, `dk2`, `lt2`, `accent1`–`accent6`, `hlink`, `folHlink`) and a major/minor
font pair. A designer wrote those. Treat them as ground truth and let observation rank them
rather than replace them — `probe_brand.py` snaps sampled colours onto theme hexes within the
merge threshold, so the pack carries the designer's exact value instead of a rendering of it.

Consequences worth knowing:

- **A declared colour survives low usage.** An accent used on two pages is still a brand token.
  The probe never drops a theme colour on usage grounds; thresholds only arbitrate undeclared
  colours, which is where the noise lives.
- **Shape colours may be theme references, not literals.** A run or fill can say "accent2"
  rather than a hex. The probe resolves those through the theme; if the theme is missing, they
  come back unresolved and the deck will look like it has almost no colour. Missing theme +
  suspiciously few colours is the signature of that failure, not of a monochrome brand.
- **Groups double-count.** A group shape and its children both report areas, so a heavily
  grouped deck inflates certain colours. Per-observation area is capped at one page to stop a
  single bleed shape or group from dominating the ranking.
- **`.potx` is better than `.pptx` when you can get it.** A template carries masters and
  layouts — the intended system — rather than one deck's usage of it.

## PDF

No theme, no declared anything. Everything is inferred from what the pages happen to contain,
and the pack you produce should say so.

`probe_brand.py` reads vector objects and text spans through `pdfplumber`: rectangles and
curves give fill colours with real bounding-box areas; characters give font name, size in
points (converted to CSS px) and fill colour. That is usually enough for both a palette and a
type ramp, without rasterising anything.

- **Colour spaces vary.** Fills arrive as 1-tuple grey, 3-tuple RGB or 4-tuple CMYK. CMYK is
  converted naively; a brand that specifies Pantone or ICC-managed CMYK will come out close but
  not exact, so prefer a `.pptx` or a digital spec for final values.
- **Font names are subset-mangled.** `ABCDEF+SourceSans3-Light` is normal. The family is after the
  `+`; the numeric suffix is usually the weight.
- **A flattened export has no vector objects at all.** If the probe reports few colours and no
  type steps, the PDF is images. Re-run with `--raster` to sample pixels — those colours are
  marked `raster` in the evidence because they are pixels, not declared values, and they carry
  antialiasing and JPEG artefacts. Raise `--delta-e` when working from raster.

## Measured: the same deck, both ways

A real brand template was probed as `.pptx` and again as its PowerPoint PDF export, and both
results scored against the brand's known token values. This is what the PDF path costs:

| | PPTX | PDF |
|---|---|---|
| core brand colours recovered (ΔE≤3) | 7/8 | 6/8 |
| colour clusters returned | 10 | 18 |
| type steps | 13 | 17 |
| font families | 4 | 4 (after subset-prefix stripping; 20 before) |
| **gradients readable** | **12** | **0** |

Read it as: **colour survives the round trip, gradients do not.** Recall is close, and the PDF
even found one accent the theme never declared (it appears only in charts). But a PDF export
flattens gradients into shading patterns with no stop list, so a brand gradient is simply
invisible on that path. The probe now says so explicitly rather than letting silence read as
"this brand has no gradient".

The PDF also returns roughly twice the clusters — export materialises intermediate fills the
source only implied — so expect to discard more, and lean harder on `pages` and area weight
when deciding what is structural.

Both paths produced packs that passed the full acceptance test, so a PDF-only brand is
workable. Just get the source file when you can.

## When the source lies

Brand artefacts drift from the brand. This is normal and you should expect it.

The clearest example: a real template declares its font scheme as **Calibri**, while
the brand's actual typeface is Source Sans 3 — the theme's font slots were simply never updated,
and the running text confirms Calibri throughout. A probe reports what is there. If what is
there contradicts what you know about the brand, say so explicitly rather than silently
"correcting" it, and let the human decide which is authoritative.

The same applies to near-duplicate hexes. Two tokens differing in a single digit
(`#2B59C3` vs `#2B59C4`) usually means one of them is a transcription slip, or the brand was
revised and one artefact never caught up. The evidence cannot tell you which is correct — only
that they differ. Report the discrepancy with both values and where each was seen; that is
genuinely useful, and guessing is not.

Finally, a thin source is a thin source. A six-page teaser gives you two colours and no ramp.
Forge the partial pack, mark the gaps in `PROVENANCE.md`, and ask for a better artefact — a
`.potx`, the written brand guidelines, or the brand's live site. Padding a thin pack with
plausible defaults produces something that will be trusted and shouldn't be.
