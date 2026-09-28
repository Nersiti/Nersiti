package com.nersiti.prokachka.data

import androidx.room.withTransaction
import javax.inject.Inject
import javax.inject.Singleton
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json

/** Резервная копия журнала и прогресса. Фото в неё не входят — они остаются только на телефоне. */
@Serializable
data class Backup(
    val version: Int = 1,
    val state: ProgramStateEntity?,
    val patternProgress: List<PatternProgressEntity>,
    val weightProgress: List<WeightProgressEntity>,
    val workouts: List<WorkoutLogEntity>,
    val sets: List<SetLogEntity>,
    val tests: List<TestResultEntity>,
    val measurements: List<MeasurementEntity>,
)

@Singleton
class BackupManager @Inject constructor(private val db: AppDatabase) {

    private val json = Json {
        prettyPrint = true
        ignoreUnknownKeys = true
    }

    suspend fun export(): String {
        val backup = Backup(
            state = db.programDao().state(),
            patternProgress = db.programDao().patternProgress(),
            weightProgress = db.programDao().weightProgress(),
            workouts = db.logDao().workouts(),
            sets = db.logDao().allSets(),
            tests = db.measureDao().tests(),
            measurements = db.measureDao().measurements(),
        )
        return json.encodeToString(Backup.serializer(), backup)
    }

    suspend fun import(text: String) {
        val backup = json.decodeFromString(Backup.serializer(), text)
        val dao = db.backupDao()
        db.withTransaction {
            dao.clearSets()
            dao.clearWorkouts()
            dao.clearPatternProgress()
            dao.clearWeightProgress()
            dao.clearTests()
            dao.clearMeasurements()
            dao.clearState()
            backup.state?.let { db.programDao().saveState(it) }
            db.programDao().savePatternProgress(backup.patternProgress)
            db.programDao().saveWeightProgress(backup.weightProgress)
            dao.insertWorkouts(backup.workouts)
            db.logDao().insertSets(backup.sets)
            dao.insertTests(backup.tests)
            dao.insertMeasurements(backup.measurements)
        }
    }
}
