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
  1. an explicit path (`--design-system`, or `load(explicit=...)`)
  2. the DECK's own declaration — `design_system` in its deck-state.json. The deck folder
     is found from `deck_dir=`, else $DECK, else `--deck-dir`/`--files`/any path argument
     on the command line (walking up to the nearest deck-state.json), else the cwd.
  3. $DECK_DESIGN_SYSTEM        — the machine-wide default pack
  4. <repo>/imprimatur-design-system — the pack shipped alongside the engine

  (2) exists because hooks and scripts run in the SAME process environment for every deck
  on the machine: with only (3) a client deck built while the env named the EPAM pack had
  every per-write verdict and stop gate judged against the wrong brand (2026-09-22). A deck
  records its pack once, at phase 4a, and every consumer reads it from there.

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

# Engine-side defaults for the pack's optional `motion` block (contract 1.1, 2026-10).
# Brand-neutral by construction: timings, easings, the effect vocabulary the runtime
# implements, the QA tolerance. Which DOM regions play which role (`roleSelectors`,
# `roleEffects`) is brand knowledge and is NOT defaulted — see DesignSystem.motion().
MOTION_DEFAULTS = {
    "enabled": False,
    "entranceBudgetMs": 1600,     # whole entrance build, cover/divider may override per template
    "staggerCapMs": 500,          # items × stagger ≤ this, so a group reads as one beat
    "distancePx": 24,             # fade-up / fade-left travel
    "durationMs": {"fast": 300, "base": 450, "slow": 700},
    "personality": "corporate",   # ONE motion language per deck (1.6.0): corporate · premium · playful · energetic — see choreograph.PERSONALITIES
    "followThrough": True,        # cinematic cards: the content settles a beat after its container
    "easing": {"transition": "power2.inOut"},   # arrival eases come from the personality; `in`/`hero`/`move` override them
    "allowedEffects": ["fade", "fade-up", "fade-left", "rise", "blur-in", "wipe-right", "wipe-up", "wipe-down", "words", "words-mask", "lines-mask",
                       "spring", "whip", "slam", "snap", "rise-rotate", "grow-y", "grow-x", "draw", "count-up",
                       "pop", "lift", "settle", "focus-pull"],
    "level": "auto",              # auto: entrance only · cinematic: slower waterfall pacing, parallax depth, idle camera/drift
    "cinematicBudgetFactor": 1.4,
    "idle": {},                   # cinematic only — see the pack's motion.idle (camera / drift / breathe)
    "variety": "rotate",          # rotate: a role's effect list turns with the slide number · fixed: first entry
    "blur": "subtle",             # how much defocus the brand allows: none · subtle (≈ 40 %) · full
    "focusPull": "on",            # off: a director's focus-pull becomes a settle on the focal element (no whole-slide defocus)
    "transition": {"type": "crossfade", "durationMs": 450},   # crossfade | push | zoom-through | none
    "gsapUrl": "https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js",
    "roleSelectors": {},
    "roleEffects": {},
    "templateOverrides": {},
    "qa": {"maxMae": 0.0, "maxInlineBytes": 4096},
}


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

    # ── motion (deck-motion module, contract 1.1) ──────────────────────
    def motion_enabled(self):
        """True when the pack ships a `motion` block that is not switched off.

        No block → no motion: the engine never animates a brand that has not said how it
        moves. A deck additionally opts in at intake (deck-state.json `motion.enabled`);
        both must hold before choreograph.py or the two-frame viewer do anything.
        """
        block = self.get("motion")
        return isinstance(block, dict) and bool(block.get("enabled", True))

    def motion(self):
        """The pack's motion block merged over MOTION_DEFAULTS (one level deep for dicts).

        Defaults carry only engine-neutral values — durations, easings, the effect vocabulary,
        the QA tolerance. Selectors and role→effect bindings are brand-specific and come from
        the pack alone: an empty `roleSelectors` means choreograph.py finds nothing to animate
        beyond structural groups, which is the correct answer for a pack that declared none.
        """
        block = self.get("motion") if isinstance(self.get("motion"), dict) else {}
        out = {}
        for k, v in MOTION_DEFAULTS.items():
            pv = block.get(k)
            if isinstance(v, dict) and isinstance(pv, dict):
                merged = dict(v)
                merged.update({kk: vv for kk, vv in pv.items() if not str(kk).startswith("$")})
                out[k] = merged
            elif pv is not None:
                out[k] = pv
            else:
                out[k] = v if not isinstance(v, (dict, list)) else (dict(v) if isinstance(v, dict) else list(v))
        for k, v in block.items():
            if k not in out and not str(k).startswith("$"):
                out[k] = v
        out["enabled"] = self.motion_enabled()
        return out

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


STATE_NAME = "deck-state.json"
STATE_KEY = "design_system"


def deck_dir_from(hint):
    """Nearest ancestor of `hint` (a file or directory path) that holds deck-state.json."""
    if not hint:
        return None
    probe = os.path.abspath(os.path.expanduser(str(hint)))
    if os.path.isfile(probe):
        probe = os.path.dirname(probe)
    while True:
        if os.path.isfile(os.path.join(probe, STATE_NAME)):
            return probe
        parent = os.path.dirname(probe)
        if parent == probe:
            return None
        probe = parent


def guess_deck_dir(argv=None):
    """The deck a script or hook is working on, without every caller having to say so.

    Order: $DECK · `--deck-dir X` on the command line · any command-line argument that is
    an existing path inside a deck (a slide file, the deck folder) · the cwd.
    """
    d = deck_dir_from(os.environ.get("DECK"))
    if d:
        return d
    args = list(sys.argv[1:] if argv is None else argv)
    for i, a in enumerate(args):
        if a == "--deck-dir" and i + 1 < len(args):
            d = deck_dir_from(args[i + 1])
            if d:
                return d
        elif a.startswith("--deck-dir="):
            d = deck_dir_from(a.split("=", 1)[1])
            if d:
                return d
    for a in args:
        if not a.startswith("-") and os.path.exists(os.path.expanduser(a)):
            d = deck_dir_from(a)
            if d:
                return d
    return deck_dir_from(os.getcwd())


def pack_from_deck_state(deck_dir):
    """The pack a deck declares in its state file, or None.

    `design_system` is an absolute path (or one relative to the deck folder, or ~-prefixed)
    to a folder holding design-system.json. A declaration that points nowhere is reported
    on stderr and ignored — falling through to the env/default is the lesser evil, but the
    deck should be fixed, not silently re-branded.
    """
    if not deck_dir:
        return None
    path = os.path.join(deck_dir, STATE_NAME)
    try:
        with open(path, encoding="utf-8") as f:
            declared = (json.load(f) or {}).get(STATE_KEY)
    except (OSError, ValueError):
        return None
    if isinstance(declared, dict):
        declared = declared.get("root") or declared.get("path")
    if not declared or not isinstance(declared, str):
        return None
    cand = os.path.expanduser(declared)
    if not os.path.isabs(cand):
        cand = os.path.join(deck_dir, cand)
    cand = os.path.abspath(cand)
    if os.path.isfile(os.path.join(cand, MANIFEST_NAME)):
        return cand
    print(f"ds_config: {path} declares {STATE_KEY}={declared!r} but no {MANIFEST_NAME} "
          f"is there — ignoring it; fix the deck state.", file=sys.stderr)
    return None


def candidates(explicit=None, deck_dir=None):
    """Every place the pack may come from, in precedence order (None entries included)."""
    deck = deck_dir_from(deck_dir) if deck_dir else guess_deck_dir()
    return [explicit, pack_from_deck_state(deck), os.environ.get("DECK_DESIGN_SYSTEM"),
            DEFAULT_DS]


def find_root(explicit=None, deck_dir=None):
    """Locate the active design-system folder without loading it.

    `deck_dir` (a deck folder, or any path inside one) makes the deck's own declaration
    win over the environment; without it the deck is guessed from $DECK, the command line
    and the cwd — see guess_deck_dir().
    """
    for cand in candidates(explicit, deck_dir):
        if cand and os.path.isfile(os.path.join(os.path.expanduser(cand), MANIFEST_NAME)):
            return os.path.abspath(os.path.expanduser(cand))
    return None


def load(explicit=None, deck_dir=None):
    """Load the active design system, or exit with an actionable message.

    Exiting rather than falling back to defaults is deliberate: a silent fallback
    would validate slides against rules nobody declared, and report a pass that
    means nothing.
    """
    root = find_root(explicit, deck_dir)
    if root is None:
        searched = [c for c in candidates(explicit, deck_dir) if c]
        sys.exit(
            f"No design system found. Looked for {MANIFEST_NAME} in:\n"
            + "\n".join(f"  - {os.path.expanduser(c)}" for c in searched)
            + "\n\nEvery brand-specific value the pipeline uses lives in a design-system "
              "folder alongside its design-system.json manifest. Declare it as "
              f"\"{STATE_KEY}\" in the deck's {STATE_NAME}, put one at {DEFAULT_DS}, or set "
              "DECK_DESIGN_SYSTEM to its path."
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
                    help="Deck folder: its deck-state.json 'design_system' selects the pack, and "
                         "it fills DECK= in --header (falls back to $DECK, else '<unset>')")
    args = ap.parse_args()

    ds = load(args.design_system, deck_dir=args.deck_dir)

    if args.header:
        _print_header(ds, args.deck_dir or os.environ.get("DECK"))
    else:
        print(f"{ds.name}  (id={ds.id}, prefix={ds.token_prefix})")
        print(f"root:      {ds.root}")
        print(f"templates: {ds.templates_dir}")
        print(f"canvas:    {ds.canvas[0]}x{ds.canvas[1]}")
        on = sorted(k for k, v in (ds.get("rules", {}) or {}).items() if v is True)
        print(f"rules on:  {', '.join(on)}")
        if ds.motion_enabled():
            m = ds.motion()
            print(f"motion:    on — transition {m['transition'].get('type')} {m['transition'].get('durationMs')} ms, "
                  f"entrance ≤ {m.get('entranceBudgetMs')} ms, roles: {', '.join(k for k in m.get('roleSelectors', {}) if not str(k).startswith('$'))}")
        else:
            print("motion:    off (pack declares no `motion` block — the §1 motion question is moot)")
