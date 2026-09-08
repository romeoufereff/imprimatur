#!/usr/bin/env python3
"""
archetypes.py — generate a pack's baseline template set from its own tokens.

A forged pack arrives with colours and a type scale and no templates, which makes it
unusable: the designer stage picks a template from the pack, so a pack with none can
validate perfectly and still not produce a slide. Hand-authoring a set per brand does not
scale and ages badly, so the layouts are DERIVED from whatever the pack declares.

Two consequences worth understanding:

  * The output is on-brand by construction. Nothing here knows a colour or a size — every
    value is resolved through the pack's roles and type scale, so a template cannot drift
    from the pack that produced it.
  * Layout is arithmetic, not flexbox. Every block is placed at a computed y with an
    explicit gap, because packs are checked for element COLLISIONS in a real browser and
    "it looked fine" is not a defence. Boxes are laid out by a cursor that can only move
    down, which makes overlap structurally impossible rather than merely unlikely.

These are a floor, not a ceiling: competent, on-brand, and boring. The designer stage
authors bespoke slides when a brief deserves one. The floor exists so that every pack —
including one forged from a brand PDF that carried nothing but colours — can make a deck
on day one.
"""

# Semantic slots the layouts ask for, with the size each one WANTS in px. The pack rarely
# has a step of exactly that size, so each slot resolves to the pack's nearest actual step:
# the brand's ramp wins, and a pack with a coarse scale simply reuses steps.
SLOTS = {
    "hero": 88, "title": 54, "heading": 40, "lead": 27,
    "subhead": 25, "body": 20, "label": 18, "eyebrow": 16, "caption": 14,
}


class Ctx:
    """Everything a layout may consult. Nothing brand-specific is hardcoded anywhere else."""

    def __init__(self, prefix, roles, type_scale, canvas, gradients, footer_label, min_px):
        self.p = prefix
        self.roles = roles
        self.scale = type_scale
        self.w = int(canvas.get("width", 1920))
        self.h = int(canvas.get("height", 1080))
        self.gradients = gradients or {}
        self.footer_label = footer_label
        self.min_px = int(min_px or 14)
        self.edge = round(self.w * 0.0417)      # 80px at 1920 — proportional, not assumed
        self.top = round(self.h * 0.0556)       # 60px at 1080
        self._slots = self._resolve_slots()

    def _resolve_slots(self):
        steps = []
        for name, s in (self.scale or {}).items():
            try:
                steps.append((name, float(str(s.get("size", "0")).replace("px", ""))))
            except (TypeError, ValueError):
                continue
        if not steps:
            return {}
        out = {}
        for slot, want in SLOTS.items():
            usable = [s for s in steps if s[1] >= self.min_px] or steps
            out[slot] = min(usable, key=lambda s: abs(s[1] - want))
        return out

    def step(self, slot):
        """Tailwind class for a slot, e.g. text-ds-display."""
        hit = self._slots.get(slot)
        return f"text-{self.p}-{hit[0]}" if hit else ""

    def px(self, slot):
        hit = self._slots.get(slot)
        return hit[1] if hit else float(self.min_px)

    def lh(self, slot):
        hit = self._slots.get(slot)
        if not hit:
            return 1.4
        try:
            return float(self.scale[hit[0]].get("lineHeight", 1.4))
        except (TypeError, ValueError, KeyError):
            return 1.4

    def block_h(self, slot, lines=1):
        return round(self.px(slot) * self.lh(slot) * lines)

    def c(self, role, kind="text"):
        """Class for a semantic role. Empty when the pack does not fill it, so a missing
        role degrades to 'unstyled' rather than to another brand's colour."""
        tok = self.roles.get(role)
        return f"{kind}-{self.p}-{tok}" if isinstance(tok, str) else ""

    def has_gradient(self, name):
        return name in self.gradients


class Cursor:
    """A y-position that only moves down. Overlap is impossible by construction."""

    def __init__(self, y):
        self.y = y

    def take(self, height, gap=0):
        top = self.y
        self.y += height + gap
        return top


def _footer(ctx):  # retained for packs whose base omits chrome; unused by default
    # Matches slide-base so the footer rule sees the same string on every slide.
    return (f'  <div class="absolute bottom-[24px] right-[{ctx.edge}px] flex items-center gap-6\n'
            f'              text-[16px] {ctx.c("muted")} font-{ctx.p}">\n'
            f'    <span>{ctx.footer_label}</span>\n'
            f'    <span class="font-bold {ctx.c("muted")}" id="page-number">1</span>\n'
            f'  </div>')


def _eyebrow(ctx, text, y):
    return (f'  <div class="absolute left-[{ctx.edge}px] top-[{y}px] {ctx.step("eyebrow")} '
            f'{ctx.c("muted")} uppercase tracking-[0.22em]">{text}</div>')


def _cover(ctx):
    cur = Cursor(ctx.top)
    y_eyebrow = cur.take(ctx.block_h("eyebrow"), gap=round(ctx.h * 0.28))
    y_title = cur.take(ctx.block_h("hero", lines=2), gap=32)
    y_lead = cur.take(ctx.block_h("lead", lines=2), gap=0)
    inner = ctx.w - ctx.edge * 2
    return "\n".join([
        _eyebrow(ctx, "Section or client name", y_eyebrow),
        f'  <div class="absolute left-[{ctx.edge}px] top-[{y_title}px] w-[{round(inner * 0.82)}px]">',
        f'    <h1 class="{ctx.step("hero")} {ctx.c("ink")}">The headline that states the point</h1>',
        "  </div>",
        f'  <div class="absolute left-[{ctx.edge}px] top-[{y_lead}px] w-[{round(inner * 0.62)}px]">',
        f'    <p class="{ctx.step("lead")} {ctx.c("body")}">One supporting line that sets up the '
        f'deck without repeating the headline.</p>',
        "  </div>",
    ])


def _section(ctx):
    # The gradient goes on #slide itself, never on a covering sibling: a full-bleed sibling
    # would sit on top of the text and read as a collision in the render check.
    # Nothing small goes on a gradient. A gradient has a light end and a dark end, so a
    # single foreground colour cannot clear 4.5:1 against all of it — measured on the
    # starter pack, body-sized text lands at 3.75:1 over the light stop. Large text only
    # needs 3.0:1, so every element here is sized up rather than recoloured. Keep this
    # property if you add gradient layouts: it is why this slide passes AA at all.
    cur = Cursor(round(ctx.h * 0.34))
    y_num = cur.take(ctx.block_h("heading"), gap=20)
    y_title = cur.take(ctx.block_h("title", lines=2), gap=0)
    on_dark = ctx.c("surface") or ctx.c("muted-soft")
    return "\n".join([
        f'  <div class="absolute left-[{ctx.edge}px] top-[{y_num}px] {ctx.step("heading")} '
        f'{on_dark} tracking-[0.10em]">02</div>',
        f'  <div class="absolute left-[{ctx.edge}px] top-[{y_title}px] w-[{round((ctx.w - ctx.edge * 2) * 0.72)}px]">',
        f'    <h2 class="{ctx.step("title")} {on_dark}">Where the deck turns</h2>',
        "  </div>",
    ])


def _two_column(ctx):
    cur = Cursor(ctx.top)
    y_eyebrow = cur.take(ctx.block_h("eyebrow"), gap=20)
    y_title = cur.take(ctx.block_h("title"), gap=56)
    y_cols = cur.y
    gap = 80
    col_w = (ctx.w - ctx.edge * 2 - gap) // 2
    right_x = ctx.edge + col_w + gap
    body_h = ctx.h - y_cols - round(ctx.h * 0.13)

    def col(x, head, items):
        lis = "\n".join(
            f'      <li class="{ctx.step("body")} {ctx.c("body")} mb-4">{t}</li>' for t in items)
        return "\n".join([
            f'  <div class="absolute left-[{x}px] top-[{y_cols}px] w-[{col_w}px] h-[{body_h}px]">',
            f'    <h3 class="{ctx.step("subhead")} {ctx.c("ink")} mb-6">{head}</h3>',
            "    <ul>", lis, "    </ul>", "  </div>",
        ])

    return "\n".join([
        _eyebrow(ctx, "Comparison", y_eyebrow),
        f'  <h2 class="absolute left-[{ctx.edge}px] top-[{y_title}px] {ctx.step("title")} '
        f'{ctx.c("ink")}">Two things, side by side</h2>',
        col(ctx.edge, "As it is today",
            ["The first point on this side", "A second observation", "A third, kept short"]),
        col(right_x, "Where it should go",
            ["The corresponding change", "What it unlocks", "How we would know"]),
    ])


def _statement(ctx):
    inner = round((ctx.w - ctx.edge * 2) * 0.78)
    h = ctx.block_h("hero", lines=3)
    y = round((ctx.h - h) / 2) - 40
    return "\n".join([
        f'  <div class="absolute left-[{ctx.edge}px] top-[{y}px] w-[{inner}px]">',
        f'    <p class="{ctx.step("hero")} {ctx.c("ink")}">One idea, stated plainly enough '
        f'that nobody needs the notes.</p>',
        "  </div>",
        f'  <div class="absolute left-[{ctx.edge}px] top-[{y + h + 48}px]">',
        f'    <span class="{ctx.step("label")} {ctx.c("muted")}">Attribution or source</span>',
        "  </div>",
    ])


def _metrics(ctx):
    cur = Cursor(ctx.top)
    y_eyebrow = cur.take(ctx.block_h("eyebrow"), gap=20)
    y_title = cur.take(ctx.block_h("title"), gap=64)
    y_cards = cur.y
    gap = 40
    card_w = (ctx.w - ctx.edge * 2 - gap * 2) // 3
    card_h = round(ctx.h * 0.24)
    surface = ctx.c("surface", "bg") or ctx.c("tint", "bg")
    cards = []
    for i, (num, label) in enumerate([("38%", "First measure"), ("2.4x", "Second measure"),
                                      ("11", "Third measure")]):
        x = ctx.edge + i * (card_w + gap)
        cards.append("\n".join([
            # Centred rather than top-aligned: a fixed-height card with its content pinned
            # to the top reads as an accident, and the number is the point of the card.
            f'  <div class="absolute left-[{x}px] top-[{y_cards}px] w-[{card_w}px] '
            f'h-[{card_h}px] {surface} px-10 flex flex-col justify-center">',
            f'    <div class="{ctx.step("heading")} {ctx.c("primary")}">{num}</div>',
            f'    <div class="{ctx.step("label")} {ctx.c("muted")} mt-4">{label}</div>',
            "  </div>",
        ]))
    return "\n".join([
        _eyebrow(ctx, "By the numbers", y_eyebrow),
        f'  <h2 class="absolute left-[{ctx.edge}px] top-[{y_title}px] {ctx.step("title")} '
        f'{ctx.c("ink")}">What the data says</h2>',
        *cards,
    ])


def _closing(ctx):
    cur = Cursor(round(ctx.h * 0.30))
    y_title = cur.take(ctx.block_h("title", lines=1), gap=48)
    y_items = cur.y
    items = "\n".join(
        f'    <li class="{ctx.step("lead")} {ctx.c("body")} mb-6">{t}</li>'
        for t in ["The first thing we would do next", "The decision we need from you",
                  "When we would come back"])
    return "\n".join([
        f'  <h2 class="absolute left-[{ctx.edge}px] top-[{y_title}px] {ctx.step("title")} '
        f'{ctx.c("ink")}">What happens next</h2>',
        f'  <div class="absolute left-[{ctx.edge}px] top-[{y_items}px] '
        f'w-[{round((ctx.w - ctx.edge * 2) * 0.7)}px]">',
        "    <ul>", items, "    </ul>", "  </div>",
    ])


ARCHETYPES = [
    # Gradient slots belong only to layouts whose text is styled for a dark ground. The
    # cover sets its headline in the ink role, which is picked to sit on the light surface.
    ("01-cover", "Opening slide: eyebrow, headline, one supporting line.", _cover, None),
    ("02-section", "Divider that marks a turn in the argument.", _section, "section"),
    ("03-two-column", "Two things compared side by side.", _two_column, None),
    ("04-statement", "One idea, large, with room around it.", _statement, None),
    ("05-metrics", "Three measures as equal cards.", _metrics, None),
    ("06-closing", "Next steps and the ask.", _closing, None),
]


def build(prefix, roles, type_scale, canvas, gradients, footer_label, min_px):
    """Returns [{file, template, body, gradient, description}] for the pack."""
    ctx = Ctx(prefix, roles, type_scale, canvas, gradients, footer_label, min_px)
    out = []
    for name, desc, fn, grad in ARCHETYPES:
        out.append({
            "file": f"{name}.html",
            "template": name,
            "description": desc,
            # A gradient slot is only used if the pack actually declares that gradient;
            # otherwise the layout falls back to the plain canvas rather than inventing one.
            "gradient": grad if (grad and ctx.has_gradient(grad)) else None,
            # No footer here: slide-base already carries the footer chrome, and emitting a
            # second one stacks identical text on itself — which the render check correctly
            # reports as a collision. The base owns the chrome; archetypes own the content.
            "body": fn(ctx),
        })
    return out
