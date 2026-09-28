package com.nersiti.prokachka.core

import java.time.LocalDate

/** Уровни прокачки по группам мышц: номер ступени лестницы паттерна. */
object Levels {

    fun byPattern(catalog: ExerciseCatalog, progress: Map<Pattern, PatternProgress>): Map<Pattern, Int> =
        progress.mapValues { (_, state) -> catalog.ladderLevel(catalog[state.exerciseId]) }

    /** «Спина — ур. 4»: среднее по паттернам группы. */
    fun byGroup(catalog: ExerciseCatalog, progress: Map<Pattern, PatternProgress>): Map<MuscleGroup, Int> =
        byPattern(catalog, progress).entries
            .groupBy({ it.key.group }, { it.value })
            .mapValues { (_, levels) -> Math.round(levels.average()).toInt() }
            .toSortedMap(compareBy { it.ordinal })
}

object Streak {

    /** Серия: дни подряд с тренировкой или растяжкой, заканчивая сегодня или вчера. */
    fun current(activeDays: Set<LocalDate>, today: LocalDate): Int {
        var day = if (today in activeDays) today else today.minusDays(1)
        var count = 0
        while (day in activeDays) {
            count++
            day = day.minusDays(1)
        }
        return count
    }

    fun best(activeDays: Set<LocalDate>): Int {
        var best = 0
        for (day in activeDays) {
            if (day.minusDays(1) in activeDays) continue
            var length = 0
            var cursor = day
            while (cursor in activeDays) {
                length++
                cursor = cursor.plusDays(1)
            }
            best = maxOf(best, length)
        }
        return best
    }
}

data class Stats(
    val workoutsDone: Int = 0,
    val bestStreak: Int = 0,
    val maxPullups: Int = 0,
    val cyclesCompleted: Int = 0,
    val maxGroupLevel: Int = 0,
    val photosTaken: Int = 0,
)

enum class Achievement(val title: String, val description: String, val unlocked: (Stats) -> Boolean) {
    FIRST_WORKOUT("Первый шаг", "Первая тренировка позади", { it.workoutsDone >= 1 }),
    FIRST_PULLUP("Первое подтягивание", "Подтянулся хотя бы раз", { it.maxPullups >= 1 }),
    STREAK_7("7 дней подряд", "Неделя без пропусков", { it.bestStreak >= 7 }),
    TEN_WORKOUTS("Десятка", "10 тренировок", { it.workoutsDone >= 10 }),
    LEVEL_5("Прокачан", "Любая группа мышц на 5-м уровне", { it.maxGroupLevel >= 5 }),
    PHOTO_10("Фотолетопись", "10 фото прогресса", { it.photosTaken >= 10 }),
    STREAK_30("Железная воля", "30 дней подряд", { it.bestStreak >= 30 }),
    FULL_30("30/30", "Пройден полный цикл", { it.cyclesCompleted >= 1 }),
    ;

    companion object {
        fun unlocked(stats: Stats): List<Achievement> = entries.filter { it.unlocked(stats) }
    }
}

/** Ежедневный чек-лист восстановления. */
object DailyChecklist {
    const val SLEEP = "Сон 7–9 часов"
    const val WATER = "Вода 30–35 мл на кг веса"

    fun protein(weightKg: Double?): String =
        if (weightKg == null) "Белок ≈1,6 г на кг веса"
        else "Белок ≈${Math.round(weightKg * 1.6)} г (1,6 г на кг)"
}
