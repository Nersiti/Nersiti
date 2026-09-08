# -*- coding: utf-8 -*-
"""Эскизы к техпроцессу детали «Втулка» КИКГ.010114.002.

Строятся: схема нумерации поверхностей, эскиз заготовки и операционные
эскизы на операции 005-020 по маршруту из пояснительной записки:

    005 Заготовительная (8Б72)  — отрезать пруток Ø58 в размер 43
    010 Токарная (16К20), устан. 1 — подрезать торец, точить Ø40,8, сверлить Ø15
    015 Токарная (16К20), устан. 2 — подрезать торец, точить Ø40,8 и Ø55,8,
                                     рассверлить Ø28, расточить Ø29,8
    020 Токарная (16К20) чистовая  — торцы в размер 38, Ø40 и Ø55 начисто,
                                     расточить Ø30H9, фаски 2x45°

Запуск:  python sketches.py [папка]
"""

from __future__ import annotations

import math
import os
import sys

import cairosvg

S = 7.4              # пикселей на миллиметр
X0 = 250.0           # левый торец
CY = 300.0           # ось детали
W, H = 830, 770

FONT = "DejaVu Sans, Arial, sans-serif"
C_MAIN = "#1b5fbe"
C_WORK = "#0d8f7a"
C_AXIS = "#e08a1e"
C_DIM = "#1b2430"
C_THIN = "#7b8796"


def X(a):
    return X0 + a * S


def Y(r):
    return CY - r * S


# --- примитивы ---------------------------------------------------------------
def poly(points, fill="url(#hatch)", stroke=C_MAIN, w=2.2):
    pts = " ".join(f"{X(a):.1f},{Y(r):.1f}" for a, r in points)
    return (f'<polygon points="{pts}" fill="{fill}" stroke="{stroke}" '
            f'stroke-width="{w}" stroke-linejoin="round"/>')


def mirror(points):
    return [(a, -r) for a, r in points]


def line(x1, y1, x2, y2, color=C_DIM, w=1.0, dash=None):
    d = f' stroke-dasharray="{dash}"' if dash else ""
    return (f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
            f'stroke="{color}" stroke-width="{w}"{d}/>')


def text(x, y, s, size=15, anchor="middle", color=C_DIM, rot=0, italic=False):
    tr = f' transform="rotate({rot} {x:.1f} {y:.1f})"' if rot else ""
    it = ' font-style="italic"' if italic else ""
    return (f'<text x="{x:.1f}" y="{y:.1f}" font-family="{FONT}" font-size="{size}" '
            f'text-anchor="{anchor}" fill="{color}"{it}{tr}>{s}</text>')


def arrow(x, y, dx, dy, color=C_DIM, size=9):
    ln = math.hypot(dx, dy)
    ux, uy = dx / ln, dy / ln
    px, py = -uy, ux
    return (f'<polygon points="{x:.1f},{y:.1f} '
            f'{x - ux * size + px * size * 0.28:.1f},{y - uy * size + py * size * 0.28:.1f} '
            f'{x - ux * size - px * size * 0.28:.1f},{y - uy * size - py * size * 0.28:.1f}" '
            f'fill="{color}"/>')


def mark(x, y, num):
    return (f'<circle cx="{x:.1f}" cy="{y:.1f}" r="11" fill="#fff" stroke="{C_DIM}" '
            f'stroke-width="1.3"/>' + text(x, y + 5, str(num), size=14))


def dim_d(x, r, label, num=None, a_ref=None, inner=False):
    """Диаметральный размер (вертикальная размерная линия)."""
    y1, y2 = Y(r), Y(-r)
    out = []
    if a_ref is not None:
        for y in (y1, y2):
            out.append(line(X(a_ref), y, x + (12 if x > X(a_ref) else -12), y, C_THIN, 0.9))
    out += [line(x, y1 - 16, x, y2 + 16), arrow(x, y1, 0, -1), arrow(x, y2, 0, 1),
            text(x + (16 if inner else -8), (y1 + y2) / 2, label, size=15, rot=-90)]
    if num is not None:
        out.append(mark(x, (y2 + 30) if inner else (y1 - 34), num))
    return "".join(out)


def dim_l(y, a1, a2, label, num=None, r_ref=None):
    """Линейный размер вдоль оси."""
    x1, x2 = X(a1), X(a2)
    out = []
    if r_ref is not None:
        for x in (x1, x2):
            out.append(line(x, Y(-r_ref), x, y + 12, C_THIN, 0.9))
    out += [line(x1 - 14, y, x2 + 14, y), arrow(x1, y, -1, 0), arrow(x2, y, 1, 0),
            text((x1 + x2) / 2, y - 9, label, size=15)]
    if num is not None:
        out.append(mark(x2 + 38, y, num))
    return "".join(out)


def base(x, y, up=True):
    """Опора (база) по ГОСТ 3.1107-81."""
    s, d = 13, (-1 if up else 1)
    return (f'<polygon points="{x:.1f},{y:.1f} {x - s * 0.6:.1f},{y + d * s:.1f} '
            f'{x + s * 0.6:.1f},{y + d * s:.1f}" fill="none" stroke="{C_MAIN}" '
            f'stroke-width="2"/>')


def clamp(x, y, dx, dy):
    ln = math.hypot(dx, dy)
    ux, uy = dx / ln, dy / ln
    return (line(x - ux * 32, y - uy * 32, x - ux * 9, y - uy * 9, C_MAIN, 2)
            + arrow(x, y, dx, dy, C_MAIN, 11))


def work(a1, r1, a2, r2):
    """Обрабатываемая на операции поверхность."""
    return (f'<line x1="{X(a1):.1f}" y1="{Y(r1):.1f}" x2="{X(a2):.1f}" y2="{Y(r2):.1f}" '
            f'stroke="{C_WORK}" stroke-width="5" stroke-linecap="round"/>')


def work_both(a1, r1, a2, r2):
    return work(a1, r1, a2, r2) + work(a1, -r1, a2, -r2)


def leader(a, r, x2, y2, num):
    """Выноска с номером поверхности."""
    return (line(X(a), Y(r), x2, y2, C_DIM, 1.0) + mark(x2, y2, num))


def ra(x, y, value):
    return (f'<path d="M {x} {y} l 9 16 l 16 -30" fill="none" stroke="{C_DIM}" '
            f'stroke-width="1.6"/>' + line(x + 25, y - 14, x + 92, y - 14, C_DIM, 1.6)
            + text(x + 58, y - 20, f"Ra {value}", size=17, italic=True))


def svg(body, caption, ra_value="6,3", a_axis=(-6, 50)):
    axis = line(X(a_axis[0]), CY, X(a_axis[1]), CY, C_AXIS, 1.2, "22 5 4 5")
    ra_sign = ra(W - 150, 46, ra_value) if ra_value else ""
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">
<defs><pattern id="hatch" width="9" height="9" patternTransform="rotate(45)"
  patternUnits="userSpaceOnUse">
  <line x1="0" y1="0" x2="0" y2="9" stroke="{C_MAIN}" stroke-width="0.9"/></pattern></defs>
<rect width="{W}" height="{H}" fill="#ffffff"/>
{axis}
{body}
{ra_sign}
{text(W / 2, H - 22, caption, size=18)}
</svg>'''


# --- профили (верхняя половина сечения) --------------------------------------
# готовая деталь: буртик Ø55 x5 на 7...12 от левого торца, фаски 2x45°
DETAL = [(0, 18), (2, 20), (7, 20), (7, 25.5), (9, 27.5), (10, 27.5), (12, 25.5),
         (12, 20), (36, 20), (38, 18), (38, 17), (36, 15), (2, 15), (0, 17)]
# после 015 (черновая, длина 40, Ø40,8 / Ø55,8, отверстие Ø29,8)
OP015 = [(0, 20.4), (8, 20.4), (8, 27.9), (13, 27.9), (13, 20.4), (40, 20.4),
         (40, 14.9), (0, 14.9)]
# после 010 (длина 41,5: Ø58 не обработан слева, Ø40,8 справа, отверстие Ø15)
OP010 = [(0, 29), (23.5, 29), (23.5, 20.4), (41.5, 20.4), (41.5, 7.5), (0, 7.5)]
# заготовка — пруток Ø58 x 43
ZAGOT = [(0, 29), (43, 29), (43, 0), (0, 0)]


def both(profile):
    return poly(profile) + poly(mirror(profile))


# --- эскизы ------------------------------------------------------------------
def sketch_poverhnosti():
    body = [both(DETAL)]
    # дно паза 6x3 в буртике — штриховой линией (паз не попадает в плоскость разреза)
    for sign in (1, -1):
        body.append(line(X(7), Y(sign * 24.5), X(12), Y(sign * 24.5), C_MAIN, 1.6, "7 4"))
    body += [
        leader(0, 16.0, X0 - 120, Y(30), 1),
        leader(4, 20.0, X0 - 60, Y(34), 2),
        leader(9.5, 27.5, X(9) + 10, Y(37), 3),
        leader(10.5, 24.5, X(26), Y(36), 4),
        leader(26, 20.0, X(40), Y(30), 5),
        leader(38, 17.5, X(46), Y(12), 6),
        leader(20, -15.0, X(27), Y(-31), 7),
        leader(37, -16.0, X(45), Y(-26), 8),
    ]
    body += [text(X(19), Y(-40), "1 — левый торец; 2, 5 — Ø40; 3 — буртик Ø55; "
                  "4 — паз 6×3 (4 шт.);", size=15),
             text(X(19), Y(-44.5), "6 — правый торец; 7 — отверстие Ø30H9; "
                  "8 — фаски 2×45°", size=15)]
    return svg("".join(body), "Рисунок 1 — Схема нумерации поверхностей детали «Втулка»",
               ra_value=None)


def sketch_005():
    body = [both(ZAGOT)]
    body += [work_both(43, 0, 43, 29)]
    body += [clamp(X(10), Y(29), 0, 1), clamp(X(10), Y(-29), 0, -1),
             base(X(20), Y(29), up=True), base(X(20), Y(-29), up=False)]
    body += [dim_d(X0 - 90, 29, "&#216;58", None, a_ref=0),
             dim_l(Y(-29) + 66, 0, 43, "43", None, r_ref=29)]
    return svg("".join(body), "005 Заготовительная. Отрезать пруток Ø58 в размер 43 (8Б72)",
               "12,5")


def sketch_010():
    body = [both(OP010)]
    body += [work_both(41.5, 7.5, 41.5, 20.4),          # подрезанный торец
             work_both(23.5, 20.4, 41.5, 20.4),         # Ø40,8
             work_both(0, 7.5, 41.5, 7.5)]              # сверление Ø15
    body += [base(X(8), Y(29), up=True), base(X(8), Y(-29), up=False),
             clamp(X(14), Y(29), 0, 1), clamp(X(14), Y(-29), 0, -1)]
    body += [dim_d(X0 - 150, 20.4, "&#216;40,8", 1, a_ref=30),
             dim_d(X0 - 80, 7.5, "&#216;15", 3, a_ref=10),
             dim_l(Y(-29) + 66, 23.5, 41.5, "18", 2, r_ref=29),
             dim_l(Y(-29) + 122, 0, 41.5, "41,5", None, r_ref=29)]
    return svg("".join(body), "010 Токарная, установ 1 (16К20): торец, Ø40,8, сверление Ø15")


def sketch_015():
    body = [both(OP015)]
    body += [work_both(0, 14.9, 0, 20.4),               # подрезанный торец 2
             work_both(0, 20.4, 8, 20.4),               # левая ступень Ø40,8
             work_both(8, 27.9, 13, 27.9),              # буртик Ø55,8
             work_both(0, 14.9, 40, 14.9)]              # растачивание Ø29,8
    body += [base(X(32), Y(20.4), up=True), base(X(32), Y(-20.4), up=False),
             clamp(X(40), Y(10), -1, 0), clamp(X(40), Y(-10), -1, 0)]
    body += [dim_d(X0 - 150, 27.9, "&#216;55,8", 2, a_ref=8),
             dim_d(X0 - 80, 20.4, "&#216;40,8", 3, a_ref=8),
             dim_d(X(20), 14.9, "&#216;29,8", 4, inner=True),
             dim_l(Y(-29) + 66, 0, 13, "13", 1, r_ref=27.9),
             dim_l(Y(-29) + 122, 0, 40, "40", 5, r_ref=27.9)]
    return svg("".join(body),
               "015 Токарная, установ 2 (16К20): торец, Ø40,8 и Ø55,8, Ø28, расточка Ø29,8")


def sketch_020():
    body = [both(DETAL)]
    body += [work_both(0, 17, 0, 18), work_both(38, 17, 38, 18),      # торцы
             work_both(2, 20, 7, 20), work_both(12, 20, 36, 20),      # Ø40
             work_both(9, 27.5, 10, 27.5),                            # Ø55
             work_both(2, 15, 36, 15),                                # Ø30H9
             work(0, 18, 2, 20), work(0, -18, 2, -20),                # фаски
             work(36, 20, 38, 18), work(36, -20, 38, -18),
             work(0, 17, 2, 15), work(0, -17, 2, -15),
             work(36, 15, 38, 17), work(36, -15, 38, -17)]
    body += [base(X(30), Y(20), up=True), base(X(30), Y(-20), up=False),
             clamp(X(38), Y(18.5), -1, 0), clamp(X(38), Y(-18.5), -1, 0)]
    body += [dim_d(X0 - 150, 27.5, "&#216;55h14", 2, a_ref=9),
             dim_d(X0 - 80, 20, "&#216;40h14", 3, a_ref=2),
             dim_d(X(20), 15, "&#216;30H9 Ra1,6", 4, inner=True),
             dim_l(Y(-29) + 66, 0, 12, "12", 5, r_ref=27.5),
             dim_l(Y(-29) + 122, 0, 38, "38*", 1, r_ref=27.5),
             text(X(20), Y(34), "Фаски 2×45° по всем кромкам", size=15)]
    return svg("".join(body),
               "020 Токарная чистовая (16К20): торцы в размер 38, Ø40 и Ø55, Ø30H9, фаски",
               "1,6")


SKETCHES = [
    ("poverhnosti.png", sketch_poverhnosti),
    ("op_005_otreznaya.png", sketch_005),
    ("op_010_tokarnaya_1.png", sketch_010),
    ("op_015_tokarnaya_2.png", sketch_015),
    ("op_020_chistovaya.png", sketch_020),
]


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    out = argv[0] if argv else os.path.join(os.path.dirname(os.path.abspath(__file__)), "img")
    os.makedirs(out, exist_ok=True)
    for name, fn in SKETCHES:
        data = fn()
        open(os.path.join(out, name.replace(".png", ".svg")), "w", encoding="utf-8").write(data)
        cairosvg.svg2png(bytestring=data.encode("utf-8"),
                         write_to=os.path.join(out, name), scale=1.7)
        print("готово:", name, flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
