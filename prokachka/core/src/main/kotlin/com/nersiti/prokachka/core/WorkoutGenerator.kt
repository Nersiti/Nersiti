package com.nersiti.prokachka.core

import kotlin.math.abs
import kotlin.math.max
import kotlin.math.min
import kotlin.math.roundToInt

data class GenerationRequest(
    val mode: Mode,
    val day: Int,
    val cycle: Int = 1,
    val adjustment: Int = 0,
    val progress: Map<Pattern, PatternProgress>,
    val weights: Map<String, WeightProgress> = emptyMap(),
    val inventory: Inventory = Inventory.NOTHING,
    val excluded: Set<InjuryTag> = emptySet(),
    /** Упражнения прошлой тренировки: они уходят в конец очереди. */
    val recentExerciseIds: Set<String> = emptySet(),
)

data class PlannedExercise(
    val exercise: Exercise,
    val pattern: Pattern,
    val sets: Int,
    /** Повторы (на сторону, если perSide) или секунды. 0 — «на максимум» в тесте. */
    val target: Int,
    val weightKg: Double? = null,
    /** Медленный негатив 3 с вниз. */
    val slowNegative: Boolean = false,
    /** Упражнение легче уровня паттерна, поэтому добавлены подход и медленный негатив. */
    val compensated: Boolean = false,
    val lastSetToFailure: Boolean = false,
) {
    val isTime: Boolean get() = exercise.type == ExerciseType.TIME

    /** Строка вида «3 × 14», «3 × 30 с», «3 × 10 на руку · 8 кг». */
    val summary: String
        get() = buildString {
            append(sets).append(" × ")
            if (target == 0) append("макс.") else append(target)
            if (isTime) append(" с")
            if (exercise.perSide) append(sideLabel(exercise.pattern))
            weightKg?.let { append(" · ").append(formatKg(it)).append(" кг") }
        }

    private fun sideLabel(pattern: Pattern): String = when (pattern.group) {
        MuscleGroup.LEGS -> " на ногу"
        MuscleGroup.CORE -> " на сторону"
        else -> " на руку"
    }
}

data class Workout(
    val day: Int,
    val cycle: Int,
    val kind: DayKind,
    val template: DayTemplate?,
    val exercises: List<PlannedExercise>,
    val restSec: Int,
    val warmupMin: Int = WorkoutGenerator.WARMUP_MIN,
    val cooldownMin: Int = WorkoutGenerator.COOLDOWN_MIN,
    val light: Boolean = false,
) {
    val title: String
        get() = when (kind) {
            DayKind.TEST -> "Тест: калибровка"
            DayKind.FINAL_TEST -> "Финальный тест"
            DayKind.STRETCH -> "Растяжка"
            DayKind.WORKOUT -> template?.title ?: "Тренировка"
        }

    /** Примерная длительность с разминкой и заминкой. */
    val estimatedMinutes: Int
        get() {
            if (kind == DayKind.STRETCH) return Stretching.MINUTES
            val work = exercises.sumOf { planned ->
                val oneSet = when {
                    planned.target == 0 -> 45
                    planned.isTime -> planned.target
                    else -> planned.target * if (planned.slowNegative || planned.exercise.tempo != null) 5 else 3
                } * if (planned.exercise.perSide) 2 else 1
                planned.sets * oneSet + (planned.sets - 1) * restSec + TRANSITION_SEC
            }
            return ((work + (warmupMin + cooldownMin) * 60) / 60.0).roundToInt()
        }

    private companion object {
        const val TRANSITION_SEC = 60
    }
}

/** Результат генерации: тренировка и состояние прогресса, которое сохраняется после её выполнения. */
data class GeneratedWorkout(
    val workout: Workout,
    val progress: Map<Pattern, PatternProgress>,
    val weights: Map<String, WeightProgress>,
)

class WorkoutGenerator(
    private val catalog: ExerciseCatalog = ExerciseCatalog.default,
) {

    fun generate(request: GenerationRequest): GeneratedWorkout {
        val kind = Schedule.kind(request.mode, request.day, request.cycle)
        return when (kind) {
            DayKind.TEST, DayKind.FINAL_TEST -> GeneratedWorkout(testWorkout(request, kind), request.progress, request.weights)
            DayKind.STRETCH -> GeneratedWorkout(
                Workout(request.day, request.cycle, kind, null, emptyList(), restSec = 0),
                request.progress,
                request.weights,
            )
            DayKind.WORKOUT -> training(request)
        }
    }

    private fun testWorkout(request: GenerationRequest, kind: DayKind): Workout {
        val tests = listOf(
            "pushup_classic" to Pattern.PUSH_H,
            "squat" to Pattern.SQUAT,
            "pullup_classic" to Pattern.PULL_V,
            "plank" to Pattern.CORE,
        )
        return Workout(
            day = request.day,
            cycle = request.cycle,
            kind = kind,
            template = null,
            exercises = tests.map { (id, pattern) ->
                PlannedExercise(catalog[id], pattern, sets = 1, target = 0, lastSetToFailure = true)
            },
            restSec = TEST_REST_SEC,
        )
    }

    private fun training(request: GenerationRequest): GeneratedWorkout {
        val mode = request.mode
        val day = request.day
        val engine = ProgressionEngine(catalog, mode)
        val template = Schedule.template(mode, day)
        val occurrence = Schedule.occurrence(mode, day)
        val light = Schedule.isLight(day, request.cycle)
        val sets = Schedule.sets(mode, day, request.cycle)

        val progress = request.progress.toMutableMap()
        val weights = request.weights.toMutableMap()
        val usedToday = mutableSetOf<String>()
        val planned = mutableListOf<PlannedExercise>()

        for (slot in template.slots) {
            val wanted = slot[occurrence % slot.size]
            val (pattern, exercise) = pick(wanted, request, usedToday, progress, engine) ?: continue
            usedToday += exercise.id

            val current = engine.normalize(progress.getValue(pattern), day, request.adjustment, request.excluded)
            progress[pattern] = current
            val level = catalog[current.exerciseId]

            var item = if (exercise.type == ExerciseType.WEIGHT) {
                val available = request.inventory.weightsFor(exercise)
                val state = weights[exercise.id] ?: engine.startWeight(exercise, available)
                val result = engine.weighted(state, available, day, request.adjustment)
                weights[exercise.id] = result.progress
                PlannedExercise(
                    exercise = exercise,
                    pattern = pattern,
                    sets = sets + if (result.overloaded) 1 else 0,
                    target = result.reps,
                    weightKg = result.progress.weightKg,
                    slowNegative = result.overloaded,
                )
            } else {
                bodyweight(exercise, pattern, level, engine.cappedTarget(current, day, request.adjustment), sets)
            }

            if (light) item = item.copy(target = max(1, (item.target * LIGHT_FACTOR).roundToInt()))
            planned += item
        }

        if (mode.lastSetToFailure && !light) {
            planned.replaceAll { it.copy(lastSetToFailure = true) }
        }

        val workout = Workout(day, request.cycle, DayKind.WORKOUT, template, planned, mode.restSec, light = light)
        return GeneratedWorkout(workout, progress, weights)
    }

    /**
     * Выбор упражнения для паттерна: доступное по инвентарю, без запретов,
     * со сложностью ближе всего к уровню паттерна. Упражнения с весом берутся первыми:
     * их сложность подстраивается весом.
     */
    private fun pick(
        wanted: Pattern,
        request: GenerationRequest,
        usedToday: Set<String>,
        progress: Map<Pattern, PatternProgress>,
        engine: ProgressionEngine,
    ): Pair<Pattern, Exercise>? {
        for (pattern in listOf(wanted) + FALLBACKS[wanted].orEmpty()) {
            val state = progress[pattern] ?: continue
            val levelExercise = catalog[engine.normalize(state, request.day, request.adjustment, request.excluded).exerciseId]
            val level = levelExercise.difficulty
            val candidates = catalog.forPattern(pattern).filter {
                request.inventory.has(it) && it.avoid.none(request.excluded::contains) && it.id !in usedToday
            }
            if (candidates.isEmpty()) continue

            val weighted = candidates.filter { it.type == ExerciseType.WEIGHT && it.difficulty <= level + 1 }
            val pool = weighted.ifEmpty { candidates }
            val best = pool.withIndex().sortedWith(
                compareBy<IndexedValue<Exercise>>(
                    { distanceBucket(it.value, level) },
                    { it.value.id in request.recentExerciseIds },
                    { distance(it.value, level) },
                    { if (it.value.difficulty >= level) 0 else 1 },
                    { it.index },
                ),
            ).first().value
            return pattern to best
        }
        return null
    }

    private fun distance(exercise: Exercise, level: Int): Int =
        if (exercise.type == ExerciseType.WEIGHT) 0 else abs(exercise.difficulty - level)

    /** Варианты в пределах одной ступени считаются равноценными, чтобы работала ротация. */
    private fun distanceBucket(exercise: Exercise, level: Int): Int =
        distance(exercise, level).let { if (it <= 1) 0 else it }

    private fun bodyweight(
        exercise: Exercise,
        pattern: Pattern,
        level: Exercise,
        levelTarget: Int,
        sets: Int,
    ): PlannedExercise {
        var value = convert(levelTarget.toDouble(), from = level.type, to = exercise.type)
        val gap = exercise.difficulty - level.difficulty
        val compensated = gap < 0
        value = when {
            gap < 0 -> value * (1 + EASIER_STEP * -gap)
            gap > 0 -> value * max(HARDER_MIN, 1 - HARDER_STEP * gap)
            else -> value
        }
        val minimum = if (exercise.type == ExerciseType.TIME) MIN_SECONDS else MIN_REPS
        val target = min(exercise.limit, max(minimum, value.roundToInt()))
        return PlannedExercise(
            exercise = exercise,
            pattern = pattern,
            sets = sets + if (compensated) 1 else 0,
            target = target,
            slowNegative = compensated,
            compensated = compensated,
        )
    }

    private fun convert(value: Double, from: ExerciseType, to: ExerciseType): Double = when {
        from == ExerciseType.TIME && to != ExerciseType.TIME -> value / SECONDS_PER_REP
        from != ExerciseType.TIME && to == ExerciseType.TIME -> value * SECONDS_PER_REP
        else -> value
    }

    companion object {
        const val WARMUP_MIN = 5
        const val COOLDOWN_MIN = 5
        private const val TEST_REST_SEC = 180
        private const val LIGHT_FACTOR = 0.8
        private const val EASIER_STEP = 0.15
        private const val HARDER_STEP = 0.2
        private const val HARDER_MIN = 0.4
        private const val MIN_REPS = 3
        private const val MIN_SECONDS = 10
        private const val SECONDS_PER_REP = 3.0

        /** Замены, если для паттерна не осталось упражнений (например, выпады при больных коленях). */
        private val FALLBACKS = mapOf(
            Pattern.LUNGE to listOf(Pattern.HINGE, Pattern.SQUAT),
            Pattern.SQUAT to listOf(Pattern.HINGE),
            Pattern.PULL_V to listOf(Pattern.PULL_H),
            Pattern.PULL_H to listOf(Pattern.PULL_V),
            Pattern.PUSH_V to listOf(Pattern.PUSH_H),
            Pattern.PUSH_H to listOf(Pattern.PUSH_V),
            Pattern.BICEPS to listOf(Pattern.PULL_H),
            Pattern.TRICEPS to listOf(Pattern.PUSH_H),
        )
    }
}

internal fun formatKg(kg: Double): String =
    if (kg % 1.0 == 0.0) kg.toInt().toString() else kg.toString().replace('.', ',')
