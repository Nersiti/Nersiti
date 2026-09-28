package com.nersiti.prokachka.core

import kotlinx.serialization.Serializable

/** Инвентарь, который может быть у пользователя сегодня. «Ничего» — это пустой набор. */
@Serializable
enum class Equipment(val title: String) {
    BAR("Турник"),
    DIP_BARS("Брусья"),
    DUMBBELLS("Гантели"),
    KETTLEBELL("Гиря"),
    BANDS("Резинки"),
    BENCH("Скамья/стул"),
    BACKPACK("Рюкзак с грузом"),
}

enum class MuscleGroup(val title: String) {
    CHEST("Грудь"),
    SHOULDERS("Плечи"),
    BACK("Спина"),
    LEGS("Ноги"),
    CORE("Пресс"),
    ARMS("Руки"),
}

/** Паттерн движения. Прогресс хранится по паттерну, а не по конкретному упражнению. */
@Serializable
enum class Pattern(val title: String, val group: MuscleGroup) {
    PUSH_H("Грудь", MuscleGroup.CHEST),
    PUSH_V("Плечи", MuscleGroup.SHOULDERS),
    PULL_V("Спина: вертикальная тяга", MuscleGroup.BACK),
    PULL_H("Спина: горизонтальная тяга", MuscleGroup.BACK),
    SQUAT("Ноги: присед", MuscleGroup.LEGS),
    LUNGE("Ноги: выпады", MuscleGroup.LEGS),
    HINGE("Ноги: задняя поверхность", MuscleGroup.LEGS),
    CORE("Пресс", MuscleGroup.CORE),
    BICEPS("Бицепс", MuscleGroup.ARMS),
    TRICEPS("Трицепс", MuscleGroup.ARMS),
    CALVES("Икры", MuscleGroup.LEGS),
}

@Serializable
enum class ExerciseType {
    /** Повторения с весом тела. */
    REPS,

    /** Удержание на время, в секундах. */
    TIME,

    /** Гантели или гиря: двойная прогрессия 8→12 повторов, затем вес больше. */
    WEIGHT,
}

/** Ограничения по здоровью, выбранные в онбординге. */
@Serializable
enum class InjuryTag(val title: String) {
    JUMPS("Без прыжков"),
    KNEES("Беречь колени"),
}

@Serializable
data class Exercise(
    val id: String,
    val name: String,
    val pattern: Pattern,
    val requires: List<Equipment> = emptyList(),
    /** Сложность внутри паттерна: 1 — самое лёгкое. */
    val difficulty: Int,
    val type: ExerciseType,
    /** Потолок повторов или секунд; выше него упражнение сменяется следующим на лестнице. */
    val cap: Int? = null,
    /** Ступень основной лестницы прогрессии паттерна. */
    val ladder: Boolean = false,
    /** Повторы считаются на каждую руку или ногу. */
    val perSide: Boolean = false,
    val avoid: List<InjuryTag> = emptyList(),
    /** Особый темп, например «5 с вниз». */
    val tempo: String? = null,
    /** Стартовый вес для WEIGHT, кг. */
    val startKg: Double? = null,
    val tip: String = "",
) {
    val limit: Int
        get() = cap ?: when (type) {
            ExerciseType.TIME -> ProgressionEngine.TIME_CAP
            ExerciseType.WEIGHT -> ProgressionEngine.WEIGHT_MAX_REPS
            ExerciseType.REPS -> ProgressionEngine.REPS_CAP
        }

    /** С чего начинается упражнение после перехода на новую ступень лестницы. */
    val resetBase: Int
        get() = if (type == ExerciseType.TIME) ProgressionEngine.TIME_RESET else ProgressionEngine.REPS_RESET
}

/** Что есть у пользователя сегодня. */
@Serializable
data class Inventory(
    val items: Set<Equipment> = emptySet(),
    val dumbbellsKg: List<Double> = emptyList(),
    val kettlebellsKg: List<Double> = emptyList(),
) {
    fun has(exercise: Exercise): Boolean =
        items.containsAll(exercise.requires) &&
            (exercise.type != ExerciseType.WEIGHT || weightsFor(exercise).isNotEmpty())

    fun weightsFor(exercise: Exercise): List<Double> = when {
        Equipment.DUMBBELLS in exercise.requires -> dumbbellsKg.sorted()
        Equipment.KETTLEBELL in exercise.requires -> kettlebellsKg.sorted()
        else -> emptyList()
    }

    companion object {
        val NOTHING = Inventory()
        val HOME = Inventory(setOf(Equipment.BENCH, Equipment.BACKPACK))
        val PLAYGROUND = Inventory(setOf(Equipment.BAR, Equipment.DIP_BARS, Equipment.BENCH))
        val GYM = Inventory(
            items = Equipment.entries.toSet(),
            dumbbellsKg = listOf(4.0, 6.0, 8.0, 10.0, 12.0, 14.0, 16.0, 18.0, 20.0),
            kettlebellsKg = listOf(8.0, 12.0, 16.0, 20.0, 24.0),
        )
    }
}

enum class DayTemplate(val title: String, val slots: List<List<Pattern>>) {
    FULL(
        "Всё тело",
        listOf(
            listOf(Pattern.PUSH_H),
            listOf(Pattern.PULL_V, Pattern.PULL_H),
            listOf(Pattern.SQUAT),
            listOf(Pattern.HINGE),
            listOf(Pattern.CORE),
        ),
    ),
    UPPER(
        "Верх",
        listOf(
            listOf(Pattern.PUSH_H),
            listOf(Pattern.PULL_V),
            listOf(Pattern.PUSH_V),
            listOf(Pattern.PULL_H),
            listOf(Pattern.TRICEPS, Pattern.BICEPS),
        ),
    ),
    LOWER(
        "Низ",
        listOf(
            listOf(Pattern.SQUAT),
            listOf(Pattern.HINGE),
            listOf(Pattern.LUNGE),
            listOf(Pattern.CALVES),
            listOf(Pattern.CORE),
        ),
    ),
    PUSH(
        "Жим",
        listOf(
            listOf(Pattern.PUSH_H),
            listOf(Pattern.PUSH_V),
            listOf(Pattern.PUSH_H),
            listOf(Pattern.PUSH_V),
            listOf(Pattern.TRICEPS),
        ),
    ),
    PULL(
        "Тяга",
        listOf(
            listOf(Pattern.PULL_V),
            listOf(Pattern.PULL_H),
            listOf(Pattern.PULL_V),
            listOf(Pattern.PULL_H),
            listOf(Pattern.BICEPS),
            listOf(Pattern.CORE),
        ),
    ),
    LEGS(
        "Ноги",
        listOf(
            listOf(Pattern.SQUAT),
            listOf(Pattern.HINGE),
            listOf(Pattern.LUNGE),
            listOf(Pattern.SQUAT),
            listOf(Pattern.CALVES),
        ),
    ),
    UPPER_FULL(
        "Верх",
        listOf(
            listOf(Pattern.PUSH_H),
            listOf(Pattern.PULL_V),
            listOf(Pattern.PUSH_V),
            listOf(Pattern.PULL_H),
            listOf(Pattern.BICEPS),
            listOf(Pattern.TRICEPS),
        ),
    ),
    LOWER_FULL(
        "Низ",
        listOf(
            listOf(Pattern.SQUAT),
            listOf(Pattern.HINGE),
            listOf(Pattern.LUNGE),
            listOf(Pattern.HINGE),
            listOf(Pattern.CALVES),
            listOf(Pattern.CORE),
        ),
    ),
}

enum class Mode(
    val title: String,
    val emoji: String,
    /** Неделя: «Т» — тренировка, «о» — отдых. */
    val week: String,
    val baseSets: Int,
    val extraSetFromDay15: Boolean,
    val restSec: Int,
    /** Рост нагрузки в день. */
    val k: Double,
    /** Старт в долях от результата теста. */
    val startPercent: Double,
    val minutes: Int,
    /** Шаблоны тренировок по порядку внутри недели. */
    val templates: List<DayTemplate>,
    val lastSetToFailure: Boolean,
) {
    SMOOTH(
        "Плавный", "🐢", "ТоТоТоо", 3, false, 90, 0.01, 0.50, 30,
        listOf(DayTemplate.FULL, DayTemplate.FULL, DayTemplate.FULL), false,
    ),
    MEDIUM(
        "Средний", "⚖️", "ТТоТТоо", 3, true, 75, 0.015, 0.60, 40,
        listOf(DayTemplate.UPPER, DayTemplate.LOWER, DayTemplate.UPPER, DayTemplate.LOWER), false,
    ),
    FAST(
        "Быстрый", "🔥", "ТТТоТТо", 4, true, 60, 0.02, 0.65, 50,
        listOf(DayTemplate.PUSH, DayTemplate.PULL, DayTemplate.LEGS, DayTemplate.UPPER_FULL, DayTemplate.LOWER_FULL),
        true,
    ),
    ;

    val workoutsPerWeek: Int get() = week.count { it == 'Т' }
}

/** Оценка после тренировки и поправка, которую она даёт. */
enum class Rating(val title: String, val adjustment: Int) {
    EASY("Легко", 1),
    OK("Норм", 0),
    HARD("Тяжело", -1),
    FAILED("Не смог", -2),
}

/** Результаты теста 1-го и 30-го дня. */
@Serializable
data class TestResult(
    val pushups: Int,
    val squats: Int,
    val pullups: Int,
    val plankSec: Int,
)

/** Прогресс паттерна: текущая ступень лестницы и формула роста от неё. */
@Serializable
data class PatternProgress(
    val pattern: Pattern,
    val exerciseId: String,
    val base: Int,
    val startDay: Int,
)

/** Двойная прогрессия упражнения с весом. */
@Serializable
data class WeightProgress(
    val exerciseId: String,
    val weightKg: Double,
    val startDay: Int,
)
