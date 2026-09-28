"""Прогон 30 дней по формуле прогрессии, чтобы подобрать коэффициенты.

    python3 tools/simulate.py --pushups 20 --mode MEDIUM

Формула та же, что в ProgressionEngine:
    цель = база × (1 + k × (день − день_старта + поправка))
Лестница отжиманий и потолок 20 повторов тоже совпадают с exercises.json.
"""
import argparse

MODES = {
    # k, старт от теста, неделя
    "SMOOTH": (0.010, 0.50, "ТоТоТоо"),
    "MEDIUM": (0.015, 0.60, "ТТоТТоо"),
    "FAST": (0.020, 0.65, "ТТТоТТо"),
}
LADDER = ["Отжимания с колен", "Классические", "Узкие", "Ноги на стуле", "«Лучник»", "На одной руке"]
CAP, RESET = 20, 8


def target(base, start, day, k, adj=0):
    return max(1, round(base * max(0.5, 1 + k * (day - start + adj))))


def simulate(mode, pushups, adj):
    k, start_pct, week = MODES[mode]
    step = 1 if pushups >= 5 else 0
    base = max(3, round(pushups * start_pct)) if step else max(4, round((pushups + 8) * start_pct))
    start = 1
    weight_start, weight = 1, 8.0
    print(f"{mode}: k={k}, старт {int(start_pct * 100)}% от теста ({pushups} отжиманий), поправка {adj}")
    print("день  отжимания                   гантели")
    for day in range(2, 30):
        if week[(day - 1) % 7] != "Т":
            continue
        while target(base, start, day, k, adj) > CAP and step + 1 < len(LADDER):
            step, base, start = step + 1, RESET, day
        reps = min(CAP, target(base, start, day, k, adj))
        db = target(8, weight_start, day, 2 * k, adj)
        if db > 12:
            weight, weight_start = weight + 2, day
            db = target(8, weight_start, day, 2 * k, adj)
        print(f"{day:>4}  {LADDER[step]:<18} {reps:>3}   {db:>2} × {weight:g} кг")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=MODES, default="MEDIUM")
    parser.add_argument("--pushups", type=int, default=20)
    parser.add_argument("--adj", type=int, default=0, help="поправка от оценок")
    args = parser.parse_args()
    simulate(args.mode, args.pushups, args.adj)
