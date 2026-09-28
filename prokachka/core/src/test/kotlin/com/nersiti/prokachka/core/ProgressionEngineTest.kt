package com.nersiti.prokachka.core

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class ProgressionEngineTest {

    private val catalog = ExerciseCatalog.default
    private val medium = ProgressionEngine(catalog, Mode.MEDIUM)

    @Test
    fun `формула роста`() {
        assertEquals(14, medium.target(base = 12, startDay = 1, day = 11, adjustment = 0))
        assertEquals(12, medium.target(base = 12, startDay = 1, day = 1, adjustment = 0))
        assertEquals(14, medium.target(base = 12, startDay = 1, day = 10, adjustment = 1))
        assertEquals(13, medium.target(base = 12, startDay = 1, day = 11, adjustment = -2))
    }

    @Test
    fun `лестница — смена упражнения при превышении потолка`() {
        val progress = PatternProgress(Pattern.PUSH_H, "pushup_classic", base = 18, startDay = 1)
        val day = (1..30).first { medium.target(progress, it, 0) > 20 }
        assertEquals(progress, medium.normalize(progress, day - 1, 0))

        val next = medium.normalize(progress, day, 0)
        assertEquals("pushup_close", next.exerciseId)
        assertEquals(8, next.base)
        assertEquals(day, next.startDay)
    }

    @Test
    fun `после лестницы на время база 20 секунд`() {
        val progress = PatternProgress(Pattern.CORE, "plank", base = 70, startDay = 1)
        val next = medium.normalize(progress, 1, 0)
        assertEquals("side_plank", next.exerciseId)
        assertEquals(20, next.base)
    }

    @Test
    fun `калибровка по тесту`() {
        val weak = medium.calibrate(TestResult(pushups = 3, squats = 8, pullups = 0, plankSec = 15))
        assertEquals("pushup_knee", weak.getValue(Pattern.PUSH_H).exerciseId)
        assertEquals("pullup_negative", weak.getValue(Pattern.PULL_V).exerciseId)
        assertEquals("box_squat", weak.getValue(Pattern.SQUAT).exerciseId)

        val regular = medium.calibrate(TestResult(pushups = 20, squats = 30, pullups = 8, plankSec = 60))
        assertEquals(PatternProgress(Pattern.PUSH_H, "pushup_classic", 12, 1), regular.getValue(Pattern.PUSH_H))
        assertEquals("pullup_classic", regular.getValue(Pattern.PULL_V).exerciseId)
        assertEquals(Pattern.entries.toSet(), regular.keys)

        val strong = medium.calibrate(TestResult(pushups = 50, squats = 50, pullups = 20, plankSec = 180))
        strong.values.forEach { state ->
            assertTrue(medium.target(state, 1, 0) <= catalog[state.exerciseId].limit, state.toString())
        }
    }

    @Test
    fun `калибровка учитывает ограничения`() {
        val progress = medium.calibrate(TestResult(50, 50, 10, 60), excluded = setOf(InjuryTag.KNEES, InjuryTag.JUMPS))
        progress.values.forEach { state ->
            assertTrue(catalog[state.exerciseId].avoid.isEmpty() || state.pattern == Pattern.LUNGE, state.toString())
        }
    }

    @Test
    fun `двойная прогрессия с гантелями`() {
        val press = catalog["db_shoulder_press"]
        val weights = listOf(6.0, 8.0, 10.0)
        val start = medium.startWeight(press, weights)
        assertEquals(6.0, start.weightKg)

        val day11 = medium.weighted(start, weights, day = 11, adjustment = 0)
        assertEquals(10, day11.reps)
        assertEquals(6.0, day11.progress.weightKg)

        val day30 = medium.weighted(start, weights, day = 30, adjustment = 0)
        assertEquals(8.0, day30.progress.weightKg)
        assertEquals(8, day30.reps)
        assertFalse(day30.overloaded)
    }

    @Test
    fun `тяжелее гантелей нет — медленный негатив`() {
        val press = catalog["db_shoulder_press"]
        val state = medium.startWeight(press, listOf(8.0))
        val result = medium.weighted(state, listOf(8.0), day = 30, adjustment = 0)
        assertTrue(result.overloaded)
        assertEquals(12, result.reps)

        val workout = WorkoutGenerator(catalog).generate(
            GenerationRequest(
                mode = Mode.MEDIUM,
                day = 29,
                progress = medium.calibrate(TestResult(20, 30, 0, 60)),
                weights = mapOf(state.exerciseId to state),
                inventory = Inventory(setOf(Equipment.DUMBBELLS), dumbbellsKg = listOf(8.0)),
            ),
        ).workout
        val planned = workout.exercises.first { it.exercise.id == "db_shoulder_press" }
        assertTrue(planned.slowNegative)
        assertEquals(5, planned.sets)
    }

    @Test
    fun `оценки дают поправку`() {
        assertEquals(listOf(1, 0, -1, -2), Rating.entries.map { it.adjustment })
    }
}
