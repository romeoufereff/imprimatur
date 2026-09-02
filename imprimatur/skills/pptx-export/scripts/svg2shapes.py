#!/usr/bin/env python3
"""
pptx-export — SVG → native-shape model (the C2 converter).

Parses a serialized diagram SVG (the `asset_svg` extract_ir.py writes) into a flat list
of shape-model nodes the builder turns into REAL PowerPoint shapes — rects, ovals,
freeform beziers (a:custGeom), textboxes — grouped so the diagram moves/scales as one
and ungroups for editing. This is what makes an exported diagram adjustable in
PowerPoint instead of a picture.

Scope = the design system's SVG grammar (rect/circle/ellipse/line/polyline/polygon/
path/text/g, linearGradient incl. userSpaceOnUse, marker-end arrowheads, feDropShadow,
transforms, dashes, text-anchor). Anything outside it raises Unconvertible with a reason
and the builder falls back to today's svgBlip: textPath (curved labels), mask, pattern,
radialGradient, <use>, <image>, <foreignObject>, or >150 elements (ECharts).
<clipPath> definitions are skipped rather than rejected: ECharts' SVG renderer wraps every
plot in a clip equal to the plot area, which trims nothing visible, and PowerPoint shapes
cannot carry a clip anyway — so a clipped group converts to native shapes unclipped.

Model coordinates are SLIDE PX (the caller passes the placement rect); the builder does
px→EMU. Text sizes stay px (builder applies PT_PER_PX).

Self-verification: `model_to_svg()` re-renders the parsed model back to SVG;
`--verify file.svg` screenshots source and re-render and content-MAEs them — the parse
is proven numerically BEFORE PowerPoint ever sees it.

Usage:
    python3 svg2shapes.py file.svg --verify        # parse + render-diff proof
    python3 svg2shapes.py file.svg --dump          # print the model JSON
"""

import json
import math
import os
import re
import sys
import xml.etree.ElementTree as ET

# Depth-independent: anchor on the plugin marker rather than counting `..` hops,
# so moving this file between skill folders cannot silently resolve to the wrong
# directory. See scripts/_paths.py.
_here = os.path.dirname(os.path.abspath(__file__))
_probe = _here
while not os.path.isdir(os.path.join(_probe, ".claude-plugin")):
    _parent = os.path.dirname(_probe)
    if _parent == _probe:
        raise RuntimeError(f"No .claude-plugin/ found above {_here}")
    _probe = _parent
sys.path.insert(0, os.path.join(_probe, "scripts"))
from ds_config import load as _load_ds  # noqa: E402

# Font written back into SVG by model_to_svg (the render-diff verify path). Read from
# the active design system so the proof compares like with like whichever pack is in play.
_TEXT_FONT = _load_ds().get("typography.familyLabel", "sans-serif")

MAX_ELEMENTS = 150

UNSUPPORTED = {'textPath', 'mask', 'pattern', 'radialGradient',
               'use', 'image', 'foreignObject', 'symbol', 'switch'}


class Unconvertible(Exception):
    pass


def _strip(tag):
    return tag.split('}', 1)[1] if '}' in tag else tag


# ---------------------------------------------------------------- transforms

def mat_identity():
    return (1, 0, 0, 1, 0, 0)  # a b c d e f  (SVG matrix order)


def mat_mul(m, n):
    a1, b1, c1, d1, e1, f1 = m
    a2, b2, c2, d2, e2, f2 = n
    return (a1 * a2 + c1 * b2, b1 * a2 + d1 * b2,
            a1 * c2 + c1 * d2, b1 * c2 + d1 * d2,
            a1 * e2 + c1 * f2 + e1, b1 * e2 + d1 * f2 + f1)


def mat_apply(m, x, y):
    a, b, c, d, e, f = m
    return (a * x + c * y + e, b * x + d * y + f)


def parse_transform(s):
    m = mat_identity()
    for name, args in re.findall(r'(\w+)\s*\(([^)]*)\)', s or ''):
        v = [float(t) for t in re.split(r'[\s,]+', args.strip()) if t]
        if name == 'translate':
            t = (1, 0, 0, 1, v[0], v[1] if len(v) > 1 else 0)
        elif name == 'scale':
            t = (v[0], 0, 0, v[1] if len(v) > 1 else v[0], 0, 0)
        elif name == 'rotate':
            a = math.radians(v[0])
            r = (math.cos(a), math.sin(a), -math.sin(a), math.cos(a), 0, 0)
            if len(v) == 3:
                t = mat_mul(mat_mul((1, 0, 0, 1, v[1], v[2]), r), (1, 0, 0, 1, -v[1], -v[2]))
            else:
                t = r
        elif name == 'matrix' and len(v) == 6:
            t = tuple(v)
        else:
            continue
        m = mat_mul(m, t)
    return m


def mat_is_rotated(m):
    a, b, c, d, _, _ = m
    return abs(b) > 1e-6 or abs(c) > 1e-6


def mat_rotation_deg(m):
    return math.degrees(math.atan2(m[1], m[0]))


def mat_scale_avg(m):
    a, b, c, d, _, _ = m
    return (math.hypot(a, b) + math.hypot(c, d)) / 2


# ---------------------------------------------------------------- path parsing

_NUM = re.compile(r'[-+]?(?:\d*\.\d+|\d+\.?)(?:[eE][-+]?\d+)?')


def parse_path(d):
    """→ list of subpaths: {'start':(x,y), 'closed':bool, 'segs':[('l',x,y)|('c',x1,y1,x2,y2,x,y)]}
    All commands normalized to absolute lines/cubics; arcs → cubic approximation."""
    tokens = re.findall(r'[MmLlHhVvCcSsQqTtAaZz]|' + _NUM.pattern, d)
    i, n = 0, len(tokens)
    subpaths, segs, start = [], [], None
    cx = cy = 0.0
    last_cmd = None
    last_ctrl = None  # for S/T reflection

    def num():
        nonlocal i
        v = float(tokens[i]); i += 1
        return v

    def flush(closed):
        nonlocal segs, start
        if start is not None and segs:
            subpaths.append({'start': start, 'closed': closed, 'segs': segs})
        segs = []

    while i < n:
        t = tokens[i]
        if re.match(r'[A-Za-z]', t):
            cmd = t; i += 1
        else:
            cmd = last_cmd  # implicit repeat
            if cmd in 'Mm':
                cmd = 'L' if cmd == 'M' else 'l'
        rel = cmd.islower()
        C = cmd.upper()
        if C == 'M':
            flush(False)
            x, y = num(), num()
            if rel:
                x, y = cx + x, cy + y
            cx, cy = x, y
            start = (x, y)
            last_ctrl = None
        elif C == 'Z':
            if start is not None:
                if (cx, cy) != start:
                    segs.append(('l', start[0], start[1]))
                cx, cy = start
                flush(True)
                start = (cx, cy)
            last_ctrl = None
        elif C == 'L':
            x, y = num(), num()
            if rel:
                x, y = cx + x, cy + y
            segs.append(('l', x, y)); cx, cy = x, y; last_ctrl = None
        elif C == 'H':
            x = num()
            if rel:
                x = cx + x
            segs.append(('l', x, cy)); cx = x; last_ctrl = None
        elif C == 'V':
            y = num()
            if rel:
                y = cy + y
            segs.append(('l', cx, y)); cy = y; last_ctrl = None
        elif C in ('C', 'S'):
            if C == 'C':
                x1, y1 = num(), num()
                if rel:
                    x1, y1 = cx + x1, cy + y1
            else:
                if last_cmd and last_cmd.upper() in 'CS' and last_ctrl:
                    x1, y1 = 2 * cx - last_ctrl[0], 2 * cy - last_ctrl[1]
                else:
                    x1, y1 = cx, cy
            x2, y2 = num(), num()
            x, y = num(), num()
            if rel:
                x2, y2, x, y = cx + x2, cy + y2, cx + x, cy + y
            segs.append(('c', x1, y1, x2, y2, x, y))
            last_ctrl = (x2, y2); cx, cy = x, y
        elif C in ('Q', 'T'):
            if C == 'Q':
                qx, qy = num(), num()
                if rel:
                    qx, qy = cx + qx, cy + qy
            else:
                if last_cmd and last_cmd.upper() in 'QT' and last_ctrl:
                    qx, qy = 2 * cx - last_ctrl[0], 2 * cy - last_ctrl[1]
                else:
                    qx, qy = cx, cy
            x, y = num(), num()
            if rel:
                x, y = cx + x, cy + y
            # quadratic → cubic
            c1 = (cx + 2 / 3 * (qx - cx), cy + 2 / 3 * (qy - cy))
            c2 = (x + 2 / 3 * (qx - x), y + 2 / 3 * (qy - y))
            segs.append(('c', c1[0], c1[1], c2[0], c2[1], x, y))
            last_ctrl = (qx, qy); cx, cy = x, y
        elif C == 'A':
            rx, ry, rot, laf, swf = num(), num(), num(), num(), num()
            x, y = num(), num()
            if rel:
                x, y = cx + x, cy + y
            for c1x, c1y, c2x, c2y, ex, ey in _arc_to_cubics(cx, cy, rx, ry, rot, laf, swf, x, y):
                segs.append(('c', c1x, c1y, c2x, c2y, ex, ey))
            cx, cy = x, y; last_ctrl = None
        else:
            raise Unconvertible(f'path command {cmd!r}')
        last_cmd = cmd
    flush(False)
    return subpaths


def _arc_to_cubics(x1, y1, rx, ry, phi_deg, laf, swf, x2, y2):
    """SVG arc endpoint → center parametrization → ≤90° cubic segments."""
    if rx == 0 or ry == 0 or (x1, y1) == (x2, y2):
        return [(x1, y1, x2, y2, x2, y2)]
    phi = math.radians(phi_deg)
    cosp, sinp = math.cos(phi), math.sin(phi)
    dx, dy = (x1 - x2) / 2, (y1 - y2) / 2
    x1p = cosp * dx + sinp * dy
    y1p = -sinp * dx + cosp * dy
    rx, ry = abs(rx), abs(ry)
    lam = x1p ** 2 / rx ** 2 + y1p ** 2 / ry ** 2
    if lam > 1:
        s = math.sqrt(lam)
        rx, ry = rx * s, ry * s
    num = rx ** 2 * ry ** 2 - rx ** 2 * y1p ** 2 - ry ** 2 * x1p ** 2
    den = rx ** 2 * y1p ** 2 + ry ** 2 * x1p ** 2
    co = math.sqrt(max(0.0, num / den)) if den else 0.0
    if laf == swf:
        co = -co
    cxp = co * rx * y1p / ry
    cyp = -co * ry * x1p / rx
    cx = cosp * cxp - sinp * cyp + (x1 + x2) / 2
    cy = sinp * cxp + cosp * cyp + (y1 + y2) / 2

    def ang(ux, uy, vx, vy):
        d = math.hypot(ux, uy) * math.hypot(vx, vy)
        c = max(-1.0, min(1.0, (ux * vx + uy * vy) / d))
        a = math.acos(c)
        return a if ux * vy - uy * vx >= 0 else -a

    th1 = ang(1, 0, (x1p - cxp) / rx, (y1p - cyp) / ry)
    dth = ang((x1p - cxp) / rx, (y1p - cyp) / ry, (-x1p - cxp) / rx, (-y1p - cyp) / ry)
    if swf == 0 and dth > 0:
        dth -= 2 * math.pi
    elif swf == 1 and dth < 0:
        dth += 2 * math.pi

    nseg = max(1, int(math.ceil(abs(dth) / (math.pi / 2))))
    out = []
    for k in range(nseg):
        a0 = th1 + dth * k / nseg
        a1 = th1 + dth * (k + 1) / nseg
        da = a1 - a0
        alpha = 4 / 3 * math.tan(da / 4)

        def pt(a):
            px = rx * math.cos(a)
            py = ry * math.sin(a)
            return (cosp * px - sinp * py + cx, sinp * px + cosp * py + cy)

        def dpt(a):
            px = -rx * math.sin(a)
            py = ry * math.cos(a)
            return (cosp * px - sinp * py, sinp * px + cosp * py)

        p0, p1 = pt(a0), pt(a1)
        d0, d1 = dpt(a0), dpt(a1)
        out.append((p0[0] + alpha * d0[0], p0[1] + alpha * d0[1],
                    p1[0] - alpha * d1[0], p1[1] - alpha * d1[1], p1[0], p1[1]))
    return out


# ---------------------------------------------------------------- main parser

class Parser:
    def __init__(self, root, rect):
        self.root = root
        self.gradients = {}
        self.markers = {}
        self.filters = {}
        self.nodes = []
        self.count = 0
        # viewBox → slide-px mapping
        vb = root.get('viewBox')
        if vb:
            vx, vy, vw, vh = [float(v) for v in re.split(r'[\s,]+', vb.strip())]
        else:
            vx = vy = 0.0
            vw = float(re.sub('[^0-9.]', '', root.get('width') or '0') or 0)
            vh = float(re.sub('[^0-9.]', '', root.get('height') or '0') or 0)
        if not vw or not vh:
            raise Unconvertible('no viewBox/size')
        sx, sy = rect['w'] / vw, rect['h'] / vh
        # preserveAspectRatio "meet" (default): uniform scale, centered
        if (root.get('preserveAspectRatio') or 'xMidYMid meet') != 'none':
            s = min(sx, sy)
            ox = rect['x'] + (rect['w'] - vw * s) / 2 - vx * s
            oy = rect['y'] + (rect['h'] - vh * s) / 2 - vy * s
            self.base = (s, 0, 0, s, ox, oy)
        else:
            self.base = (sx, 0, 0, sy, rect['x'] - vx * sx, rect['y'] - vy * sy)

    # ---- styles

    def style_of(self, el, inherited):
        st = dict(inherited)
        decls = {}
        for k in ('fill', 'stroke', 'stroke-width', 'stroke-dasharray', 'stroke-linecap',
                  'font-size', 'font-weight', 'font-style', 'text-anchor', 'opacity',
                  'fill-opacity', 'stroke-opacity', 'filter', 'dominant-baseline',
                  'letter-spacing', 'font-family'):
            v = el.get(k)
            if v is not None:
                decls[k] = v
        for part in (el.get('style') or '').split(';'):
            if ':' in part:
                k, v = part.split(':', 1)
                decls[k.strip()] = v.strip()
        st.update(decls)
        return st

    def resolve_fill(self, val, opacity):
        if val is None:
            val = '#000000'
        val = val.strip()
        if val == 'none':
            return None
        m = re.match(r'url\(#([^)]+)\)', val)
        if m:
            g = self.gradients.get(m.group(1))
            if g is None:
                raise Unconvertible(f'unresolved paint url #{m.group(1)}')
            return g
        c, ca = _color_alpha(val)
        return {'kind': 'solid', 'color': c, 'alpha': ca * opacity}

    # ---- defs

    def collect_defs(self, el):
        for child in el.iter():
            tag = _strip(child.tag)
            if tag == 'linearGradient':
                self.gradients[child.get('id')] = self._gradient(child)
            elif tag == 'marker':
                self.markers[child.get('id')] = child
            elif tag == 'filter':
                fe = next((c for c in child if _strip(c.tag) == 'feDropShadow'), None)
                if fe is not None:
                    self.filters[child.get('id')] = {
                        'dx': float(fe.get('dx') or 0), 'dy': float(fe.get('dy') or 2),
                        'blur': float(fe.get('stdDeviation') or 3),
                        'color': _color(fe.get('flood-color') or '#000000'),
                        'alpha': float(fe.get('flood-opacity') or 0.3)}

    def _gradient(self, g):
        stops = []
        for s in g:
            if _strip(s.tag) != 'stop':
                continue
            off = s.get('offset') or '0'
            pos = float(off[:-1]) / 100 if off.endswith('%') else float(off)
            color = s.get('stop-color')
            alpha = float(s.get('stop-opacity') or 1)
            for part in (s.get('style') or '').split(';'):
                if ':' in part:
                    k, v = part.split(':', 1)
                    if k.strip() == 'stop-color':
                        color = v.strip()
                    if k.strip() == 'stop-opacity':
                        alpha = float(v.strip())
            c, ca = _color_alpha(color or '#000')
            stops.append((pos, c, alpha * ca))
        x1 = float((g.get('x1') or '0').rstrip('%'))
        y1 = float((g.get('y1') or '0').rstrip('%'))
        x2 = float((g.get('x2') or ('1' if not (g.get('x2') or '').endswith('%') else '100')).rstrip('%'))
        y2 = float((g.get('y2') or '0').rstrip('%'))
        gt = parse_transform(g.get('gradientTransform') or '')
        p1 = mat_apply(gt, x1, y1)
        p2 = mat_apply(gt, x2, y2)
        angle = math.degrees(math.atan2(p2[1] - p1[1], p2[0] - p1[0])) % 360
        return {'kind': 'grad', 'angle': angle, 'stops': stops}

    # ---- traversal

    def run(self):
        self.collect_defs(self.root)
        # element-count guard: charts explode into hundreds of nodes — not worth shapes
        n_paint = sum(1 for e in self.root.iter()
                      if _strip(e.tag) in ('rect', 'circle', 'ellipse', 'line', 'polyline',
                                           'polygon', 'path', 'text'))
        if n_paint > MAX_ELEMENTS:
            raise Unconvertible(f'{n_paint} paint elements (chart?)')
        for e in self.root.iter():
            if _strip(e.tag) in UNSUPPORTED:
                raise Unconvertible(_strip(e.tag))
        base_style = {'fill': '#000000', 'font-size': '16', 'font-weight': '400',
                      'text-anchor': 'start'}
        self.walk(self.root, self.base, base_style, in_defs=False)
        return self.nodes

    def walk(self, el, m, style, in_defs):
        tag = _strip(el.tag)
        if tag in ('defs', 'clipPath', 'marker', 'filter', 'linearGradient', 'title', 'desc', 'metadata', 'style'):
            return
        st = self.style_of(el, style)
        mm = mat_mul(m, parse_transform(el.get('transform') or ''))
        if tag in ('svg', 'g'):
            for c in el:
                self.walk(c, mm, st, in_defs)
            return
        emit = getattr(self, 'el_' + tag, None)
        if emit is None:
            raise Unconvertible(f'element <{tag}>')
        emit(el, mm, st)

    # ---- shared emit helpers

    def _paints(self, el, st, m):
        opacity = float(st.get('opacity') or 1)
        fill = self.resolve_fill(st.get('fill'), float(st.get('fill-opacity') or 1) * opacity)
        stroke = None
        sval = st.get('stroke')
        if sval and sval != 'none':
            sm = re.match(r'url\(#([^)]+)\)', sval)
            if sm:
                g = self.gradients.get(sm.group(1))
                if g is None:
                    raise Unconvertible(f'unresolved stroke url')
                # PPTX lines can't take gradients via python-pptx cleanly → mid-stop color
                scolor, salpha = g['stops'][len(g['stops']) // 2][1], 1.0
            else:
                scolor, salpha = _color_alpha(sval)
            stroke = {'color': scolor,
                      'alpha': salpha * float(st.get('stroke-opacity') or 1) * opacity,
                      'width': float(st.get('stroke-width') or 1) * mat_scale_avg(m),
                      'dash': bool(st.get('stroke-dasharray') and st.get('stroke-dasharray') != 'none'),
                      'cap': 'rnd' if st.get('stroke-linecap') == 'round' else 'flat'}
        shadow = None
        fv = st.get('filter')
        if fv:
            fm = re.match(r'url\(#([^)]+)\)', fv)
            if fm and fm.group(1) in self.filters:
                shadow = self.filters[fm.group(1)]
        return fill, stroke, shadow

    def _emit_free(self, subpaths, m, fill, stroke, shadow):
        # transform all points into slide px
        out = []
        xs, ys = [], []

        def tp(x, y):
            px_, py_ = mat_apply(m, x, y)
            xs.append(px_); ys.append(py_)
            return (px_, py_)

        for sp in subpaths:
            segs2 = []
            s0 = tp(*sp['start'])
            for seg in sp['segs']:
                if seg[0] == 'l':
                    segs2.append(('l',) + tp(seg[1], seg[2]))
                else:
                    segs2.append(('c',) + tp(seg[1], seg[2]) + tp(seg[3], seg[4]) + tp(seg[5], seg[6]))
            out.append({'start': s0, 'closed': sp['closed'], 'segs': segs2})
        if not xs:
            return
        pad = (stroke['width'] / 2 if stroke else 0) + 0.5
        bx, by = min(xs) - pad, min(ys) - pad
        bw = max(xs) - bx + pad
        bh = max(ys) - by + pad
        self.nodes.append({'t': 'free', 'subpaths': out,
                           'bbox': (bx, by, max(bw, 0.5), max(bh, 0.5)),
                           'fill': fill, 'stroke': stroke, 'shadow': shadow})

    def _marker_hits(self, el, st, endpoints):
        """Instantiate marker-start/end content as freeforms at path endpoints."""
        for attr, (pt, ang, is_start) in endpoints.items():
            mv = st.get(attr) or el.get(attr)
            if not mv:
                continue
            mm_ = re.match(r'url\(#([^)]+)\)', mv)
            if not mm_ or mm_.group(1) not in self.markers:
                continue
            mk = self.markers[mm_.group(1)]
            orient = mk.get('orient') or '0'
            a = ang + (180 if (is_start and orient == 'auto-start-reverse') else 0)
            if orient not in ('auto', 'auto-start-reverse'):
                a = float(orient)
            vb = mk.get('viewBox')
            if vb:
                vx, vy, vw, vh = [float(v) for v in re.split(r'[\s,]+', vb.strip())]
            else:
                vx = vy = 0.0
                vw = float(mk.get('markerWidth') or 3)
                vh = float(mk.get('markerHeight') or 3)
            mw = float(mk.get('markerWidth') or 3)
            mh = float(mk.get('markerHeight') or 3)
            refx = float(mk.get('refX') or 0)
            refy = float(mk.get('refY') or 0)
            scale = 1.0
            if (mk.get('markerUnits') or 'strokeWidth') == 'strokeWidth':
                scale = float(st.get('stroke-width') or 1)
            rad = math.radians(a)
            rot = (math.cos(rad), math.sin(rad), -math.sin(rad), math.cos(rad), 0, 0)
            mmat = mat_mul((1, 0, 0, 1, pt[0], pt[1]), rot)
            mmat = mat_mul(mmat, (scale * mw / vw, 0, 0, scale * mh / vh, 0, 0))
            mmat = mat_mul(mmat, (1, 0, 0, 1, -refx, -refy))
            for c in mk:
                ctag = _strip(c.tag)
                cst = self.style_of(c, {'fill': '#000000'})
                fill = self.resolve_fill(cst.get('fill'), 1.0)
                if ctag == 'path':
                    self._emit_free(parse_path(c.get('d') or ''), mmat, fill, None, None)
                elif ctag == 'polygon':
                    pts = _points(c.get('points'))
                    sp = {'start': pts[0], 'closed': True,
                          'segs': [('l',) + p for p in pts[1:]]}
                    self._emit_free([sp], mmat, fill, None, None)

    # ---- element emitters (slide-px, m already includes viewBox map)

    def el_rect(self, el, m, st):
        fill, stroke, shadow = self._paints(el, st, m)
        x, y = float(el.get('x') or 0), float(el.get('y') or 0)
        w, h = float(el.get('width') or 0), float(el.get('height') or 0)
        rx = float(el.get('rx') or el.get('ry') or 0)
        if mat_is_rotated(m):
            sp = {'start': (x, y), 'closed': True,
                  'segs': [('l', x + w, y), ('l', x + w, y + h), ('l', x, y + h)]}
            self._emit_free([sp], m, fill, stroke, shadow)
            return
        p0 = mat_apply(m, x, y)
        p1 = mat_apply(m, x + w, y + h)
        self.nodes.append({'t': 'rect', 'x': p0[0], 'y': p0[1],
                           'w': p1[0] - p0[0], 'h': p1[1] - p0[1],
                           'rx': rx * mat_scale_avg(m),
                           'fill': fill, 'stroke': stroke, 'shadow': shadow})

    def el_circle(self, el, m, st):
        fill, stroke, shadow = self._paints(el, st, m)
        cx, cy = float(el.get('cx') or 0), float(el.get('cy') or 0)
        r = float(el.get('r') or 0)
        p0 = mat_apply(m, cx - r, cy - r)
        p1 = mat_apply(m, cx + r, cy + r)
        self.nodes.append({'t': 'ellipse', 'x': p0[0], 'y': p0[1],
                           'w': p1[0] - p0[0], 'h': p1[1] - p0[1],
                           'fill': fill, 'stroke': stroke, 'shadow': shadow})

    def el_ellipse(self, el, m, st):
        fill, stroke, shadow = self._paints(el, st, m)
        cx, cy = float(el.get('cx') or 0), float(el.get('cy') or 0)
        rx, ry = float(el.get('rx') or 0), float(el.get('ry') or 0)
        p0 = mat_apply(m, cx - rx, cy - ry)
        p1 = mat_apply(m, cx + rx, cy + ry)
        self.nodes.append({'t': 'ellipse', 'x': p0[0], 'y': p0[1],
                           'w': p1[0] - p0[0], 'h': p1[1] - p0[1],
                           'fill': fill, 'stroke': stroke, 'shadow': shadow})

    def el_line(self, el, m, st):
        _, stroke, shadow = self._paints(el, st, m)
        x1, y1 = float(el.get('x1') or 0), float(el.get('y1') or 0)
        x2, y2 = float(el.get('x2') or 0), float(el.get('y2') or 0)
        sp = {'start': (x1, y1), 'closed': False, 'segs': [('l', x2, y2)]}
        self._emit_free([sp], m, None, stroke, shadow)
        ang = math.degrees(math.atan2(*(lambda p, q: (q[1] - p[1], q[0] - p[0]))(
            mat_apply(m, x1, y1), mat_apply(m, x2, y2))))
        self._marker_hits(el, st, {
            'marker-end': (mat_apply(m, x2, y2), ang, False),
            'marker-start': (mat_apply(m, x1, y1), ang, True)})

    def el_polyline(self, el, m, st, closed=False):
        fill, stroke, shadow = self._paints(el, st, m)
        pts = _points(el.get('points'))
        if len(pts) < 2:
            return
        sp = {'start': pts[0], 'closed': closed,
              'segs': [('l',) + p for p in pts[1:]]}
        self._emit_free([sp], m, fill if closed else None, stroke, shadow)
        if not closed:
            p_end = mat_apply(m, *pts[-1])
            p_prev = mat_apply(m, *pts[-2])
            ang = math.degrees(math.atan2(p_end[1] - p_prev[1], p_end[0] - p_prev[0]))
            self._marker_hits(el, st, {'marker-end': (p_end, ang, False)})

    def el_polygon(self, el, m, st):
        self.el_polyline(el, m, st, closed=True)

    def el_path(self, el, m, st):
        fill, stroke, shadow = self._paints(el, st, m)
        subpaths = parse_path(el.get('d') or '')
        if not subpaths:
            return
        self._emit_free(subpaths, m, fill, stroke, shadow)
        # endpoint + tangent for markers
        last = subpaths[-1]
        segs = last['segs']
        if segs:
            end = segs[-1][-2:]
            if segs[-1][0] == 'c':
                t0 = segs[-1][3:5]
            else:
                t0 = segs[-2][-2:] if len(segs) > 1 else last['start']
            p_end = mat_apply(m, *end)
            p_t0 = mat_apply(m, *t0)
            ang_end = math.degrees(math.atan2(p_end[1] - p_t0[1], p_end[0] - p_t0[0]))
            first = subpaths[0]
            fs = first['segs'][0]
            f_to = fs[1:3]
            p_s = mat_apply(m, *first['start'])
            p_f = mat_apply(m, *f_to)
            ang_start = math.degrees(math.atan2(p_s[1] - p_f[1], p_s[0] - p_f[0]))
            self._marker_hits(el, st, {
                'marker-end': (p_end, ang_end, False),
                'marker-start': (p_s, ang_start, True)})

    def el_text(self, el, m, st):
        size = float(re.sub('[^0-9.]', '', st.get('font-size') or '16') or 16) * mat_scale_avg(m)
        weight = st.get('font-weight') or '400'
        weight = {'bold': 700, 'normal': 400}.get(weight, int(re.sub('[^0-9]', '', weight) or 400))
        color_v = st.get('fill') or '#000'
        if color_v.startswith('url('):
            g = self.resolve_fill(color_v, 1.0)
            color = g['stops'][len(g['stops']) // 2][1]
            grad = g
        else:
            color = _color(color_v)
            grad = None
        anchor = st.get('text-anchor') or 'start'
        baseline = st.get('dominant-baseline') or ''
        x = float(el.get('x') or 0)
        y = float(el.get('y') or 0)
        parts = []
        if (el.text or '').strip():
            parts.append(((x, y), (el.text or '').strip()))
        for tsp in el:
            if _strip(tsp.tag) != 'tspan':
                continue
            tx = float(tsp.get('x')) if tsp.get('x') is not None else x
            ty = float(tsp.get('y')) if tsp.get('y') is not None else y
            tx += float(tsp.get('dx') or 0)
            ty += float(tsp.get('dy') or 0)
            if (tsp.text or '').strip():
                parts.append(((tx, ty), (tsp.text or '').strip()))
            x, y = tx, ty
        rot = mat_rotation_deg(m) if mat_is_rotated(m) else 0.0
        for (px_, py_), text in parts:
            p = mat_apply(m, px_, py_)
            self.nodes.append({'t': 'text', 'x': p[0], 'y': p[1], 'size': size,
                               'weight': weight, 'color': color, 'grad': grad,
                               'anchor': anchor, 'baseline': baseline,
                               'rot': rot, 'text': text})


def _points(s):
    v = [float(t) for t in re.split(r'[\s,]+', (s or '').strip()) if t]
    return list(zip(v[0::2], v[1::2]))


_NAMED = {'black': '#000000', 'white': '#FFFFFF', 'none': None, 'red': '#FF0000',
          'green': '#008000', 'blue': '#0000FF', 'gray': '#808080', 'grey': '#808080'}


def _color(v):
    return _color_alpha(v)[0]


def _color_alpha(v):
    """→ ('#RRGGBB', alpha). rgba()'s 4th channel MUST survive — dropping it renders
    the design system's translucent white badges/number circles as solid white, which
    then hides the white glyphs and numerals drawn on top of them."""
    v = (v or '').strip()
    if v.startswith('#'):
        if len(v) == 4:
            return ('#' + v[1] * 2 + v[2] * 2 + v[3] * 2).upper(), 1.0
        if len(v) == 9:   # #RRGGBBAA
            return v[:7].upper(), int(v[7:9], 16) / 255.0
        return v.upper(), 1.0
    m = re.match(r'rgba?\(([\d.]+)[,\s]+([\d.]+)[,\s]+([\d.]+)(?:[,\s/]+([\d.]+%?))?\s*\)', v)
    if m:
        hexv = '#%02X%02X%02X' % tuple(int(round(float(g))) for g in m.groups()[:3])
        a = m.group(4)
        if a is None:
            alpha = 1.0
        elif a.endswith('%'):
            alpha = float(a[:-1]) / 100.0
        else:
            alpha = float(a)
        return hexv, alpha
    if v.lower() in _NAMED and _NAMED[v.lower()]:
        return _NAMED[v.lower()], 1.0
    return '#000000', 1.0


def convert(svg_path, rect):
    """svg file + placement rect {'x','y','w','h'} (slide px) → list of model nodes."""
    try:
        root = ET.parse(svg_path).getroot()
    except ET.ParseError as e:
        raise Unconvertible(f'XML parse: {e}')
    return Parser(root, rect).run()


# ---------------------------------------------------------------- re-render (verify)

def model_to_svg(nodes, rect):
    """Re-render the model back to SVG — what the verify diff screenshots."""
    defs, body = [], []
    gid = [0]

    def fill_attr(fill, el_id):
        if fill is None:
            return 'fill="none"'
        if fill['kind'] == 'solid':
            a = f' fill-opacity="{fill["alpha"]}"' if fill.get('alpha', 1) < 1 else ''
            return f'fill="{fill["color"]}"{a}'
        gid[0] += 1
        name = f'vg{gid[0]}'
        ang = math.radians(fill['angle'])
        x2, y2 = math.cos(ang), math.sin(ang)
        x1 = y1 = 0.0
        if x2 < 0:
            x1, x2 = -x2, 0.0
        if y2 < 0:
            y1, y2 = -y2, 0.0
        stops = ''.join(
            f'<stop offset="{p * 100:.0f}%" stop-color="{c}" stop-opacity="{a}"/>'
            for p, c, a in fill['stops'])
        defs.append(f'<linearGradient id="{name}" x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}">{stops}</linearGradient>')
        return f'fill="url(#{name})"'

    def stroke_attr(sk):
        if not sk:
            return 'stroke="none"'
        dash = ' stroke-dasharray="6 5"' if sk['dash'] else ''
        cap = ' stroke-linecap="round"' if sk['cap'] == 'rnd' else ''
        op = f' stroke-opacity="{sk["alpha"]}"' if sk.get('alpha', 1) < 1 else ''
        return f'stroke="{sk["color"]}" stroke-width="{sk["width"]}"{dash}{cap}{op}'

    for n in nodes:
        if n['t'] == 'rect':
            body.append(f'<rect x="{n["x"]}" y="{n["y"]}" width="{n["w"]}" height="{n["h"]}" '
                        f'rx="{n.get("rx") or 0}" {fill_attr(n["fill"], id(n))} {stroke_attr(n["stroke"])}/>')
        elif n['t'] == 'ellipse':
            body.append(f'<ellipse cx="{n["x"] + n["w"] / 2}" cy="{n["y"] + n["h"] / 2}" '
                        f'rx="{n["w"] / 2}" ry="{n["h"] / 2}" {fill_attr(n["fill"], id(n))} {stroke_attr(n["stroke"])}/>')
        elif n['t'] == 'free':
            d = []
            for sp in n['subpaths']:
                d.append(f'M {sp["start"][0]} {sp["start"][1]}')
                for seg in sp['segs']:
                    if seg[0] == 'l':
                        d.append(f'L {seg[1]} {seg[2]}')
                    else:
                        d.append(f'C {seg[1]} {seg[2]} {seg[3]} {seg[4]} {seg[5]} {seg[6]}')
                if sp['closed']:
                    d.append('Z')
            body.append(f'<path d="{" ".join(d)}" {fill_attr(n["fill"], id(n))} {stroke_attr(n["stroke"])}/>')
        elif n['t'] == 'text':
            anchor = n['anchor']
            rot = f' transform="rotate({n["rot"]} {n["x"]} {n["y"]})"' if n.get('rot') else ''
            body.append(f'<text x="{n["x"]}" y="{n["y"]}" font-size="{n["size"]}" '
                        f'font-family="{_TEXT_FONT}" font-weight="{n["weight"]}" fill="{n["color"]}" '
                        f'text-anchor="{anchor}"{rot}>{_xml_esc(n["text"])}</text>')
    w = rect['x'] + rect['w'] + 20
    h = rect['y'] + rect['h'] + 20
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
            f'viewBox="0 0 {w} {h}"><defs>{"".join(defs)}</defs>{"".join(body)}</svg>')


def _xml_esc(s):
    return s.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


# ---------------------------------------------------------------- CLI

def _verify(svg_path):
    import os
    import tempfile
    from playwright.sync_api import sync_playwright
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from ir_preview import diff_images

    root = ET.parse(svg_path).getroot()
    w = float(re.sub('[^0-9.]', '', root.get('width') or '400') or 400)
    h = float(re.sub('[^0-9.]', '', root.get('height') or '300') or 300)
    rect = {'x': 0, 'y': 0, 'w': w, 'h': h}
    nodes = convert(svg_path, rect)
    out_dir = tempfile.mkdtemp(prefix='svg2shapes-')
    model_svg = os.path.join(out_dir, 'model.svg')
    open(model_svg, 'w').write(model_to_svg(nodes, rect))

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={'width': int(w) + 20, 'height': int(h) + 20})
        shots = {}
        for name, path in (('source', svg_path), ('model', model_svg)):
            page.goto('file://' + os.path.abspath(path))
            page.wait_for_timeout(200)
            png = os.path.join(out_dir, f'{name}.png')
            page.screenshot(path=png)
            shots[name] = png
        browser.close()
    mae, mae_c = diff_images(shots['source'], shots['model'],
                             os.path.join(out_dir, 'heatmap.png'))
    kinds = {}
    for n in nodes:
        kinds[n['t']] = kinds.get(n['t'], 0) + 1
    return mae_c, kinds, out_dir


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('svg')
    ap.add_argument('--verify', action='store_true')
    ap.add_argument('--dump', action='store_true')
    args = ap.parse_args()
    if args.verify:
        try:
            mae_c, kinds, out_dir = _verify(args.svg)
        except Unconvertible as e:
            print(f'UNCONVERTIBLE  {args.svg}: {e}')
            sys.exit(2)
        flag = 'PASS' if mae_c < 60 else 'FAIL'
        print(f'{flag}  {args.svg}: content-MAE {mae_c:.1f}  nodes={kinds}  artifacts={out_dir}')
        sys.exit(0 if mae_c < 60 else 1)
    if args.dump:
        root = ET.parse(args.svg).getroot()
        w = float(re.sub('[^0-9.]', '', root.get('width') or '400') or 400)
        h = float(re.sub('[^0-9.]', '', root.get('height') or '300') or 300)
        print(json.dumps(convert(args.svg, {'x': 0, 'y': 0, 'w': w, 'h': h}), indent=1))


if __name__ == '__main__':
    main()
