# -*- coding: utf-8 -*-
"""Рендер детали «Крышка» (СПТК 15.02.16.023) и её заготовки.

Геометрия взята с чертежа и сверена с массой 3,87 кг из пояснительной записки:
    фланец Ø175 x 18, поясок Ø90h8 x 26 (фаска 2x45°), отв. Ø52H7 насквозь,
    4 отв. Ø14 на окружности Ø140, общая длина 44 мм.
Заготовка (поковка): Ø177,8 x 47, поясок Ø92,7 x 26, отв. Ø50.

Изображение считается трассировкой лучей по CSG-модели, без триангуляции,
поэтому кромки и фаска получаются точными.

Запуск:  python render_krishka.py [папка]
"""

from __future__ import annotations

import os
import sys

import numpy as np
from PIL import Image

TOL = 1e-3
INF = 1e9

BASE_COLOR = np.array([0.60, 0.64, 0.70])
BLANK_COLOR = np.array([0.66, 0.60, 0.50])
CUT_COLOR = np.array([0.80, 0.72, 0.52])
BG_TOP = np.array([0.95, 0.96, 0.98])
BG_BOTTOM = np.array([0.74, 0.79, 0.86])
EDGE_COLOR = np.array([0.09, 0.12, 0.16])


class Part:
    """Тело вращения: фланец + поясок с фаской, минус отверстия."""

    def __init__(self, r_flange, h_flange, r_boss, h_boss, r_bore,
                 bolt_r=None, bolt_n=0, bolt_pcd=0.0, chamfer=0.0, color=BASE_COLOR):
        self.r_flange, self.r_boss, self.r_bore = r_flange, r_boss, r_bore
        self.z_boss = h_boss                     # поясок: 0 .. z_boss
        self.z_top = h_boss + h_flange           # фланец: z_boss .. z_top
        self.chamfer = chamfer                   # фаска 45° на торце пояска
        self.cone_b = r_boss - chamfer           # r <= z + cone_b
        self.color = color
        self.bolts = []
        if bolt_n:
            ang = np.radians(np.arange(bolt_n) * 360.0 / bolt_n)
            self.bolts = [(bolt_pcd / 2 * np.cos(a), bolt_pcd / 2 * np.sin(a), bolt_r)
                          for a in ang]
        self.subs = [(0.0, 0.0, r_bore)] + self.bolts

    # --- предикаты принадлежности -------------------------------------------
    def in_flange(self, p, strict):
        e = -TOL if strict else TOL
        r = np.hypot(p[:, 0], p[:, 1])
        return (r < self.r_flange + e) & (p[:, 2] > self.z_boss - e) & (p[:, 2] < self.z_top + e)

    def in_boss(self, p, strict):
        e = -TOL if strict else TOL
        r = np.hypot(p[:, 0], p[:, 1])
        ok = (r < self.r_boss + e) & (p[:, 2] > -e) & (p[:, 2] < self.z_boss + e)
        if self.chamfer > 0:
            ok &= r < p[:, 2] + self.cone_b + e
        return ok

    def in_body(self, p):
        return self.in_flange(p, False) | self.in_boss(p, False)

    def in_subs(self, p, skip=None, cut=None):
        acc = np.zeros(p.shape[0], dtype=bool)
        for i, (cx, cy, r) in enumerate(self.subs):
            if i != skip:
                acc |= np.hypot(p[:, 0] - cx, p[:, 1] - cy) < r - TOL
        if cut is not None and skip != "cut":
            acc |= cut.inside(p)
        return acc


class QuarterCut:
    """Четвертной вырез: удаляется область x > 0 и y < 0."""

    @staticmethod
    def inside(p):
        return (p[:, 0] > TOL) & (p[:, 1] < -TOL)

    @staticmethod
    def planes(o, d):
        """Плоскости выреза: (t, нормаль, лежит ли точка в вырезаемом секторе)."""
        res = []
        for axis, sign in ((0, 1.0), (1, -1.0)):
            dv = d[:, axis]
            flat = np.abs(dv) < 1e-12
            t = (0.0 - o[:, axis]) / np.where(flat, 1.0, dv)
            n = np.zeros((o.shape[0], 3))
            n[:, axis] = sign
            res.append((np.where(flat, INF, t), n))
        return res


def _cyl(o, d, cx, cy, radius, zmin, zmax):
    ox, oy, oz = o[:, 0] - cx, o[:, 1] - cy, o[:, 2]
    dx, dy, dz = d[:, 0], d[:, 1], d[:, 2]
    a = dx * dx + dy * dy
    b = 2.0 * (ox * dx + oy * dy)
    c = ox * ox + oy * oy - radius * radius
    par = a < 1e-12
    a_s = np.where(par, 1.0, a)
    disc = b * b - 4.0 * a_s * c
    sq = np.sqrt(np.maximum(disc, 0.0))
    tc0 = np.where(par, -INF, (-b - sq) / (2.0 * a_s))
    tc1 = np.where(par, INF, (-b + sq) / (2.0 * a_s))
    hit_c = np.where(par, c <= 0.0, disc > 0.0)

    flat = np.abs(dz) < 1e-12
    dz_s = np.where(flat, 1.0, dz)
    ta, tb = (zmin - oz) / dz_s, (zmax - oz) / dz_s
    ts0 = np.where(flat, -INF, np.minimum(ta, tb))
    ts1 = np.where(flat, INF, np.maximum(ta, tb))
    hit_s = np.where(flat, (oz >= zmin) & (oz <= zmax), True)

    t0, t1 = np.maximum(tc0, ts0), np.minimum(tc1, ts1)
    return t0, t1, tc0 >= ts0, tc1 <= ts1, hit_c & hit_s & (t0 < t1)


def _cone(o, d, b_off):
    """Пересечение с конусом r = z + b_off (фаска 45°)."""
    ox, oy, oz = o[:, 0], o[:, 1], o[:, 2] + b_off
    dx, dy, dz = d[:, 0], d[:, 1], d[:, 2]
    A = dx * dx + dy * dy - dz * dz
    B = 2.0 * (ox * dx + oy * dy - oz * dz)
    C = ox * ox + oy * oy - oz * oz
    lin = np.abs(A) < 1e-12
    A_s = np.where(lin, 1.0, A)
    disc = B * B - 4.0 * A_s * C
    sq = np.sqrt(np.maximum(disc, 0.0))
    t0 = np.where(lin, np.where(np.abs(B) < 1e-12, INF, -C / np.where(np.abs(B) < 1e-12, 1.0, B)),
                  (-B - sq) / (2.0 * A_s))
    t1 = np.where(lin, INF, (-B + sq) / (2.0 * A_s))
    ok = np.where(lin, np.abs(B) >= 1e-12, disc > 0.0)
    return t0, t1, ok


def _side_normal(p, cx, cy, radius):
    n = np.zeros_like(p)
    n[:, 0] = (p[:, 0] - cx) / radius
    n[:, 1] = (p[:, 1] - cy) / radius
    return n


def _cap_normal(d):
    n = np.zeros((d.shape[0], 3))
    n[:, 2] = np.where(d[:, 2] > 0, -1.0, 1.0)
    return n


def trace(part, o, d, cut):
    cand_t, cand_n, cand_cut = [], [], []

    def push(t, n, ok, is_cut=False):
        cand_t.append(np.where(ok, t, INF))
        cand_n.append(n)
        cand_cut.append(is_cut)

    P = lambda t: o + t[:, None] * d

    # фланец
    t0, t1, s0, s1, hit = _cyl(o, d, 0, 0, part.r_flange, part.z_boss, part.z_top)
    for t, side in ((t0, s0), (t1, s1)):
        p = P(t)
        n = np.where(side[:, None], _side_normal(p, 0, 0, part.r_flange), _cap_normal(d))
        push(t, n, hit & (t > TOL) & ~part.in_boss(p, True) & ~part.in_subs(p, cut=cut))

    # поясок
    t0, t1, s0, s1, hit = _cyl(o, d, 0, 0, part.r_boss, 0.0, part.z_boss)
    for t, side in ((t0, s0), (t1, s1)):
        p = P(t)
        n = np.where(side[:, None], _side_normal(p, 0, 0, part.r_boss), _cap_normal(d))
        ok = (hit & (t > TOL) & part.in_boss(p, False) & ~part.in_flange(p, True)
              & ~part.in_subs(p, cut=cut))
        push(t, n, ok)

    # фаска 2x45° (конус)
    if part.chamfer > 0:
        c0, c1, cok = _cone(o, d, part.cone_b)
        for t in (c0, c1):
            p = P(t)
            n = np.stack([p[:, 0], p[:, 1], -(p[:, 2] + part.cone_b)], axis=1)
            ln = np.linalg.norm(n, axis=1)
            n = n / np.where(ln[:, None] < 1e-9, 1.0, ln[:, None])
            ok = (cok & (t > TOL) & part.in_boss(p, False) & ~part.in_flange(p, True)
                  & ~part.in_subs(p, cut=cut))
            push(t, n, ok)

    # отверстия
    for i, (cx, cy, r) in enumerate(part.subs):
        t0, t1, _, _, hit = _cyl(o, d, cx, cy, r, -INF, INF)
        for t in (t0, t1):
            p = P(t)
            push(t, -_side_normal(p, cx, cy, r),
                 hit & (t > TOL) & part.in_body(p) & ~part.in_subs(p, skip=i, cut=cut))

    # плоскости четвертного выреза
    if cut is not None:
        for t, n in cut.planes(o, d):
            p = P(np.where(np.abs(t) < INF / 2, t, 0.0))
            ok = ((np.abs(t) < INF / 2) & (t > TOL) & part.in_body(p)
                  & cut.inside(p + n * 2 * TOL) & ~part.in_subs(p, skip="cut"))
            push(t, n, ok, is_cut=True)

    ts = np.stack(cand_t)
    best = np.argmin(ts, axis=0)
    t_best = np.take_along_axis(ts, best[None, :], axis=0)[0]
    n_best = np.take_along_axis(np.stack(cand_n), best[None, :, None], axis=0)[0]
    return t_best, n_best, t_best < INF / 2, np.array(cand_cut)[best]


def _norm(v):
    v = np.asarray(v, dtype=np.float64)
    return v / np.linalg.norm(v)


def shade(part, d, n, is_cut, basis):
    """Освещение задаётся относительно камеры — деталь одинаково читается
    с любого направления, как в окне 3D-вида."""
    n = np.where((np.sum(n * d, axis=1) > 0)[:, None], -n, n)
    right, upv, dv = basis
    key = _norm(-dv + 0.42 * upv + 0.34 * right)
    fill = _norm(-dv - 0.70 * right - 0.10 * upv)
    rim = _norm(dv * 0.35 + upv * 0.85)
    lam = (0.58 * np.maximum(n @ key, 0) + 0.26 * np.maximum(n @ fill, 0)
           + 0.14 * np.maximum(n @ rim, 0))
    ambient = 0.32
    spec = np.power(np.maximum(n @ key, 0), 46.0) * 0.26
    base = np.where(is_cut[:, None], CUT_COLOR, part.color)
    return np.clip(base * (ambient + lam)[:, None] + spec[:, None], 0, 1)


def render(path, part, view_dir, up, half_height, target, width=1400, height=1050,
           ss=2, cut=None):
    w, h = width * ss, height * ss
    dv = _norm(view_dir)
    right = _norm(np.cross(dv, _norm(up)))
    upv = np.cross(right, dv)
    target = np.asarray(target, dtype=np.float64)
    half_w = half_height * w / h

    xs = (np.arange(w) + 0.5) / w * 2 - 1
    ys = (np.arange(h) + 0.5) / h * 2 - 1
    depth = np.zeros((h, w)); normal = np.zeros((h, w, 3))
    color = np.zeros((h, w, 3)); mask = np.zeros((h, w), dtype=bool)

    rows = max(1, int(2_000_000 / w))
    for y0 in range(0, h, rows):
        y1 = min(h, y0 + rows)
        gx, gy = np.meshgrid(xs, ys[y0:y1])
        o = (target + right * (gx.ravel() * half_w)[:, None]
             + upv * (-gy.ravel() * half_height)[:, None] - dv * 900.0)
        dirs = np.repeat(dv[None, :], o.shape[0], axis=0)
        t, n, hit, is_cut = trace(part, o, dirs, cut)
        rgb = shade(part, dirs, n, is_cut, (right, upv, dv))
        blk = (y1 - y0, w)
        depth[y0:y1] = np.where(hit, t, 1e6).reshape(blk)
        normal[y0:y1] = n.reshape(blk + (3,))
        mask[y0:y1] = hit.reshape(blk)
        color[y0:y1] = np.where(hit[:, None], rgb, 0.0).reshape(blk + (3,))

    grad = np.linspace(0, 1, h)[:, None, None]
    img = np.where(mask[:, :, None], color, BG_TOP * (1 - grad) + BG_BOTTOM * grad)

    # рёбра: силуэт, излом поверхности и разрыв глубины.
    # Для разрыва берём вторую разность — она равна нулю на плоскости
    # под любым наклоном, поэтому наклонные грани не «зачерняются».
    sh = lambda a, dy, dx: np.roll(np.roll(a, dy, axis=0), dx, axis=1)
    mm_per_px = 2.0 * half_height / h
    jump = 4.0 * mm_per_px
    edge = np.zeros((h, w), dtype=bool)
    for dy, dx in ((0, 1), (1, 0), (1, 1), (1, -1)):
        m1, m2 = sh(mask, dy, dx), sh(mask, -dy, -dx)
        d1, d2 = sh(depth, dy, dx), sh(depth, -dy, -dx)
        edge |= mask ^ m1
        three = mask & m1 & m2
        edge |= three & (np.abs(d1 + d2 - 2.0 * depth) > jump)
        edge |= (mask & m1) & (np.sum(normal * sh(normal, dy, dx), axis=2) < 0.70)
    edge[:1, :] = edge[-1:, :] = edge[:, :1] = edge[:, -1:] = False
    img = np.where(edge[:, :, None], EDGE_COLOR, img)

    small = img.reshape(height, ss, width, ss, 3).mean(axis=(1, 3))
    Image.fromarray((np.clip(small, 0, 1) * 255).astype(np.uint8)).save(path)
    return path


KRISHKA = dict(r_flange=87.5, h_flange=18.0, r_boss=45.0, h_boss=26.0, r_bore=26.0,
               bolt_r=7.0, bolt_n=4, bolt_pcd=140.0, chamfer=2.0)
ZAGOTOVKA = dict(r_flange=88.9, h_flange=21.0, r_boss=46.35, h_boss=26.0, r_bore=25.0,
                 bolt_n=0, chamfer=0.0, color=BLANK_COLOR)

CENTER = (0.0, 0.0, 20.0)
# камера смотрит «между» плоскостями выреза — так разрез читается лучше всего
ISO = dict(view_dir=(-0.95, 0.40, -0.72), up=(0, 0, 1), half_height=104.0, target=CENTER)
ISO_BOSS = dict(view_dir=(-0.95, 0.40, 0.72), up=(0, 0, -1), half_height=104.0, target=CENTER)

VIEWS = [
    ("krishka_iso.png",       KRISHKA,   dict(ISO)),
    ("krishka_iso_poyasok.png", KRISHKA, dict(ISO_BOSS)),
    ("krishka_cut.png",       KRISHKA,   dict(ISO, cut=QuarterCut)),
    ("krishka_cut_poyasok.png", KRISHKA, dict(ISO_BOSS, cut=QuarterCut)),
    ("krishka_front.png",     KRISHKA,   dict(view_dir=(0, 1, 0), up=(0, 0, 1),
                                             half_height=62.0, target=(0, 0, 22))),
    ("krishka_top.png",       KRISHKA,   dict(view_dir=(0, 0, -1), up=(0, 1, 0),
                                             half_height=98.0, target=CENTER)),
    ("zagotovka_iso.png",     ZAGOTOVKA, dict(ISO)),
    ("zagotovka_cut.png",     ZAGOTOVKA, dict(ISO, cut=QuarterCut)),
]


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    out = argv[0] if argv else os.path.join(os.path.dirname(os.path.abspath(__file__)), "img")
    os.makedirs(out, exist_ok=True)
    for name, geom, params in VIEWS:
        render(os.path.join(out, name), Part(**geom), **params)
        print("готово:", name, flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
