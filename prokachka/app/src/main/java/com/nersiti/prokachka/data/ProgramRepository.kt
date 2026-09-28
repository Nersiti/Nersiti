package com.nersiti.prokachka.data

import androidx.room.withTransaction
import com.nersiti.prokachka.core.Achievement
import com.nersiti.prokachka.core.DayKind
import com.nersiti.prokachka.core.ExerciseCatalog
import com.nersiti.prokachka.core.GeneratedWorkout
import com.nersiti.prokachka.core.GenerationRequest
import com.nersiti.prokachka.core.InjuryTag
import com.nersiti.prokachka.core.Inventory
import com.nersiti.prokachka.core.Levels
import com.nersiti.prokachka.core.MuscleGroup
import com.nersiti.prokachka.core.Mode
import com.nersiti.prokachka.core.Pattern
import com.nersiti.prokachka.core.PatternProgress
import com.nersiti.prokachka.core.ProgramCalendar
import com.nersiti.prokachka.core.ProgramState
import com.nersiti.prokachka.core.ProgressionEngine
import com.nersiti.prokachka.core.Rating
import com.nersiti.prokachka.core.Stats
import com.nersiti.prokachka.core.Streak
import com.nersiti.prokachka.core.TestResult
import com.nersiti.prokachka.core.WorkoutGenerator
import java.time.LocalDate
import javax.inject.Inject
import javax.inject.Singleton
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.map

/** Сделанный подход в журнале тренировки. */
data class DoneSet(val exerciseId: String, val setIndex: Int, val target: Int, val done: Int, val weightKg: Double?)

@Singleton
class ProgramRepository @Inject constructor(
    private val db: AppDatabase,
    val catalog: ExerciseCatalog,
    private val photos: PhotoStorage,
) {
    private val programDao = db.programDao()
    private val logDao = db.logDao()
    private val measureDao = db.measureDao()

    val generator = WorkoutGenerator(catalog)

    val state: Flow<ProgramState?> = programDao.observeState().map { it?.toDomain() }

    val workouts: Flow<List<WorkoutLogEntity>> = logDao.observeWorkouts()

    val tests: Flow<List<TestResultEntity>> = measureDao.observeTests()

    val measurements: Flow<List<MeasurementEntity>> = measureDao.observeMeasurements()

    val levels: Flow<Map<MuscleGroup, Int>> = programDao.observePatternProgress().map { rows ->
        Levels.byGroup(catalog, rows.associate { Pattern.valueOf(it.pattern) to it.toDomain() })
    }

    val streak: Flow<Int> = workouts.map { logs -> Streak.current(activeDays(logs), LocalDate.now()) }

    val achievements: Flow<List<Achievement>> = combine(workouts, levels, photos.photos) { _, _, _ ->
        Achievement.unlocked(stats())
    }

    /** Сдвигает программу к сегодняшнему дню и сохраняет. */
    suspend fun sync(today: LocalDate = LocalDate.now()): ProgramState? {
        val stored = programDao.state()?.toDomain() ?: return null
        val synced = ProgramCalendar.sync(stored, today)
        if (synced != stored) programDao.saveState(synced.toEntity())
        return synced
    }

    /** Онбординг: режим и ограничения. База считается после теста 1-го дня. */
    suspend fun startProgram(mode: Mode, excluded: Set<InjuryTag>, today: LocalDate = LocalDate.now()) {
        db.withTransaction {
            programDao.clearPatternProgress()
            programDao.saveState(ProgramCalendar.start(mode, today, excluded).toEntity())
        }
    }

    /** Тест 1-го или 30-го дня. После 1-го дня считается стартовая база. */
    suspend fun saveTest(test: TestResult, today: LocalDate = LocalDate.now()) {
        val state = sync(today) ?: return
        db.withTransaction {
            measureDao.insertTest(
                TestResultEntity(
                    cycle = state.cycle,
                    day = state.day,
                    date = today.toEpochDay(),
                    pushups = test.pushups,
                    squats = test.squats,
                    pullups = test.pullups,
                    plankSec = test.plankSec,
                ),
            )
            if (state.kind == DayKind.TEST) {
                val progress = ProgressionEngine(catalog, state.mode).calibrate(test, state.day, state.excluded)
                programDao.savePatternProgress(progress.values.map { it.toEntity() })
            }
            logDao.insertWorkout(
                WorkoutLogEntity(
                    date = today.toEpochDay(),
                    cycle = state.cycle,
                    day = state.day,
                    kind = state.kind.name,
                    title = if (state.kind == DayKind.TEST) "Тест: калибровка" else "Финальный тест",
                    rating = null,
                    durationSec = 0,
                ),
            )
            programDao.saveState(ProgramCalendar.complete(state, today).toEntity())
        }
    }

    suspend fun request(inventory: Inventory, today: LocalDate = LocalDate.now()): GenerationRequest {
        val state = checkNotNull(sync(today)) { "Программа не начата" }
        val last = logDao.lastWorkout()
        val recent = last?.let { log -> logDao.sets(log.id).map { it.exerciseId }.toSet() }.orEmpty()
        return GenerationRequest(
            mode = state.mode,
            day = state.day,
            cycle = state.cycle,
            adjustment = state.adjustment,
            progress = patternProgress(),
            weights = programDao.weightProgress().associate { it.exerciseId to it.toDomain() },
            inventory = inventory,
            excluded = state.excluded,
            recentExerciseIds = recent,
        )
    }

    suspend fun generate(inventory: Inventory): Pair<GenerationRequest, GeneratedWorkout> {
        val request = request(inventory)
        return request to generator.generate(request)
    }

    private suspend fun patternProgress(): Map<Pattern, PatternProgress> =
        programDao.patternProgress().associate { Pattern.valueOf(it.pattern) to it.toDomain() }

    /**
     * Сохраняет тренировку: журнал подходов, новый прогресс паттернов и весов, оценку.
     * Возвращает ачивки, которые открылись этой тренировкой.
     */
    suspend fun finishWorkout(
        generated: GeneratedWorkout,
        sets: List<DoneSet>,
        durationSec: Int,
        rating: Rating,
        today: LocalDate = LocalDate.now(),
    ): List<Achievement> {
        val before = Achievement.unlocked(stats()).toSet()
        val state = checkNotNull(sync(today))
        val usedIds = sets.map { it.exerciseId }.toSet()
        db.withTransaction {
            val workoutId = logDao.insertWorkout(
                WorkoutLogEntity(
                    date = today.toEpochDay(),
                    cycle = state.cycle,
                    day = state.day,
                    kind = DayKind.WORKOUT.name,
                    title = generated.workout.title,
                    rating = rating.name,
                    durationSec = durationSec,
                ),
            )
            logDao.insertSets(
                sets.map { SetLogEntity(0, workoutId, it.exerciseId, it.setIndex, it.target, it.done, it.weightKg) },
            )
            programDao.savePatternProgress(generated.progress.values.map { it.toEntity() })
            programDao.saveWeightProgress(
                generated.weights.values.filter { it.exerciseId in usedIds }.map { it.toEntity() },
            )
            programDao.saveState(ProgramCalendar.complete(state, today, rating).toEntity())
        }
        return Achievement.unlocked(stats()).filter { it !in before }
    }

    /** Растяжка в день отдыха засчитывается в серию. */
    suspend fun finishStretch(durationSec: Int, today: LocalDate = LocalDate.now()) {
        val state = checkNotNull(sync(today))
        db.withTransaction {
            logDao.insertWorkout(
                WorkoutLogEntity(
                    date = today.toEpochDay(),
                    cycle = state.cycle,
                    day = state.day,
                    kind = DayKind.STRETCH.name,
                    title = "Растяжка",
                    rating = null,
                    durationSec = durationSec,
                ),
            )
            programDao.saveState(ProgramCalendar.complete(state, today).toEntity())
        }
    }

    /** «Продолжить» после 30-го дня: база пересчитывается от финального теста. */
    suspend fun nextCycle(mode: Mode, today: LocalDate = LocalDate.now()) {
        val state = checkNotNull(sync(today))
        val final = measureDao.tests().lastOrNull { it.cycle == state.cycle } ?: return
        val next = ProgramCalendar.nextCycle(state, today, mode)
        val progress = ProgressionEngine(catalog, mode).calibrate(final.toDomain(), 1, next.excluded)
        db.withTransaction {
            programDao.clearPatternProgress()
            programDao.savePatternProgress(progress.values.map { it.toEntity() })
            programDao.saveWeightProgress(programDao.weightProgress().map { it.copy(startDay = 1) })
            programDao.saveState(next.toEntity())
        }
    }

    suspend fun updateExcluded(excluded: Set<InjuryTag>) {
        val state = programDao.state()?.toDomain() ?: return
        programDao.saveState(state.copy(excluded = excluded).toEntity())
    }

    /** «Начать заново»: программа сбрасывается, журнал, тесты и фото остаются. */
    suspend fun reset() {
        db.withTransaction {
            programDao.clearPatternProgress()
            db.backupDao().clearState()
        }
    }

    suspend fun addMeasurement(measurement: MeasurementEntity) = measureDao.insertMeasurement(measurement)

    suspend fun stats(): Stats {
        val logs = logDao.workouts()
        val pullupIds = listOf("chinup", "pullup_classic", "pullup_wide", "pullup_backpack")
        val testPullups = measureDao.tests().maxOfOrNull { it.pullups } ?: 0
        return Stats(
            workoutsDone = logs.count { it.kind == DayKind.WORKOUT.name },
            bestStreak = Streak.best(activeDays(logs)),
            maxPullups = maxOf(testPullups, logDao.maxDone(pullupIds) ?: 0),
            cyclesCompleted = logs.count { it.kind == DayKind.FINAL_TEST.name },
            maxGroupLevel = Levels.byGroup(catalog, patternProgress()).values.maxOrNull() ?: 0,
            photosTaken = db.photoDao().photos().size,
        )
    }

    private fun activeDays(logs: List<WorkoutLogEntity>): Set<LocalDate> =
        logs.map { LocalDate.ofEpochDay(it.date) }.toSet()
}
