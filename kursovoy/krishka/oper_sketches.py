# -*- coding: utf-8 -*-
"""Операционные эскизы к техпроцессу детали «Крышка».

Эскизы строятся как векторная графика (SVG) и растеризуются в PNG.
Размеры взяты из пояснительной записки (таблица припусков):

    длина  47 -> 44                 (черновое точение)
    Ø175   177,8 -> 175             (черновое точение)
    Ø90h8  92,7 -> 90,36 -> 90,06 -> 90   (черн./чист. точение, шлифовка)
    Ø52H7  49,7 -> 51,64 -> 51,94 -> 52   (черн./чист. растачивание, шлифовка)

Запуск:  python oper_sketches.py [папка]
"""

from __future__ import annotations

import os
import sys

import cairosvg

S = 3.2            # пикселей на миллиметр
X0 = 300.0         # левый торец детали
CY = 400.0         # ось детали
W, H = 690, 880

FONT = "DejaVu Sans, Arial, sans-serif"
C_MAIN = "#1b5fbe"      # основная линия (как в КОМПАСе)
C_WORK = "#0d8f7a"      # обрабатываемая на операции поверхность
C_AXIS = "#e08a1e"      # осевая
C_DIM = "#1b2430"       # размерные линии и текст


def X(a):
    return X0 + a * S


def Y(r):
    return CY - r * S


# --------------------------------------------------------------------------
# примитивы
# --------------------------------------------------------------------------
def profile(seq):
    """Верхняя половина сечения -> замкнутый контур (по парам (a, r))."""
    return " ".join(f"{X(a):.1f},{Y(r):.1f}" for a, r in seq)


def mirror(seq):
    return [(a, -r) for a, r in seq]


def hatched(seq):
    pts = profile(seq)
    return (f'<polygon points="{pts}" fill="url(#hatch)" stroke="{C_MAIN}" '
            f'stroke-width="2.2" stroke-linejoin="round"/>')


def line(x1, y1, x2, y2, color=C_DIM, w=1.0, dash=None):
    d = f' stroke-dasharray="{dash}"' if dash else ""
    return (f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
            f'stroke="{color}" stroke-width="{w}"{d}/>')


def text(x, y, s, size=15, anchor="middle", color=C_DIM, rot=0, italic=False):
    tr = f' transform="rotate({rot} {x:.1f} {y:.1f})"' if rot else ""
    it = ' font-style="italic"' if italic else ""
    return (f'<text x="{x:.1f}" y="{y:.1f}" font-family="{FONT}" font-size="{size}" '
            f'text-anchor="{anchor}" fill="{color}"{tr}{it}>{s}</text>')


def arrow(x, y, dx, dy, color=C_DIM, size=9):
    """Стрелка размерной линии: остриё в (x, y), направление (dx, dy)."""
    import math
    ln = math.hypot(dx, dy)
    ux, uy = dx / ln, dy / ln
    px, py = -uy, ux
    x1, y1 = x - ux * size + px * size * 0.28, y - uy * size + py * size * 0.28
    x2, y2 = x - ux * size - px * size * 0.28, y - uy * size - py * size * 0.28
    return (f'<polygon points="{x:.1f},{y:.1f} {x1:.1f},{y1:.1f} {x2:.1f},{y2:.1f}" '
            f'fill="{color}"/>')


def mark(x, y, num):
    """Номер размера, выдерживаемого на операции (кружок с цифрой)."""
    return (f'<circle cx="{x:.1f}" cy="{y:.1f}" r="11" fill="#ffffff" '
            f'stroke="{C_DIM}" stroke-width="1.3"/>'
            + text(x, y + 5, str(num), size=14))


def dim_diameter(x, r, label, num=None, a_ref=None, inner=False):
    """Размер диаметра: размерная линия с выносками и номером размера."""
    y1, y2 = Y(r), Y(-r)
    out = []
    if a_ref is not None:
        for y in (y1, y2):
            out.append(line(X(a_ref), y, x - 12 if x < X(a_ref) else x + 12, y,
                            "#7b8796", 0.9))
    out += [line(x, y1 - 16, x, y2 + 16, w=1.0), arrow(x, y1, 0, -1), arrow(x, y2, 0, 1)]
    out.append(text(x + (16 if inner else -8), (y1 + y2) / 2, label, size=16, rot=-90))
    if num is not None:
        out.append(mark(x, y1 - 34, num))
    return "".join(out)


def dim_local(x, r1, r2, label, num=None, a_ref=None):
    """Размер между двумя радиусами с одной стороны от оси (например, Ø отверстия)."""
    y1, y2 = Y(r1), Y(r2)
    out = []
    if a_ref is not None:
        for y in (y1, y2):
            out.append(line(X(a_ref), y, x - 12, y, "#7b8796", 0.9))
    out += [line(x, y1 + 20, x, y2 - 20, w=1.0), arrow(x, y1, 0, 1), arrow(x, y2, 0, -1),
            text(x - 8, (y1 + y2) / 2, label, size=16, rot=-90)]
    if num is not None:
        out.append(mark(x, y2 - 38, num))
    return "".join(out)


def dim_length(y, a1, a2, label, num=None, r_ref=None):
    """Линейный размер вдоль оси детали с выносными линиями."""
    x1, x2 = X(a1), X(a2)
    out = []
    if r_ref is not None:
        for x in (x1, x2):
            out.append(line(x, Y(-r_ref), x, y + 12, "#7b8796", 0.9))
    out += [line(x1 - 14, y, x2 + 14, y, w=1.0), arrow(x1, y, -1, 0), arrow(x2, y, 1, 0),
            text((x1 + x2) / 2, y - 9, label, size=16)]
    if num is not None:
        out.append(mark(x2 + 40, y, num))
    return "".join(out)


def ext_line(a, r_from, r_to):
    """Выносная линия от контура к размерной линии."""
    return line(X(a), Y(r_from), X(a), Y(r_to), color="#7b8796", w=0.9)


def base_support(x, y, up=True):
    """Опора (база) по ГОСТ 3.1107-81 — равносторонний треугольник."""
    s = 13
    d = -1 if up else 1
    return (f'<polygon points="{x:.1f},{y:.1f} {x - s * 0.6:.1f},{y + d * s:.1f} '
            f'{x + s * 0.6:.1f},{y + d * s:.1f}" fill="none" stroke="{C_MAIN}" '
            f'stroke-width="2"/>')


def clamp(x, y, dx, dy):
    """Знак зажима: стрелка с хвостовиком, направленная на поверхность."""
    import math
    ln = math.hypot(dx, dy)
    ux, uy = dx / ln, dy / ln
    tail = 30
    return (line(x - ux * tail, y - uy * tail, x - ux * 9, y - uy * 9, C_MAIN, 2)
            + arrow(x, y, dx, dy, C_MAIN, 11))


def ra_sign(x, y, value):
    """Знак шероховатости Ra в правом верхнем углу."""
    return (f'<path d="M {x} {y} l 9 16 l 16 -30" fill="none" stroke="{C_DIM}" '
            f'stroke-width="1.6"/>'
            + line(x + 25, y - 14, x + 92, y - 14, C_DIM, 1.6)
            + text(x + 58, y - 20, f"Ra {value}", size=17, italic=True))


# --------------------------------------------------------------------------
# профили детали на разных стадиях
# --------------------------------------------------------------------------
def part_profile(d_out, l_total, d_boss, l_boss, d_bore, chamfer=0.0):
    """Верхняя половина сечения: поясок слева, фланец справа."""
    ro, rb, ri = d_out / 2, d_boss / 2, d_bore / 2
    seq = [(0, ri)]
    if chamfer:
        seq += [(0, rb - chamfer), (chamfer, rb)]
    else:
        seq += [(0, rb)]
    seq += [(l_boss, rb), (l_boss, ro), (l_total, ro), (l_total, ri)]
    return seq


ZAGOT = dict(d_out=177.8, l_total=47.0, d_boss=92.7, l_boss=26.0, d_bore=49.7)
OP010 = dict(d_out=175.0, l_total=44.0, d_boss=92.7, l_boss=26.0, d_bore=49.7)
OP015 = dict(d_out=175.0, l_total=44.0, d_boss=90.06, l_boss=26.0, d_bore=51.94, chamfer=2.0)
FINAL = dict(d_out=175.0, l_total=44.0, d_boss=90.0, l_boss=26.0, d_bore=52.0, chamfer=2.0)


def bolt_holes(seq_r=70.0, d=14.0, l_boss=26.0, l_total=44.0):
    """Крепёжные отверстия Ø14 на Ø140 — в сечении показаны сверху и снизу."""
    out = []
    for sign in (1, -1):
        y1, y2 = Y(sign * (seq_r - d / 2)), Y(sign * (seq_r + d / 2))
        x1, x2 = X(l_boss), X(l_total)
        out.append(f'<rect x="{x1:.1f}" y="{min(y1, y2):.1f}" width="{x2 - x1:.1f}" '
                   f'height="{abs(y2 - y1):.1f}" fill="#ffffff" stroke="{C_MAIN}" '
                   f'stroke-width="2.2"/>')
    return "".join(out)


def work_line(a1, r1, a2, r2):
    """Обрабатываемая на данной операции поверхность — утолщённая линия."""
    return (f'<line x1="{X(a1):.1f}" y1="{Y(r1):.1f}" x2="{X(a2):.1f}" y2="{Y(r2):.1f}" '
            f'stroke="{C_WORK}" stroke-width="5" stroke-linecap="round"/>')


def svg(body, caption, ra="6,3"):
    axis = line(X0 - 210, CY, X(56), CY, C_AXIS, 1.2, "22 5 4 5")
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">
<defs><pattern id="hatch" width="9" height="9" patternTransform="rotate(45)"
  patternUnits="userSpaceOnUse">
  <line x1="0" y1="0" x2="0" y2="9" stroke="{C_MAIN}" stroke-width="0.9"/></pattern></defs>
<rect width="{W}" height="{H}" fill="#ffffff"/>
{axis}
{body}
{ra_sign(W - 150, 52, ra)}
{text(W / 2, H - 26, caption, size=18)}
</svg>'''


# --------------------------------------------------------------------------
# сами эскизы
# --------------------------------------------------------------------------
def sketch_005():
    prof = part_profile(**ZAGOT)
    body = [hatched(prof), hatched(mirror(prof))]
    body += [
        dim_diameter(X0 - 190, 88.9, "&#216;177,8", None, a_ref=47),
        dim_diameter(X0 - 120, 46.35, "&#216;92,7", None, a_ref=0),
        dim_diameter(X(13), 24.85, "&#216;49,7", None, inner=True),
        dim_length(Y(-88.9) + 70, 0, 26, "26", None, r_ref=46.35),
        dim_length(Y(-88.9) + 130, 0, 47, "47", None, r_ref=88.9),
    ]
    return svg("".join(body), "005 Заготовительная. Поковка штампованная ГОСТ 7829-70", "12,5")


def sketch_010():
    prof = part_profile(**OP010)
    body = [hatched(prof), hatched(mirror(prof))]
    # обработка: торец фланца и наружная поверхность Ø175
    body += [work_line(44, 24.85, 44, 87.5), work_line(26, 87.5, 44, 87.5),
             work_line(26, -87.5, 44, -87.5), work_line(44, -24.85, 44, -87.5)]
    # базирование: поясок в патроне
    body += [base_support(X(13), Y(46.35), up=True),
             base_support(X(13), Y(-46.35), up=False),
             clamp(X(19), Y(46.35), 0, 1), clamp(X(19), Y(-46.35), 0, -1)]
    body += [
        dim_diameter(X0 - 170, 87.5, "&#216;175 h14(-1)", 2, a_ref=44),
        dim_length(Y(-88.9) + 80, 0, 44, "44 h14(-0,62)", 1, r_ref=87.5),
    ]
    return svg("".join(body), "010 Токарно-винторезная (установ А). Станок 16К20")


def sketch_015():
    prof = part_profile(**OP015)
    body = [hatched(prof), hatched(mirror(prof))]
    body += [work_line(0, 26.0, 0, 43.03), work_line(0, 45.03, 26, 45.03),
             work_line(0, -26.0, 0, -43.03), work_line(0, -45.03, 26, -45.03),
             work_line(0, 25.97, 44, 25.97), work_line(0, -25.97, 44, -25.97),
             work_line(0, 43.03, 2, 45.03), work_line(0, -43.03, 2, -45.03)]
    body += [base_support(X(36), Y(87.5), up=True),
             base_support(X(36), Y(-87.5), up=False),
             clamp(X(44), Y(60), -1, 0), clamp(X(44), Y(-60), -1, 0)]
    body += [
        dim_diameter(X0 - 170, 45.03, "&#216;90,06", 2, a_ref=26),
        dim_diameter(X(13), 25.97, "&#216;51,94", 1, inner=True),
        dim_length(Y(-88.9) + 70, 0, 26, "26", 4, r_ref=45.03),
        dim_length(Y(-88.9) + 130, 0, 44, "44", 5, r_ref=87.5),
        line(X(1), Y(44), X0 - 60, Y(64), "#7b8796", 0.9),
        text(X0 - 100, Y(64) - 7, "2&#215;45&#176;", size=15),
        mark(X0 - 148, Y(64) - 12, 3),
    ]
    return svg("".join(body), "015 Токарно-винторезная (установ Б). Станок 16К20", "1,6")


def sketch_020():
    prof = part_profile(**FINAL)
    body = [hatched(prof), hatched(mirror(prof)), bolt_holes()]
    body += [work_line(26, 63.0, 44, 63.0), work_line(26, 77.0, 44, 77.0),
             work_line(26, -63.0, 44, -63.0), work_line(26, -77.0, 44, -77.0)]
    body += [base_support(X(30), Y(87.5), up=True), base_support(X(30), Y(-87.5), up=False),
             clamp(X(44), Y(50), -1, 0), clamp(X(44), Y(-50), -1, 0)]
    body += [
        dim_diameter(X0 - 180, 70.0, "&#216;140", 2, a_ref=26),
        dim_local(X0 - 105, 63.0, 77.0, "4 отв. &#216;14", 1, a_ref=30),
        dim_length(Y(-88.9) + 80, 26, 44, "18", 3, r_ref=87.5),
    ]
    return svg("".join(body), "020 Вертикально-сверлильная. Станок 2Н135, кондуктор", "12,5")


def sketch_025():
    prof = part_profile(**FINAL)
    body = [hatched(prof), hatched(mirror(prof)), bolt_holes()]
    body += [work_line(0, 26.0, 44, 26.0), work_line(0, -26.0, 44, -26.0)]
    body += [base_support(X(36), Y(87.5), up=True), base_support(X(36), Y(-87.5), up=False),
             clamp(X(16), Y(45), 0, 1), clamp(X(16), Y(-45), 0, -1)]
    body += [dim_diameter(X(13), 26.0, "&#216;52 H7(+0,03)", 1, inner=True)]
    return svg("".join(body), "025 Внутришлифовальная. Станок 3К227", "1,6")


def sketch_030():
    prof = part_profile(**FINAL)
    body = [hatched(prof), hatched(mirror(prof)), bolt_holes()]
    body += [work_line(2, 45.0, 26, 45.0), work_line(2, -45.0, 26, -45.0)]
    body += [base_support(X(36), Y(87.5), up=True), base_support(X(36), Y(-87.5), up=False),
             clamp(X(44), Y(60), -1, 0), clamp(X(44), Y(-60), -1, 0)]
    body += [dim_diameter(X0 - 175, 45.0, "&#216;90 h8(-0,054)", 1, a_ref=26),
             dim_length(Y(-88.9) + 80, 0, 26, "26", 2, r_ref=45.0)]
    return svg("".join(body), "030 Круглошлифовальная. Станок 3М151", "1,6")


SKETCHES = [
    ("op_005_zagotovka.png", sketch_005),
    ("op_010_tokarnaya_A.png", sketch_010),
    ("op_015_tokarnaya_B.png", sketch_015),
    ("op_020_sverlilnaya.png", sketch_020),
    ("op_025_vnutrishlif.png", sketch_025),
    ("op_030_kruglошлиф.png".replace("ошлиф", "oshlif"), sketch_030),
]


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    out = argv[0] if argv else os.path.join(os.path.dirname(os.path.abspath(__file__)), "img")
    os.makedirs(out, exist_ok=True)
    for name, fn in SKETCHES:
        data = fn()
        with open(os.path.join(out, name.replace(".png", ".svg")), "w", encoding="utf-8") as f:
            f.write(data)
        cairosvg.svg2png(bytestring=data.encode("utf-8"),
                         write_to=os.path.join(out, name), scale=1.6)
        print("готово:", name, flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
