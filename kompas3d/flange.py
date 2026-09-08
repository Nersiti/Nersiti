# -*- coding: utf-8 -*-
"""Построение детали «Фланец» в КОМПАС-3D через COM-API.

Деталь строится полностью автоматически:
    1) эскиз Ø120 на плоскости XY  -> операция выдавливания (плита 14 мм);
    2) эскиз Ø70 на той же плоскости -> приклеенный элемент (бобышка 30 мм);
    3) эскиз Ø40  -> вырезание «через всё» в обе стороны (центральное отверстие);
    4) эскиз из 4 окружностей Ø11 на окружности Ø95 -> вырезание «через всё»
       (крепёжные отверстия).

Запуск (Windows, КОМПАС-3D установлен):
    pip install pywin32
    python flange.py
    python flange.py --d-outer 160 --bolt-count 6 --out C:\\Temp\\flange.m3d

Все размеры — в миллиметрах.
"""

from __future__ import annotations

import argparse
import math
import os
import sys

# GUID'ы библиотек типов КОМПАС-3D (те же, что выдаёт сам КОМПАС
# при экспорте макроса в Python).
TLB_API5 = "{0422828C-F174-495E-AC5D-D31014DBBE87}"
TLB_CONST_3D = "{2CAF168C-7961-4B90-9DA2-701419BEEFE3}"

LINE_MAIN = 1  # стиль линии «основная»


class KompasError(RuntimeError):
    pass


def connect():
    """Подключается к запущенному (или запускает новый) КОМПАС-3D."""
    try:
        import pythoncom
        from win32com.client import Dispatch, gencache
    except ImportError as exc:  # pragma: no cover - только на не-Windows
        raise KompasError(
            "Нужен pywin32 и Windows с установленным КОМПАС-3D: pip install pywin32"
        ) from exc

    api5 = gencache.EnsureModule(TLB_API5, 0, 1, 0)
    const3d = gencache.EnsureModule(TLB_CONST_3D, 0, 1, 0).constants

    kompas = api5.KompasObject(
        Dispatch("Kompas.Application.5")._oleobj_.QueryInterface(
            api5.KompasObject.CLSID, pythoncom.IID_IDispatch
        )
    )
    return kompas, const3d


def new_part(kompas, const3d, visible=True):
    """Создаёт новый документ-деталь и возвращает его корневой компонент."""
    doc = kompas.Document3D()
    # Create(invisible, part): первый аргумент — «невидимый документ»,
    # второй — True для детали (False дал бы сборку).
    if not doc.Create(not visible, True):
        raise KompasError("Не удалось создать документ-деталь")
    return doc, doc.GetPart(const3d.pTop_Part)


def make_sketch(part, const3d, draw):
    """Создаёт эскиз на плоскости XY и рисует в нём через callback draw(doc2d)."""
    sketch = part.NewEntity(const3d.o3d_sketch)
    definition = sketch.GetDefinition()
    definition.SetPlane(part.GetDefaultEntity(const3d.o3d_planeXOY))
    if not sketch.Create():
        raise KompasError("Не удалось создать эскиз")

    doc2d = definition.BeginEdit()
    draw(doc2d)
    definition.EndEdit()
    return sketch


def extrude(part, const3d, sketch, depth, base=True):
    """Выдавливание эскиза на depth мм в прямом направлении."""
    obj_type = const3d.o3d_baseExtrusion
    if not base:
        obj_type = getattr(const3d, "o3d_bossExtrusion", const3d.o3d_baseExtrusion)

    operation = part.NewEntity(obj_type)
    definition = operation.GetDefinition()
    definition.SetSketch(sketch)

    param = definition.ExtrusionParam()
    param.direction = const3d.dtNormal
    param.typeNormal = const3d.etBlind
    param.depthNormal = depth
    param.draftOutwardNormal = False
    param.draftValueNormal = 0

    if not operation.Create():
        raise KompasError("Не удалось выполнить выдавливание на %s мм" % depth)
    return operation


def cut_through(part, const3d, sketch):
    """Вырезание выдавливанием «через всё» в обе стороны."""
    operation = part.NewEntity(const3d.o3d_cutExtrusion)
    definition = operation.GetDefinition()
    definition.SetSketch(sketch)
    definition.directionType = const3d.dtBoth

    param = definition.ExtrusionParam()
    param.direction = const3d.dtBoth
    param.typeNormal = const3d.etThroughAll
    param.typeReverse = const3d.etThroughAll

    if not operation.Create():
        raise KompasError("Не удалось выполнить вырезание")
    return operation


def build(args):
    kompas, const3d = connect()
    kompas.Visible = args.visible
    kompas.ActivateControllerAPI()

    doc, part = new_part(kompas, const3d, visible=args.visible)
    part.name = args.name
    part.SetAdvancedColor(0x00B0B0B0, 0.8, 0.8, 0.8, 0.8, 1.0, 0.5)
    part.Update()

    # 1. Плита.
    plate_sketch = make_sketch(
        part, const3d,
        lambda d2d: d2d.ksCircle(0, 0, args.d_outer / 2.0, LINE_MAIN),
    )
    extrude(part, const3d, plate_sketch, args.plate, base=True)

    # 2. Бобышка: строится от той же плоскости XY, поэтому «прорастает»
    #    сквозь плиту и объединяется с ней без выбора грани.
    hub_sketch = make_sketch(
        part, const3d,
        lambda d2d: d2d.ksCircle(0, 0, args.d_hub / 2.0, LINE_MAIN),
    )
    extrude(part, const3d, hub_sketch, args.plate + args.hub, base=False)

    # 3. Центральное отверстие.
    bore_sketch = make_sketch(
        part, const3d,
        lambda d2d: d2d.ksCircle(0, 0, args.d_bore / 2.0, LINE_MAIN),
    )
    cut_through(part, const3d, bore_sketch)

    # 4. Крепёжные отверстия по окружности.
    def draw_bolt_holes(d2d):
        radius = args.bolt_circle / 2.0
        step = 2 * math.pi / args.bolt_count
        for i in range(args.bolt_count):
            angle = i * step + math.radians(args.bolt_offset)
            d2d.ksCircle(
                radius * math.cos(angle),
                radius * math.sin(angle),
                args.bolt_d / 2.0,
                LINE_MAIN,
            )

    bolts_sketch = make_sketch(part, const3d, draw_bolt_holes)
    cut_through(part, const3d, bolts_sketch)

    part.Update()

    path = os.path.abspath(args.out)
    if not doc.SaveAs(path):
        raise KompasError("Не удалось сохранить деталь в %s" % path)

    if not args.keep_open:
        doc.close()
    return path


def parse_args(argv=None):
    p = argparse.ArgumentParser(
        description="Строит деталь «Фланец» в КОМПАС-3D. Размеры в мм."
    )
    p.add_argument("--name", default="Фланец", help="имя детали в дереве модели")
    p.add_argument("--d-outer", type=float, default=120.0, help="наружный диаметр плиты")
    p.add_argument("--d-hub", type=float, default=70.0, help="диаметр бобышки")
    p.add_argument("--d-bore", type=float, default=40.0, help="диаметр центрального отверстия")
    p.add_argument("--plate", type=float, default=14.0, help="толщина плиты")
    p.add_argument("--hub", type=float, default=16.0, help="высота бобышки над плитой")
    p.add_argument("--bolt-circle", type=float, default=95.0, help="диаметр окружности центров отверстий")
    p.add_argument("--bolt-d", type=float, default=11.0, help="диаметр крепёжного отверстия")
    p.add_argument("--bolt-count", type=int, default=4, help="количество крепёжных отверстий")
    p.add_argument("--bolt-offset", type=float, default=45.0, help="угол первого отверстия, град.")
    p.add_argument("--out", default="flange.m3d", help="путь для сохранения файла детали")
    p.add_argument("--hidden", dest="visible", action="store_false",
                   help="строить, не показывая окно КОМПАСа")
    p.add_argument("--close", dest="keep_open", action="store_false",
                   help="закрыть документ после сохранения")
    p.set_defaults(visible=True, keep_open=True)

    args = p.parse_args(argv)

    if args.d_bore >= args.d_hub:
        p.error("--d-bore должен быть меньше --d-hub")
    if args.d_hub >= args.d_outer:
        p.error("--d-hub должен быть меньше --d-outer")
    if args.bolt_circle + args.bolt_d >= args.d_outer:
        p.error("крепёжные отверстия выходят за наружный диаметр")
    if args.bolt_circle - args.bolt_d <= args.d_hub:
        p.error("крепёжные отверстия пересекают бобышку")
    if args.bolt_count < 1:
        p.error("--bolt-count должен быть >= 1")
    return args


def main(argv=None):
    args = parse_args(argv)
    try:
        path = build(args)
    except KompasError as exc:
        print("Ошибка: %s" % exc, file=sys.stderr)
        return 1
    print("Деталь построена и сохранена: %s" % path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
