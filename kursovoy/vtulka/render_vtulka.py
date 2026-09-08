# -*- coding: utf-8 -*-
"""3D-виды детали «Втулка» КИКГ.010114.002 и её заготовки.

Геометрия по чертежу и пояснительной записке:
    буртик Ø55 x 5 (7...12 от левого торца), цилиндры Ø40, общая длина 38,
    сквозное отверстие Ø30H9, все фаски 2x45°,
    4 паза 6x3 в буртике (по чертежу, вид справа).
Заготовка: пруток Ø58 x 43, латунь Л62 ГОСТ 15527-70.

Запуск:  python render_vtulka.py [папка]
"""

from __future__ import annotations

import os
import sys

import numpy as np
from PIL import Image

from csg import Cone, Cyl, Piece, Plane, Solid, slab, _norm

# --- размеры детали, мм ------------------------------------------------------
D_COLLAR, W_COLLAR, A_COLLAR = 55.0, 5.0, 7.0     # буртик и его положение
D_BODY, L_TOTAL, D_BORE = 40.0, 38.0, 30.0
CH = 2.0                                          # фаска 2x45°
SLOT_W, SLOT_DEPTH, SLOT_N = 6.0, 3.0, 4          # пазы в буртике

D_BAR, L_BAR = 58.0, 43.0                         # заготовка — пруток

BRASS = np.array([0.72, 0.60, 0.31])              # латунь Л62
BAR_COLOR = np.array([0.66, 0.57, 0.36])
CUT_COLOR = np.array([0.86, 0.76, 0.46])
BG_TOP = np.array([0.95, 0.96, 0.98])
BG_BOTTOM = np.array([0.74, 0.79, 0.86])
EDGE_COLOR = np.array([0.09, 0.12, 0.16])


def quarter_cut():
    """Четверть выреза: удаляется сектор x > 0, y < 0."""
    p = Piece(Plane((-1, 0, 0), 0.0), Plane((0, 1, 0), 0.0))
    p.is_cut = True
    return p


def vtulka(with_slots=True, cut=False):
    r_b, r_c, r_o = D_BODY / 2, D_COLLAR / 2, D_BORE / 2
    z1, z2 = A_COLLAR, A_COLLAR + W_COLLAR

    adds = [
        # левый цилиндр Ø40 с фаской на торце
        Piece(Cyl(0, 0, r_b), slab(2, 0.0, z1), Cone(1, r_b - CH)),
        # буртик Ø55 с фасками с обеих сторон
        Piece(Cyl(0, 0, r_c), slab(2, z1, z2),
              Cone(1, r_c - CH - z1), Cone(-1, r_c - CH + z2)),
        # правый цилиндр Ø40 с фаской на торце
        Piece(Cyl(0, 0, r_b), slab(2, z2, L_TOTAL), Cone(-1, r_b - CH + L_TOTAL)),
    ]
    subs = [
        Piece(Cyl(0, 0, r_o)),                       # отверстие Ø30 насквозь
        Piece(Cone(-1, r_o + CH)),                   # фаска отверстия слева
        Piece(Cone(1, r_o + CH - L_TOTAL)),          # фаска отверстия справа
    ]
    if with_slots:
        for i in range(SLOT_N):
            ang = np.radians(i * 360.0 / SLOT_N)
            u = np.array([np.cos(ang), np.sin(ang), 0.0])
            v = np.array([-np.sin(ang), np.cos(ang), 0.0])
            subs.append(Piece(Plane(-u, -(r_c - SLOT_DEPTH)),
                              Plane(v, SLOT_W / 2), Plane(-v, SLOT_W / 2),
                              slab(2, z1, z2)))
    if cut:
        subs.append(quarter_cut())
    return Solid(adds, subs)


def zagotovka(cut=False):
    adds = [Piece(Cyl(0, 0, D_BAR / 2), slab(2, -2.5, L_BAR - 2.5))]
    subs = [quarter_cut()] if cut else []
    return Solid(adds, subs)


# --- рендер ------------------------------------------------------------------
def shade(color, d, n, is_cut, basis):
    n = np.where((np.sum(n * d, axis=1) > 0)[:, None], -n, n)
    right, upv, dv = basis
    key = _norm(-dv + 0.42 * upv + 0.34 * right)
    fill = _norm(-dv - 0.70 * right - 0.10 * upv)
    rim = _norm(dv * 0.35 + upv * 0.85)
    lam = (0.58 * np.maximum(n @ key, 0) + 0.26 * np.maximum(n @ fill, 0)
           + 0.14 * np.maximum(n @ rim, 0))
    spec = np.power(np.maximum(n @ key, 0), 46.0) * 0.26
    base = np.where(is_cut[:, None], CUT_COLOR, color)
    return np.clip(base * (0.32 + lam)[:, None] + spec[:, None], 0, 1)


def render(path, solid, view_dir, up, half_height, target, color=BRASS,
           width=1200, height=900, ss=2):
    w, h = width * ss, height * ss
    dv = _norm(view_dir)
    right = _norm(np.cross(dv, _norm(up)))
    upv = np.cross(right, dv)
    target = np.asarray(target, dtype=np.float64)
    half_w = half_height * w / h

    xs = (np.arange(w) + 0.5) / w * 2 - 1
    ys = (np.arange(h) + 0.5) / h * 2 - 1
    depth = np.zeros((h, w)); normal = np.zeros((h, w, 3))
    color_buf = np.zeros((h, w, 3)); mask = np.zeros((h, w), dtype=bool)

    rows = max(1, int(1_200_000 / w))
    for y0 in range(0, h, rows):
        y1 = min(h, y0 + rows)
        gx, gy = np.meshgrid(xs, ys[y0:y1])
        o = (target + right * (gx.ravel() * half_w)[:, None]
             + upv * (-gy.ravel() * half_height)[:, None] - dv * 400.0)
        dirs = np.repeat(dv[None, :], o.shape[0], axis=0)
        t, n, hit, is_cut = solid.trace(o, dirs)
        rgb = shade(color, dirs, n, is_cut, (right, upv, dv))
        blk = (y1 - y0, w)
        depth[y0:y1] = np.where(hit, t, 1e6).reshape(blk)
        normal[y0:y1] = n.reshape(blk + (3,))
        mask[y0:y1] = hit.reshape(blk)
        color_buf[y0:y1] = np.where(hit[:, None], rgb, 0.0).reshape(blk + (3,))

    grad = np.linspace(0, 1, h)[:, None, None]
    img = np.where(mask[:, :, None], color_buf, BG_TOP * (1 - grad) + BG_BOTTOM * grad)

    sh = lambda a, dy, dx: np.roll(np.roll(a, dy, axis=0), dx, axis=1)
    jump = 4.0 * (2.0 * half_height / h)
    edge = np.zeros((h, w), dtype=bool)
    for dy, dx in ((0, 1), (1, 0), (1, 1), (1, -1)):
        m1, m2 = sh(mask, dy, dx), sh(mask, -dy, -dx)
        d1, d2 = sh(depth, dy, dx), sh(depth, -dy, -dx)
        edge |= mask ^ m1
        edge |= (mask & m1 & m2) & (np.abs(d1 + d2 - 2.0 * depth) > jump)
        edge |= (mask & m1) & (np.sum(normal * sh(normal, dy, dx), axis=2) < 0.70)
    edge[:1, :] = edge[-1:, :] = edge[:, :1] = edge[:, -1:] = False
    img = np.where(edge[:, :, None], EDGE_COLOR, img)

    small = img.reshape(height, ss, width, ss, 3).mean(axis=(1, 3))
    Image.fromarray((np.clip(small, 0, 1) * 255).astype(np.uint8)).save(path)
    return path


CENTER = (0.0, 0.0, 19.0)
ISO = dict(view_dir=(-0.95, 0.40, -0.62), up=(0, 0, 1), half_height=33.0, target=CENTER)
ISO_BACK = dict(view_dir=(-0.95, 0.40, 0.62), up=(0, 0, -1), half_height=33.0, target=CENTER)

VIEWS = [
    ("vtulka_iso.png", lambda: vtulka(), dict(ISO)),
    ("vtulka_iso_2.png", lambda: vtulka(), dict(ISO_BACK)),
    ("vtulka_cut.png", lambda: vtulka(cut=True), dict(ISO)),
    ("vtulka_front.png", lambda: vtulka(),
     dict(view_dir=(0, 1, 0), up=(0, 0, 1), half_height=21.0, target=(0, 0, 19),
          width=1300, height=1000)),
    ("vtulka_torec.png", lambda: vtulka(),
     dict(view_dir=(0, 0, 1), up=(0, 1, 0), half_height=31.0, target=CENTER,
          width=1100, height=1100)),
    ("zagotovka_iso.png", lambda: zagotovka(), dict(ISO, color=BAR_COLOR)),
    ("zagotovka_cut.png", lambda: zagotovka(cut=True), dict(ISO, color=BAR_COLOR)),
]


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    out = argv[0] if argv else os.path.join(os.path.dirname(os.path.abspath(__file__)), "img")
    os.makedirs(out, exist_ok=True)
    for name, build, params in VIEWS:
        render(os.path.join(out, name), build(), **params)
        print("готово:", name, flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
