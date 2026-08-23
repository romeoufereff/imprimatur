# The pack contract

What a design-system pack must contain, and the `decisions.json` you write to produce one.

- [What "standalone" means](#what-standalone-means)
- [decisions.json](#decisionsjson)
- [Rules → the data each one needs](#rules--the-data-each-one-needs)
- [Roles](#roles)

## What "standalone" means

This skill does not import a deck orchestrator, and a pack it produces is a plain folder — no
engine code inside it. The contract below is written out here so the forge works with nothing
else installed.

When an orchestrator *is* installed, `verify_pack.py` finds its `validate.py` and runs the pack
through it via the `DECK_DESIGN_SYSTEM` environment variable. That is the real test, because it
uses the engine the pack will actually face. Treat a contract-only result as provisional: the
pack is structurally sound but nothing has yet confirmed it can reject anything.

## decisions.json

Your judgment, in machine-readable form. `emit_pack.py` does not fill gaps — an absent field
produces an absent field, visibly, rather than a default nobody notices.

```json
{
  "id": "northwind",
  "name": "Northwind Design System",
  "version": "1.0",
  "canvas": { "width": 1920, "height": 1080 },

  "tokens": {
    "prefix": "nw",
    "colors": {
      "blue":    "#0B5FFF",
      "teal":    "#0E7C7B",
      "purple":  "#6B3FA0",
      "ink":     "#14161A",
      "body":    "#3A3E45",
      "muted":   "#6B7079",
      "rule":    "#D5D9E0",
      "tint":    "#EEF3FF",
      "surface": "#F6F7F9"
    }
  },

  "roles": {
    "primary": "blue", "accent": "purple",
    "ink": "ink", "body": "body", "muted": "muted",
    "rule": "rule", "tint": "tint", "surface": "surface",
    "viz": ["blue", "teal", "purple"]
  },

  "typography": {
    "familyLabel": "Source Sans 3",
    "familyMarker": "Source Sans",
    "familyRequiredPattern": "Source Sans",
    "fontUtilityClass": "font-nw",
    "stack": ["Source Sans 3", "system-ui", "sans-serif"],
    "allowedWeights": [300, 400, 700],
    "minFontSizePx": 14
  },

  "typeScale": {
    "display": { "size": "88px", "lineHeight": "1.05", "fontWeight": "300" },
    "title":   { "size": "40px", "lineHeight": "1.1",  "fontWeight": "700" },
    "body":    { "size": "20px", "lineHeight": "1.5",  "fontWeight": "400" }
  },

  "gradients":       { "brand": "linear-gradient(60deg, #0B5FFF 0%, #6B3FA0 100%)" },
  "gradientMarkers": ["#0B5FFF", "#6B3FA0"],
  "tracking":        { "eyebrow": "0.22em" },
  "radii":           { "sm": "8px", "pill": "9999px" },
  "footer":          { "requiredText": "Client Confidential", "label": "Client Confidential." },
  "rules":           { "checkFontUrlsResolve": false },
  "licensing":       { "assetsRedistributable": false, "note": "…" }
}
```

**Every role must name a token that `tokens.colors` actually declares.** `emit_pack.py`
refuses otherwise — `roles point at tokens that do not exist: [...]` — because a role
pointing at nothing is how a pack ends up silently painting in engine defaults. The example
above is exercised in `evals/`, so it cannot drift from what the tool accepts.

`gradientMarkers` are the hexes that identify a string as an *attempted* brand gradient, so a
near-miss can be reported as a near-miss rather than as an unknown gradient. Pick the stops a
designer would recognise — usually the first and last.

Optional passthrough blocks (`svg`, `pptx`, `charts`, `iconPolicy`, `editor`, `exemptions`,
`ruleNotes`) are copied verbatim if present. Add them when the consuming engine has features
that need brand values — a parametric SVG builder, a PPTX exporter that resolves fonts by full
name per weight, a review editor's properties panel.

## Rules → the data each one needs

`rules` is a set of toggles for mechanical checks. **Turn a rule off when the brand genuinely
has no such constraint** — that is an honest statement about the brand. Never leave a rule on
and invent data to satisfy it; the pack then enforces a fiction.

| rule | needs |
|---|---|
| `requireSlideCanvas` | `canvas.width/height` |
| `requireInlineTailwindConfig` | the config block inside `slide-base.html` |
| `requireCanonicalScaler` | the scaler script in `slide-base.html` |
| `requireDataTemplate` | every template carries `data-template` |
| `requireFooterText` | `footer.requiredText` |
| `requireFontMarker` / `banOffBrandFontFamilies` | `typography.familyMarker`, `familyRequiredPattern` |
| `enforceFontSizeFloor` | `typography.minFontSizePx` |
| `banOffScaleFontWeights` | `typography.allowedWeights` |
| `enforceTokenValues` | tokens in `tailwind.config.js` |
| `enforcePaletteCensus` | `palette.censusSources` |
| `enforceGradientCanon` | `gradients.canonical`, `gradients.brandHexMarkers` |
| `banTailwindDefaultPalette`, `banEmoji`, `banStructuralShadows`, `banLeftAccentBars` | nothing — pure bans |
| `banElementCollisions` | `collisionTolerancePx` |
| `checkFontUrlsResolve` | a `fonts/` directory with the files — leave **off** unless you ship fonts |

A caution about the palette census: it validates a slide's hexes against the union of the
pack's own files, so it is self-referential. It catches a slide that drifts from the pack; it
cannot catch a pack whose tokens were wrong to begin with. That is what `PROVENANCE.md` is for.

## Roles

Engines ask for a role, never a token name — that indirection is what lets shared code stay
brand-blind. Fill at least `primary`, `ink`, `body`, `muted`, `rule`, `surface`, plus `viz`.

Two judgment calls worth care:

**`muted` must be legible.** It carries eyebrows, captions and sub-labels. Check it against the
surface it will sit on; below 4.5:1 it cannot hold body text. Brands very often have no legible
muted — darken theirs, record the ratio and the fact that you derived it, and consider keeping
the brand's own value as `muted-soft` for decorative use at large sizes. Shipping an
inaccessible token harms every deck built afterwards, silently.

**`viz` order is a decision.** Adjacent series must be distinguishable; lead with the two most
separable hues rather than copying palette order.
