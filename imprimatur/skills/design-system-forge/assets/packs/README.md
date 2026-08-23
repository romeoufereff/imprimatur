# Reference pack decisions

`decisions.json` files for packs this forge can rebuild from nothing.

`starter.decisions.json` produces **Imprimatur Starter** — the neutral, MIT-safe pack: authored
colours, a system font stack, a geometric placeholder mark. No third-party fonts, no trademarks.

It lives here rather than as a checked-in folder of HTML because a generated pack that is also
hand-maintained drifts from its generator. Rebuild it whenever you need it:

```bash
python3 ../{PLUGIN}/scripts/emit_pack.py --authored \
    --decisions starter.decisions.json --out <somewhere>/imprimatur-design-system --force
```

That is also how you produce the public design-system repo: rebuild the starter into a clean
folder rather than stripping a brand pack down by hand.
