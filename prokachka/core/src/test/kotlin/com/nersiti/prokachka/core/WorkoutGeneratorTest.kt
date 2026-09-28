package com.nersiti.prokachka.core

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class WorkoutGeneratorTest {

    private val catalog = ExerciseCatalog.default
    private val generator = WorkoutGenerator(catalog)
    private val test = TestResult(pushups = 20, squats = 30, pullups = 0, plankSec = 60)

    private fun request(
        mode: Mode,
        day: Int,
        inventory: Inventory = Inventory.NOTHING,
        excluded: Set<InjuryTag> = emptySet(),
        test: TestResult = this.test,
        cycle: Int = 1,
    ) = GenerationRequest(
        mode = mode,
        day = day,
        cycle = cycle,
        progress = ProgressionEngine(catalog, mode).calibrate(test, excluded = excluded),
        inventory = inventory,
        excluded = excluded,
    )

    @Test
    // В плане у гантелей 3 × 9. Здесь 3 × 10: для веса k удвоен, иначе вес за цикл не растёт.
    fun `день 11, Средний, турник и гантели 8 кг — пример из плана`() {
        val inventory = Inventory(setOf(Equipment.BAR, Equipment.DUMBBELLS), dumbbellsKg = listOf(8.0))
        val workout = generator.generate(request(Mode.MEDIUM, 11, inventory)).workout

        assertEquals(DayTemplate.UPPER, workout.template)
        assertEquals(75, workout.restSec)
        val plan = workout.exercises.map { Triple(it.exercise.id, it.sets, it.target) }
        assertEquals(
            listOf(
                Triple("pushup_classic", 3, 14),
                Triple("pullup_negative", 3, 5),
                Triple("db_shoulder_press", 3, 10),
                Triple("db_row", 3, 10),
                Triple("db_hammer", 3, 10),
            ),
            plan,
        )
        assertTrue(workout.exercises.filter { it.exercise.type == ExerciseType.WEIGHT }.all { it.weightKg == 8.0 })
        assertEquals("3 × 10 на руку · 8 кг", workout.exercises[3].summary)
        assertTrue(workout.estimatedMinutes in 30..50, "Длительность ${workout.estimatedMinutes} мин")
    }

    @Test
    fun `тест в первый день и финальный в тридцатый`() {
        for (mode in Mode.entries) {
            assertEquals(DayKind.TEST, generator.generate(request(mode, 1)).workout.kind)
            assertEquals(DayKind.FINAL_TEST, generator.generate(request(mode, 30)).workout.kind)
        }
        assertEquals(DayKind.WORKOUT, generator.generate(request(Mode.MEDIUM, 1, cycle = 2)).workout.kind)
    }

    @Test
    fun `в дни отдыха растяжка`() {
        val workout = generator.generate(request(Mode.SMOOTH, 2)).workout
        assertEquals(DayKind.STRETCH, workout.kind)
        assertEquals(Stretching.MINUTES, workout.estimatedMinutes)
    }

    @Test
    fun `без инвентаря тренировка собирается в любой день любого режима`() {
        for (mode in Mode.entries) {
            for (day in 2 until Schedule.DAYS) {
                val workout = generator.generate(request(mode, day)).workout
                if (workout.kind == DayKind.STRETCH) continue
                val expected = Schedule.template(mode, day).slots.size
                assertEquals(expected, workout.exercises.size, "$mode, день $day")
                assertTrue(workout.exercises.all { it.exercise.requires.isEmpty() }, "$mode, день $day")
                assertTrue(workout.exercises.all { it.target > 0 && it.target <= it.exercise.limit }, "$mode, день $day")
                assertEquals(workout.exercises.size, workout.exercises.map { it.exercise.id }.toSet().size)
            }
        }
    }

    @Test
    fun `длительность близка к заявленной для режима`() {
        val days = mapOf(Mode.SMOOTH to 3, Mode.MEDIUM to 4, Mode.FAST to 5)
        for ((mode, day) in days) {
            val minutes = generator.generate(request(mode, day, Inventory.GYM)).workout.estimatedMinutes
            assertTrue(minutes in mode.minutes - 12..mode.minutes + 15, "$mode: $minutes мин")
        }
    }

    @Test
    fun `с 15-го дня дополнительный подход в Среднем и Быстром`() {
        val before = generator.generate(request(Mode.MEDIUM, 12)).workout
        val after = generator.generate(request(Mode.MEDIUM, 15)).workout
        assertEquals(3, before.exercises.first { !it.compensated }.sets)
        assertEquals(4, after.exercises.first { !it.compensated }.sets)

        val smooth = generator.generate(request(Mode.SMOOTH, 15)).workout
        assertEquals(3, smooth.exercises.first { !it.compensated }.sets)
    }

    @Test
    fun `в Быстром последний подход на максимум`() {
        val workout = generator.generate(request(Mode.FAST, 2)).workout
        assertTrue(workout.exercises.all { it.lastSetToFailure })
        assertFalse(generator.generate(request(Mode.MEDIUM, 2)).workout.exercises.any { it.lastSetToFailure })
    }

    @Test
    fun `без турника спина тренируется без потери уровня`() {
        val home = generator.generate(request(Mode.MEDIUM, 11, Inventory.NOTHING)).workout
        val pull = home.exercises.first { it.pattern == Pattern.PULL_V }
        assertTrue(pull.exercise.requires.isEmpty())
        assertTrue(pull.compensated)
        assertTrue(pull.slowNegative)
        assertEquals(4, pull.sets)
    }

    @Test
    fun `при больных коленях нет выпадов и пистолетов`() {
        val excluded = setOf(InjuryTag.KNEES, InjuryTag.JUMPS)
        for (day in listOf(2, 4, 5, 9, 16, 23)) {
            val workout = generator.generate(
                request(Mode.FAST, day, Inventory.GYM, excluded, TestResult(40, 50, 10, 120)),
            ).workout
            assertTrue(workout.exercises.none { ex -> ex.exercise.avoid.any { it in excluded } }, "день $day")
        }
    }

    @Test
    fun `вчерашнее упражнение уходит в конец очереди`() {
        val base = request(Mode.SMOOTH, 3)
        val first = generator.generate(base).workout
        val push = first.exercises.first { it.pattern == Pattern.PUSH_H }.exercise.id
        val next = generator.generate(base.copy(day = 5, recentExerciseIds = first.exercises.map { it.exercise.id }.toSet()))
            .workout.exercises.first { it.pattern == Pattern.PUSH_H }.exercise.id
        assertTrue(push != next, "Ожидалась ротация, но оба раза $push")
    }

    @Test
    fun `вторая неделя Плавного чередует вертикальную и горизонтальную тягу`() {
        val backPatterns = listOf(3, 5, 8, 10).map { day ->
            generator.generate(request(Mode.SMOOTH, day)).workout.exercises[1].pattern
        }
        assertEquals(listOf(Pattern.PULL_H, Pattern.PULL_V, Pattern.PULL_H, Pattern.PULL_V), backPatterns)
    }

    @Test
    fun `первые дни нового цикла облегчены`() {
        val normal = generator.generate(request(Mode.MEDIUM, 4)).workout
        val light = generator.generate(request(Mode.MEDIUM, 2, cycle = 2)).workout
        assertTrue(light.light)
        assertEquals(2, light.exercises.first { !it.compensated }.sets)
        assertFalse(normal.light)
    }
}
