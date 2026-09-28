package com.nersiti.prokachka.core

import java.time.LocalDate
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNull
import kotlin.test.assertTrue

class CatalogTest {

    private val catalog = ExerciseCatalog.default

    @Test
    fun `в базе около 70 упражнений и больше`() {
        assertTrue(catalog.exercises.size >= 70, "Упражнений: ${catalog.exercises.size}")
    }

    @Test
    fun `у каждого паттерна есть вариант без инвентаря`() {
        for (pattern in Pattern.entries) {
            assertTrue(catalog.forPattern(pattern).any { it.requires.isEmpty() }, pattern.name)
        }
    }

    @Test
    fun `лестницы идут строго по возрастанию сложности`() {
        for (pattern in Pattern.entries) {
            val ladder = catalog.ladder(pattern)
            assertTrue(ladder.size >= 3, pattern.name)
            assertEquals(ladder.map { it.difficulty }.distinct(), ladder.map { it.difficulty }, pattern.name)
            assertTrue(ladder.none { it.type == ExerciseType.WEIGHT }, pattern.name)
        }
    }

    @Test
    fun `у всех упражнений есть подсказка по технике, а у весовых — стартовый вес`() {
        for (exercise in catalog.exercises) {
            assertTrue(exercise.tip.isNotBlank(), exercise.id)
            if (exercise.type == ExerciseType.WEIGHT) {
                assertTrue(exercise.startKg != null, exercise.id)
                assertTrue(Equipment.DUMBBELLS in exercise.requires || Equipment.KETTLEBELL in exercise.requires, exercise.id)
            }
        }
    }

    @Test
    fun `стартовые упражнения калибровки есть в базе`() {
        for (mode in Mode.entries) {
            val progress = ProgressionEngine(catalog, mode).calibrate(TestResult(0, 0, 0, 0))
            progress.values.forEach { catalog[it.exerciseId] }
        }
    }
}

class ScheduleTest {

    @Test
    fun `расписание недели`() {
        fun week(mode: Mode) = (1..7).joinToString("") { if (Schedule.isTraining(mode, it)) "Т" else "о" }
        assertEquals("ТоТоТоо", week(Mode.SMOOTH))
        assertEquals("ТТоТТоо", week(Mode.MEDIUM))
        assertEquals("ТТТоТТо", week(Mode.FAST))
        assertEquals(listOf(3, 4, 5), Mode.entries.map { it.workoutsPerWeek })
    }

    @Test
    fun `шаблоны Быстрого по порядку`() {
        assertEquals(
            listOf(DayTemplate.PUSH, DayTemplate.PULL, DayTemplate.LEGS, DayTemplate.UPPER_FULL, DayTemplate.LOWER_FULL),
            listOf(8, 9, 10, 12, 13).map { Schedule.template(Mode.FAST, it) },
        )
    }

    @Test
    fun `фото сбоку и со спины в дни 1, 10, 20 и 30`() {
        assertEquals(setOf(1, 10, 20, 30), Schedule.fullPhotoDays)
    }
}

class ProgramCalendarTest {

    private val monday = LocalDate.of(2026, 9, 28)

    @Test
    fun `тренировочный день ждёт выполнения, день отдыха проходит сам`() {
        var state = ProgramCalendar.start(Mode.SMOOTH, monday)
        state = ProgramCalendar.complete(state, monday, Rating.OK)
        assertEquals(1, ProgramCalendar.sync(state, monday).day)

        // Вторник — день 2, отдых. В среду он уже прошёл сам, и наступил день 3.
        assertEquals(2, ProgramCalendar.sync(state, monday.plusDays(1)).day)
        val wednesday = ProgramCalendar.sync(state, monday.plusDays(2))
        assertEquals(3, wednesday.day)
        assertFalse(wednesday.isDone)

        // День 3 не выполнен — в пятницу программа всё ещё на нём.
        assertEquals(3, ProgramCalendar.sync(state, monday.plusDays(4)).day)
    }

    @Test
    fun `оценка меняет поправку`() {
        var state = ProgramCalendar.start(Mode.MEDIUM, monday)
        state = ProgramCalendar.complete(state, monday, Rating.EASY)
        assertEquals(1, state.adjustment)
        state = ProgramCalendar.sync(state, monday.plusDays(1))
        state = ProgramCalendar.complete(state, monday.plusDays(1), Rating.FAILED)
        assertEquals(-1, state.adjustment)
    }

    @Test
    fun `после перерыва 3 дня и больше ставится минус два один раз`() {
        var state = ProgramCalendar.start(Mode.MEDIUM, monday)
        state = ProgramCalendar.complete(state, monday, Rating.OK)
        val synced = ProgramCalendar.sync(state, monday.plusDays(4))
        assertEquals(2, synced.day)
        assertEquals(-2, synced.adjustment)
        assertEquals(-2, ProgramCalendar.sync(synced, monday.plusDays(6)).adjustment)
    }

    @Test
    fun `день 30 и следующий цикл`() {
        var state = ProgramState(Mode.FAST, day = 30, dayStartedOn = monday, adjustment = 3)
        state = ProgramCalendar.complete(state, monday)
        assertTrue(state.isCycleFinished)
        assertEquals(30, ProgramCalendar.sync(state, monday.plusDays(3)).day)

        val next = ProgramCalendar.nextCycle(state, monday.plusDays(1), Mode.MEDIUM)
        assertEquals(2, next.cycle)
        assertEquals(1, next.day)
        assertEquals(0, next.adjustment)
        assertEquals(Mode.MEDIUM, next.mode)
        assertEquals(DayKind.WORKOUT, next.kind)
        assertNull(next.doneOn)
    }
}

class MotivationTest {

    private val today = LocalDate.of(2026, 9, 28)

    @Test
    fun `серия считается до сегодня или вчера`() {
        val days = (0L..6L).map { today.minusDays(it) }.toSet()
        assertEquals(7, Streak.current(days, today))
        assertEquals(6, Streak.current(days - today, today))
        assertEquals(0, Streak.current(days, today.plusDays(3)))
        assertEquals(7, Streak.best(days + today.minusDays(20)))
    }

    @Test
    fun `уровни по группам мышц`() {
        val catalog = ExerciseCatalog.default
        val progress = mapOf(
            Pattern.PULL_V to PatternProgress(Pattern.PULL_V, "pullup_classic", 8, 1),
            Pattern.PULL_H to PatternProgress(Pattern.PULL_H, "australian", 8, 1),
        )
        assertEquals(mapOf(MuscleGroup.BACK to 4), Levels.byGroup(catalog, progress))
    }

    @Test
    fun `ачивки`() {
        val stats = Stats(workoutsDone = 12, bestStreak = 7, maxPullups = 1)
        assertEquals(
            listOf(Achievement.FIRST_WORKOUT, Achievement.FIRST_PULLUP, Achievement.STREAK_7, Achievement.TEN_WORKOUTS),
            Achievement.unlocked(stats),
        )
    }
}
