#!/usr/bin/env python3
"""
Design-system resolver — the one place the engine learns what brand it is running.

Every other script in scripts/ imports from here rather than hardcoding a token
name, hex, font, or footer string. That separation is what makes the pipeline
design-system agnostic: replace the design-system/ folder (or point
DECK_DESIGN_SYSTEM at a different one) and the same engine produces a different
flavor, because the only thing it ever knew about the brand came from the pack's
own design-system.json.

Resolution order:
  1. $DECK_DESIGN_SYSTEM        — absolute path to a design-system folder
  2. <repo>/imprimatur-design-system — the pack shipped alongside the engine

Usage:
    from ds_config import load
    ds = load()
    ds.root                  # absolute path to the active pack
    ds.name                  # the pack's display name
    ds.token_prefix          # the pack's Tailwind token prefix
    ds.templates_dir         # <root>/templates
    ds.rule("banEmoji")      # True/False, missing rules default to False
    ds.color("primary")      # hex for a semantic role, resolved via the pack's roles map
    ds.palette("viz")        # ordered hex list for a list-valued role
    ds.get("typography.minFontSizePx", 14)
"""

import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _paths import plugin_root, default_pack  # noqa: E402

PLUGIN_ROOT = plugin_root(__file__)
# The pack ships as a sibling folder of the plugin, not inside it, so that the
# engine and the brand content stay separable even though they travel together.
DEFAULT_DS = default_pack(__file__)
MANIFEST_NAME = "design-system.json"

# Major version of the pack contract this engine implements. A pack declares the contract it
# was built against; a mismatch in the MAJOR means the engine would be reading fields that
# have changed shape, which fails in ways that look like design bugs rather than version
# bugs. Refusing loudly costs one clear error; guessing costs an afternoon.
SUPPORTED_CONTRACT = 1


class DesignSystem:
    def __init__(self, root, data):
        self.root = root
        self.data = data

    def check_contract(self):
        """Returns a problem string when this pack cannot be trusted with this engine."""
        raw = self.get("contractVersion")
        if raw is None:
            # Packs that predate the contract field are treated as the current major —
            # breaking every already-working pack would be worse than the risk. verify_pack.py
            # reports the omission when the pack is built or checked; load() stays quiet
            # because it runs on every script invocation.
            return None
        try:
            major = int(str(raw).split(".")[0])
        except (TypeError, ValueError):
            return f"contractVersion {raw!r} is not a version number"
        if major > SUPPORTED_CONTRACT:
            return (f"pack declares contract {raw}, but this engine implements "
                    f"{SUPPORTED_CONTRACT}.x — upgrade the engine, or re-forge the pack "
                    f"against this one")
        if major < SUPPORTED_CONTRACT:
            return (f"pack declares contract {raw}, which this engine ({SUPPORTED_CONTRACT}.x) "
                    f"no longer implements — re-forge the pack")
        return None

    # ── generic access ────────────────────────────────────────────────
    def get(self, dotted, default=None):
        """Read a nested key by dotted path, e.g. get('typography.allowedWeights')."""
        node = self.data
        for part in dotted.split("."):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node

    def rule(self, name):
        """A check is on only if the pack says so — unknown rules are off."""
        return bool(self.get("rules." + name, False))

    def note(self, name, default=""):
        """Pack-authored explanation appended to a failure message."""
        return self.get("ruleNotes." + name, default) or default

    def path(self, *parts):
        return os.path.join(self.root, *parts)

    # ── frequently used values ────────────────────────────────────────
    @property
    def id(self):
        return self.get("id", "design-system")

    @property
    def name(self):
        return self.get("name", "Design System")

    @property
    def token_prefix(self):
        return self.get("tokens.prefix", "ds")

    @property
    def config_file(self):
        return self.path(self.get("tokens.configFile", "tailwind.config.js"))

    @property
    def base_file(self):
        return self.path(self.get("tokens.baseFile", "slide-base.html"))

    @property
    def templates_dir(self):
        return self.path(self.get("tokens.templatesDir", "templates"))

    @property
    def fonts_dir(self):
        return self.path(self.get("tokens.fontsDir", "fonts"))

    @property
    def canvas(self):
        return (int(self.get("canvas.width", 1920)), int(self.get("canvas.height", 1080)))

    def token_class_example(self):
        """A human-readable stand-in used in failure messages, e.g. '<prefix>-*'."""
        return f"{self.token_prefix}-*"

    # ── role-based color access ───────────────────────────────────────
    # Engine code that needs a color asks for a ROLE ('primary', 'ink', 'rule'),
    # never a token name. The pack's `roles` map resolves the role onto its own
    # token, and the token's hex comes from its Tailwind config. That indirection
    # is why the SVG builder, the PPTX chart styling, and the template gallery can
    # be shared across design systems without knowing any of them.

    def tokens(self):
        """{token-name-without-prefix: '#RRGGBB'} parsed from the pack's config."""
        if getattr(self, "_tokens", None) is None:
            try:
                cfg = open(self.config_file, encoding="utf-8").read()
            except OSError:
                cfg = ""
            self._tokens = dict(re.findall(
                r"'" + re.escape(self.token_prefix) + r"-([\w-]+)':\s*'(#[0-9A-Fa-f]{6})'", cfg))
        return self._tokens

    def color(self, role, default=None):
        """Hex for a semantic role, or `default` if the pack doesn't fill that role."""
        token = self.get("roles." + role)
        if isinstance(token, str):
            return self.tokens().get(token, default)
        return default

    def palette(self, role, default=None):
        """Ordered hex list for a list-valued role (e.g. 'viz' chart series order)."""
        names = self.get("roles." + role)
        if not isinstance(names, list):
            return list(default or [])
        toks = self.tokens()
        out = [toks[n] for n in names if n in toks]
        return out or list(default or [])


    # ── editable vocabulary (deck-review properties panel) ────────────
    # The review harness's Edit mode may only offer values THIS pack sanctions,
    # so its properties panel is built from the pack rather than hardcoded.
    # Anything not returned here simply isn't offerable — which is what stops
    # direct manipulation from authoring the off-brand styling validate.py
    # exists to reject.

    def _config_text(self):
        if getattr(self, "_cfg_text", None) is None:
            try:
                self._cfg_text = open(self.config_file, encoding="utf-8").read()
            except OSError:
                self._cfg_text = ""
        return self._cfg_text

    def _block(self, key):
        """Raw body of a `key: { … }` block in the pack's Tailwind config."""
        txt = self._config_text()
        m = re.search(r"\b" + re.escape(key) + r"\s*:\s*\{", txt)
        if not m:
            return ""
        start = m.end() - 1
        depth = 0
        for j in range(start, len(txt)):
            if txt[j] == "{":
                depth += 1
            elif txt[j] == "}":
                depth -= 1
                if depth == 0:
                    return txt[start + 1:j]
        return ""

    def type_scale(self):
        """{step: {'size','lineHeight','fontWeight'}} — the pack's whole type ramp.

        Handles both Tailwind spellings: `'x': ['40px', { lineHeight, fontWeight }]`
        and the bare `'x': '40px'`.
        """
        if getattr(self, "_scale", None) is None:
            out = {}
            body = self._block("fontSize")
            pref = re.escape(self.token_prefix)
            for name, size, extra in re.findall(
                    r"'" + pref + r"-([\w-]+)'\s*:\s*\[\s*'([^']+)'\s*,\s*\{([^}]*)\}", body):
                step = {"size": size}
                lh = re.search(r"lineHeight\s*:\s*'([^']+)'", extra)
                fw = re.search(r"fontWeight\s*:\s*'?(\d+)'?", extra)
                if lh:
                    step["lineHeight"] = lh.group(1)
                if fw:
                    step["fontWeight"] = fw.group(1)
                out[name] = step
            for name, size in re.findall(
                    r"'" + pref + r"-([\w-]+)'\s*:\s*'([\d.]+(?:px|rem|em))'", body):
                out.setdefault(name, {"size": size})
            self._scale = out
        return self._scale

    def radii(self):
        """{name: value} from the pack's borderRadius scale."""
        pref = re.escape(self.token_prefix)
        return dict(re.findall(r"'" + pref + r"-([\w-]+)'\s*:\s*'([^']+)'", self._block("borderRadius")))

    def gradients(self):
        """{name: css value} from the pack's backgroundImage scale.

        These are the ONLY gradients Edit mode offers. A reviewer cannot compose a
        new one in the panel, which is what keeps enforceGradientCanon meaningful —
        every gradient a direct edit can produce is one the pack already sanctions.
        """
        pref = re.escape(self.token_prefix)
        return dict(re.findall(
            r"'" + pref + r"-([\w-]+)'\s*:\s*'((?:linear|radial|conic)-gradient\([^']+\))'",
            self._block("backgroundImage")))

    def gradient_policy(self):
        """Pack-declared rules on where its gradients may be used (see editor.gradients)."""
        return self.get("editor.gradients", {}) or {}

    def spacing(self):
        """{name: value} from the pack's spacing constants (slide edges, chrome…)."""
        return dict(re.findall(r"'([\w-]+)'\s*:\s*'([^']+)'", self._block("spacing")))

    def spacing_steps(self):
        """Ordered px steps the editor offers for padding/gap/margin.

        The pack may declare `editor.spacingSteps`; otherwise it's multiples of the
        grid, which every layout in the pack is already built on.
        """
        declared = self.get("editor.spacingSteps")
        if isinstance(declared, list) and declared:
            return [int(v) for v in declared]
        g = self.grid_px()
        return [0, g // 2, g, g * 2, g * 3, g * 4, g * 5, g * 6, g * 8, g * 10]

    def grid_px(self):
        """Snap grid for editor drag/resize, in slide pixels."""
        try:
            return max(1, int(self.get("editor.gridPx", 8)))
        except (TypeError, ValueError):
            return 8

    def editor_vocabulary(self):
        """Everything the review harness needs to build a brand-safe properties panel."""
        w, h = self.canvas
        return {
            "id": self.id,
            "name": self.name,
            "prefix": self.token_prefix,
            "canvas": {"width": w, "height": h},
            "colors": self.tokens(),
            "roles": self.get("roles", {}) or {},
            "typeScale": self.type_scale(),
            "weights": [int(x) for x in (self.get("typography.allowedWeights") or [300, 400, 700])],
            "minFontSizePx": int(self.get("typography.minFontSizePx", 14)),
            "radii": self.radii(),
            "gradients": self.gradients(),
            "gradientPolicy": self.gradient_policy(),
            "spacing": self.spacing(),
            "spacingSteps": self.spacing_steps(),
            "gridPx": self.grid_px(),
        }


def find_root(explicit=None):
    """Locate the active design-system folder without loading it."""
    candidates = [explicit, os.environ.get("DECK_DESIGN_SYSTEM"), DEFAULT_DS]
    for cand in candidates:
        if cand and os.path.isfile(os.path.join(os.path.expanduser(cand), MANIFEST_NAME)):
            return os.path.abspath(os.path.expanduser(cand))
    return None


def load(explicit=None):
    """Load the active design system, or exit with an actionable message.

    Exiting rather than falling back to defaults is deliberate: a silent fallback
    would validate slides against rules nobody declared, and report a pass that
    means nothing.
    """
    root = find_root(explicit)
    if root is None:
        searched = [c for c in (explicit, os.environ.get("DECK_DESIGN_SYSTEM"), DEFAULT_DS) if c]
        sys.exit(
            f"No design system found. Looked for {MANIFEST_NAME} in:\n"
            + "\n".join(f"  - {os.path.expanduser(c)}" for c in searched)
            + "\n\nEvery brand-specific value the pipeline uses lives in a design-system "
              "folder alongside its design-system.json manifest. Put one at "
              f"{DEFAULT_DS}, or set DECK_DESIGN_SYSTEM to its path."
        )
    with open(os.path.join(root, MANIFEST_NAME), encoding="utf-8") as f:
        data = json.load(f)
    ds = DesignSystem(root, data)

    # A pack built against a different major of the contract would be read with fields
    # that have changed shape. That surfaces as inexplicable design bugs rather than as
    # a version problem, so refuse here: one clear error beats an afternoon.
    problem = ds.check_contract()
    if problem:
        sys.exit(
            f"Design-system contract mismatch.\n"
            f"  pack:    {root}\n"
            f"  problem: {problem}\n\n"
            f"Rebuild the pack with a matching forge, or update the engine."
        )
    return ds


def _print_header(ds, deck_dir):
    """WP8: the ready-to-paste boot-sequence block every spawn prompt and
    SendMessage carries as its first line, so a fresh agent never has to
    `find` / `ls ~/.claude/plugins` its way to the plugin, pack, or deck.
    """
    deck_abs = os.path.abspath(deck_dir) if deck_dir else "<unset>"
    print(f"PLUGIN={PLUGIN_ROOT} · PACK={ds.root} · DECK={deck_abs} · DS_NAME={ds.name}")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(
        description="Design-system resolver — inspect the active pack, or print its "
                    "boot-sequence header block.")
    ap.add_argument("--design-system", default=None, help="Override the active pack")
    ap.add_argument("--header", action="store_true",
                    help="Print 'PLUGIN=<abs> · PACK=<abs> · DECK=<abs> · DS_NAME=<name>' "
                        "instead of the human-readable summary (WP8)")
    ap.add_argument("--deck-dir", default=None,
                    help="Deck folder for DECK= in --header (falls back to $DECK, else '<unset>')")
    args = ap.parse_args()

    ds = load(args.design_system)

    if args.header:
        _print_header(ds, args.deck_dir or os.environ.get("DECK"))
    else:
        print(f"{ds.name}  (id={ds.id}, prefix={ds.token_prefix})")
        print(f"root:      {ds.root}")
        print(f"templates: {ds.templates_dir}")
        print(f"canvas:    {ds.canvas[0]}x{ds.canvas[1]}")
        on = sorted(k for k, v in (ds.get("rules", {}) or {}).items() if v is True)
        print(f"rules on:  {', '.join(on)}")
