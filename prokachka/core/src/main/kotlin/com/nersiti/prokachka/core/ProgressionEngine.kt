package com.nersiti.prokachka.core

import kotlin.math.max
import kotlin.math.min
import kotlin.math.roundToInt

/**
 * Рост нагрузки: `цель = база × (1 + k × (день − день_старта + поправка))`.
 *
 * Когда цель превышает потолок упражнения, паттерн переходит на следующую ступень лестницы,
 * база сбрасывается до 8 повторов (20 с), а день_старта становится текущим.
 */
class ProgressionEngine(
    private val catalog: ExerciseCatalog,
    private val mode: Mode,
) {

    fun target(base: Int, startDay: Int, day: Int, adjustment: Int, k: Double = mode.k): Int {
        val factor = max(MIN_FACTOR, 1 + k * (day - startDay + adjustment))
        return max(1, (base * factor).roundToInt())
    }

    fun target(progress: PatternProgress, day: Int, adjustment: Int): Int =
        target(progress.base, progress.startDay, day, adjustment)

    /** Поднимает паттерн по лестнице, пока цель не уложится в потолок. */
    fun normalize(
        progress: PatternProgress,
        day: Int,
        adjustment: Int,
        excluded: Set<InjuryTag> = emptySet(),
    ): PatternProgress {
        var current = progress
        while (true) {
            val exercise = catalog[current.exerciseId]
            if (target(current, day, adjustment) <= exercise.limit) return current
            val next = catalog.nextOnLadder(exercise, excluded) ?: return current
            current = PatternProgress(current.pattern, next.id, next.resetBase, day)
        }
    }

    /** Цель на сегодня для текущей ступени, не выше потолка. */
    fun cappedTarget(progress: PatternProgress, day: Int, adjustment: Int): Int =
        min(target(progress, day, adjustment), catalog[progress.exerciseId].limit)

    /** Состояние для упражнения с весом, которое делается впервые. */
    fun startWeight(exercise: Exercise, available: List<Double>, cycleStartDay: Int = 1): WeightProgress {
        val wanted = exercise.startKg ?: available.first()
        val weight = available.minWith(compareBy({ kotlin.math.abs(it - wanted) }, { it }))
        return WeightProgress(exercise.id, weight, cycleStartDay)
    }

    /**
     * Двойная прогрессия: повторы растут от 8 до 12 по формуле, затем вес увеличивается
     * на следующую доступную ступень. Если тяжелее нет — медленный негатив и ещё один подход.
     *
     * Для веса k удвоен: с обычным k повторы дошли бы от 8 до 12 только к 38-му дню,
     * и вес внутри цикла не рос бы никогда.
     */
    fun weighted(
        progress: WeightProgress,
        available: List<Double>,
        day: Int,
        adjustment: Int,
    ): WeightedTarget {
        val weights = available.sorted()
        var state = progress.copy(weightKg = usableWeight(progress.weightKg, weights))
        while (true) {
            val reps = max(
                WEIGHT_MIN_REPS,
                target(WEIGHT_MIN_REPS_BASE, state.startDay, day, adjustment, mode.k * WEIGHT_K_MULTIPLIER),
            )
            if (reps <= WEIGHT_MAX_REPS) return WeightedTarget(state, reps, overloaded = false)
            val heavier = weights.firstOrNull { it > state.weightKg }
                ?: return WeightedTarget(state, WEIGHT_MAX_REPS, overloaded = true)
            state = state.copy(weightKg = heavier, startDay = day)
        }
    }

    private fun usableWeight(current: Double, weights: List<Double>): Double =
        if (current in weights) current else weights.lastOrNull { it <= current } ?: weights.first()

    /** Стартовые ступени и базы по результатам теста 1-го дня. */
    fun calibrate(test: TestResult, day: Int = 1, excluded: Set<InjuryTag> = emptySet()): Map<Pattern, PatternProgress> {
        val sp = mode.startPercent
        val push = test.pushups
        val pull = test.pullups
        val squat = min(test.squats, SQUAT_TEST_LIMIT)
        val plank = test.plankSec

        fun start(pattern: Pattern, id: String, base: Double, min: Int): PatternProgress =
            PatternProgress(pattern, id, max(min, base.roundToInt()), day)

        val raw = listOf(
            if (push >= 5) start(Pattern.PUSH_H, "pushup_classic", push * sp, 3)
            else start(Pattern.PUSH_H, "pushup_knee", (push + 8) * sp, 4),
            if (push >= 10) start(Pattern.PUSH_V, "pike_pushup", push * 0.4 * sp, 3)
            else start(Pattern.PUSH_V, "pike_knee", (push + 6) * 0.6 * sp, 4),
            start(Pattern.TRICEPS, "sphinx_pushup", push * 0.5 * sp, 4),
            when {
                pull < 3 -> start(Pattern.PULL_V, "pullup_negative", (6 + pull) * sp, 3)
                pull < 6 -> start(Pattern.PULL_V, "chinup", (pull + 2) * sp, 2)
                else -> start(Pattern.PULL_V, "pullup_classic", pull * sp, 2)
            },
            start(Pattern.PULL_H, "australian", (pull * 1.5 + 8) * sp, 5),
            if (pull >= 5) start(Pattern.BICEPS, "australian_chin", (pull + 4) * sp, 4)
            else start(Pattern.BICEPS, "towel_curl", 30 * sp, 10),
            if (squat >= 10) start(Pattern.SQUAT, "squat", squat * sp, 5)
            else start(Pattern.SQUAT, "box_squat", (squat + 5) * sp, 5),
            start(Pattern.LUNGE, "lunge_reverse", squat * 0.4 * sp, 5),
            if (squat >= 30) start(Pattern.HINGE, "glute_bridge_single", squat * 0.3 * sp, 6)
            else start(Pattern.HINGE, "glute_bridge", squat * 0.8 * sp, 8),
            start(Pattern.CALVES, "calf_raise", squat * 0.6 * sp, 10),
            start(Pattern.CORE, "plank", max(plank, 10) * sp, 10),
        )

        return raw.associate { progress ->
            val safe = safeStart(progress, excluded)
            safe.pattern to normalize(safe, day, 0, excluded)
        }
    }

    /** Если стартовое упражнение запрещено ограничениями, берём самую близкую разрешённую ступень. */
    private fun safeStart(progress: PatternProgress, excluded: Set<InjuryTag>): PatternProgress {
        val exercise = catalog[progress.exerciseId]
        if (exercise.avoid.none(excluded::contains)) return progress
        val ladder = catalog.ladder(progress.pattern, excluded)
        val replacement = ladder.lastOrNull { it.difficulty <= exercise.difficulty } ?: ladder.firstOrNull()
            ?: return progress
        return progress.copy(exerciseId = replacement.id)
    }

    companion object {
        const val REPS_CAP = 20
        const val TIME_CAP = 60
        const val REPS_RESET = 8
        const val TIME_RESET = 20
        const val WEIGHT_MIN_REPS = 8
        const val WEIGHT_MAX_REPS = 12
        private const val WEIGHT_MIN_REPS_BASE = 8
        private const val WEIGHT_K_MULTIPLIER = 2
        const val SQUAT_TEST_LIMIT = 50
        private const val MIN_FACTOR = 0.5

        /** Перерыв в днях, после которого автоматически ставится поправка −2. */
        const val BREAK_DAYS = 3
        const val BREAK_PENALTY = -2
    }
}

data class WeightedTarget(
    val progress: WeightProgress,
    val reps: Int,
    /** Тяжелее гантелей нет: добавляем медленный негатив и подход. */
    val overloaded: Boolean,
)
