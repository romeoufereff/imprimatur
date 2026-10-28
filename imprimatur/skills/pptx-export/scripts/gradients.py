#!/usr/bin/env python3
"""
pptx-export — gradient geometry shared by extract_ir.py (HTML) and svg2shapes.py (SVG).

PowerPoint fills every shape with its OWN gradient: stop 0 at one edge of the shape,
stop 100 at the other. HTML and SVG can instead paint one gradient across several
shapes — a CSS background sized and positioned to run across three header bars
(`background-size: calc(300% + 80px) 100%`), an SVG gradient in `userSpaceOnUse`
spanning two curves. Re-applying the full ramp per shape restarts the colour at
every bar. The fix is to cut, for each shape, the slice of the shared ramp that
shape actually shows and re-express it as that shape's own stops (`remap_stops`).

Stops here are (pos, '#RRGGBB', alpha) tuples with pos as a 0..1 fraction.
"""

import math
import re


def _rgb(c):
    c = c.lstrip('#')
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))


def _hex(rgb):
    return '#%02X%02X%02X' % tuple(int(round(max(0, min(255, v)))) for v in rgb)


def color_at(stops, t):
    """Colour of a padded gradient at parameter t (clamped, sRGB-linear interpolation —
    what both browsers and PowerPoint do between stops)."""
    stops = sorted(stops, key=lambda s: s[0])
    if t <= stops[0][0]:
        return stops[0][1], stops[0][2]
    if t >= stops[-1][0]:
        return stops[-1][1], stops[-1][2]
    for (p0, c0, a0), (p1, c1, a1) in zip(stops, stops[1:]):
        if p0 <= t <= p1:
            k = 0.0 if p1 == p0 else (t - p0) / (p1 - p0)
            r0, r1 = _rgb(c0), _rgb(c1)
            return _hex([r0[i] + (r1[i] - r0[i]) * k for i in range(3)]), a0 + (a1 - a0) * k
    return stops[-1][1], stops[-1][2]


def remap_stops(stops, t0, t1):
    """The slice [t0, t1] of a padded gradient, re-expressed as stops over 0..1.

    t0/t1 are the source-gradient parameters at the shape's own gradient start/end
    (they may lie outside 0..1 — the pad colour then fills that part, as in the
    browser). Interior source stops keep their colours; the ends are interpolated."""
    if abs(t1 - t0) < 1e-9:
        c, a = color_at(stops, t0)
        return [(0.0, c, a), (1.0, c, a)]
    out = [(0.0,) + color_at(stops, t0)]
    for p, c, a in stops:
        f = (p - t0) / (t1 - t0)
        if 1e-6 < f < 1 - 1e-6:
            out.append((f, c, a))
    out.append((1.0,) + color_at(stops, t1))
    return sorted(out, key=lambda s: s[0])


# ------------------------------------------------------------------ CSS backgrounds

def css_length(expr, base):
    """Resolve one computed CSS length — `12px`, `30%`, `calc(-100% - 40px)` — against
    `base` (the length a percentage refers to). calc() is linear in % and px here;
    anything else (multiplication, em, vw, nested functions) returns None so the caller
    can fall back instead of guessing."""
    e = (expr or '').strip()
    kw = {'left': '0%', 'top': '0%', 'center': '50%', 'right': '100%', 'bottom': '100%'}
    e = kw.get(e, e)
    if e.startswith('calc(') and e.endswith(')'):
        e = e[5:-1]
    if re.search(r'[*/]|calc\(|[a-oq-z]{2,}', e.replace('px', '')):
        return None
    total, pos = 0.0, 0
    for m in re.finditer(r'\s*([+-])?\s*([\d.]+(?:e-?\d+)?)(%|px)?', e):
        if m.start() != pos or not m.group(0).strip():
            if m.group(0).strip():
                return None
            continue
        pos = m.end()
        v = float(m.group(2)) * (-1 if m.group(1) == '-' else 1)
        unit = m.group(3) or ('px' if v == 0 else None)
        if unit is None:
            return None
        total += v * base / 100.0 if unit == '%' else v
    if e[pos:].strip():
        return None
    return total


def split_layer_pair(value):
    """'calc(300% + 80px) 100%' -> ['calc(300% + 80px)', '100%'] (spaces inside
    parentheses do not split)."""
    out, depth, cur = [], 0, ''
    for ch in (value or '').strip():
        if ch == '(':
            depth += 1
        elif ch == ')':
            depth -= 1
        if ch == ' ' and depth == 0:
            if cur:
                out.append(cur)
            cur = ''
        else:
            cur += ch
    if cur:
        out.append(cur)
    return out


def css_gradient_window(angle, stops, box_w, box_h, size, position, repeat='repeat'):
    """A CSS linear-gradient painted with a non-default background-size/-position shows
    only a window of the full gradient image. Returns the stops of that window as the
    element's own gradient (same angle), or None if the layout is not one this can
    reproduce (unparseable lengths, or a tile edge inside the element — a seam one
    linear gradient cannot express).

    angle: CSS degrees (0 = up, clockwise). stops: [(pos 0..1, hex, alpha)].
    box_w/box_h: the background positioning area (the padding box).
    repeat: computed background-repeat. With tiling on (the CSS default) a position that
    pushes the image off the element is legal — the neighbouring tile fills in. The
    slide-12 header bars rely on exactly that: `calc(-100% - 40px)` resolves to +1160px
    against a -1200px base and the PREVIOUS tile supplies the visible slice."""
    sz = split_layer_pair(size)
    if not sz or sz[0] in ('cover', 'contain'):
        iw, ih = box_w, box_h          # a gradient has no intrinsic size: cover = the area
    else:
        iw = box_w if sz[0] == 'auto' else css_length(sz[0], box_w)
        hs = sz[1] if len(sz) > 1 else 'auto'
        ih = box_h if hs == 'auto' else css_length(hs, box_h)
    if iw is None or ih is None or iw <= 0 or ih <= 0:
        return None
    ps = split_layer_pair(position) or ['0%', '0%']
    if len(ps) == 1:
        ps.append('50%')
    # background-position %: p * (area - image) — the base can be negative
    ox = css_length(ps[0], box_w - iw)
    oy = css_length(ps[1], box_h - ih)
    if ox is None or oy is None:
        return None
    rep = split_layer_pair(repeat) or ['repeat']
    if len(rep) == 1:   # one-keyword forms expand to an x/y pair
        rep = {'repeat-x': ['repeat', 'no-repeat'],
               'repeat-y': ['no-repeat', 'repeat']}.get(rep[0], rep * 2)
    rx, ry = (k in ('repeat', 'round', 'space') for k in rep[:2])
    if rx:   # shift to the tile that covers the element's left edge
        ox = ox - math.ceil((ox - 1e-6) / iw) * iw
    if ry:
        oy = oy - math.ceil((oy - 1e-6) / ih) * ih
    if ox > 0.5 or oy > 0.5 or ox + iw < box_w - 0.5 or oy + ih < box_h - 0.5:
        return None    # a tile edge falls inside the element (or no tiling) → not one gradient
    if abs(ox) < 0.5 and abs(oy) < 0.5 and abs(iw - box_w) < 0.5 and abs(ih - box_h) < 0.5:
        return [tuple(s) for s in stops]   # default layout — nothing to cut
    a = math.radians(angle)
    dx, dy = math.sin(a), -math.cos(a)
    L = abs(iw * dx) + abs(ih * dy)

    def t(x, y):   # element-px point → parameter along the IMAGE's gradient line
        return ((x - ox - iw / 2) * dx + (y - oy - ih / 2) * dy) / L + 0.5

    ts = [t(x, y) for x in (0, box_w) for y in (0, box_h)]
    return remap_stops(stops, min(ts), max(ts))


# ------------------------------------------------------------------ SVG userSpaceOnUse

def user_space_window(stops, p1, p2, bbox):
    """An SVG linearGradient in userSpaceOnUse (p1→p2, already in slide px) painted on a
    shape with bounding box (x, y, w, h): returns (angle_deg, stops) for that shape's
    own gradient — DrawingML angle convention (0 = right, clockwise)."""
    vx, vy = p2[0] - p1[0], p2[1] - p1[1]
    L2 = vx * vx + vy * vy
    if L2 < 1e-9:
        c, al = color_at(stops, 1.0)
        return 0.0, [(0.0, c, al), (1.0, c, al)]
    x, y, w, h = bbox
    ts = [((cx - p1[0]) * vx + (cy - p1[1]) * vy) / L2
          for cx in (x, x + w) for cy in (y, y + h)]
    return math.degrees(math.atan2(vy, vx)) % 360, remap_stops(stops, min(ts), max(ts))
