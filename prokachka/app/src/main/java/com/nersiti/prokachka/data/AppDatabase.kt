package com.nersiti.prokachka.data

import android.content.Context
import androidx.room.Dao
import androidx.room.Database
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query
import androidx.room.Room
import androidx.room.RoomDatabase
import androidx.room.Upsert
import kotlinx.coroutines.flow.Flow

@Dao
interface ProgramDao {
    @Query("SELECT * FROM program_state WHERE id = 1")
    fun observeState(): Flow<ProgramStateEntity?>

    @Query("SELECT * FROM program_state WHERE id = 1")
    suspend fun state(): ProgramStateEntity?

    @Upsert
    suspend fun saveState(state: ProgramStateEntity)

    @Query("SELECT * FROM pattern_progress")
    suspend fun patternProgress(): List<PatternProgressEntity>

    @Query("SELECT * FROM pattern_progress")
    fun observePatternProgress(): Flow<List<PatternProgressEntity>>

    @Upsert
    suspend fun savePatternProgress(items: List<PatternProgressEntity>)

    @Query("DELETE FROM pattern_progress")
    suspend fun clearPatternProgress()

    @Query("SELECT * FROM weight_progress")
    suspend fun weightProgress(): List<WeightProgressEntity>

    @Upsert
    suspend fun saveWeightProgress(items: List<WeightProgressEntity>)
}

@Dao
interface LogDao {
    @Insert
    suspend fun insertWorkout(log: WorkoutLogEntity): Long

    @Insert
    suspend fun insertSets(sets: List<SetLogEntity>)

    @Query("SELECT * FROM workout_log ORDER BY date DESC, id DESC")
    fun observeWorkouts(): Flow<List<WorkoutLogEntity>>

    @Query("SELECT * FROM workout_log ORDER BY date DESC, id DESC")
    suspend fun workouts(): List<WorkoutLogEntity>

    @Query("SELECT * FROM workout_log WHERE kind = 'WORKOUT' ORDER BY id DESC LIMIT 1")
    suspend fun lastWorkout(): WorkoutLogEntity?

    @Query("SELECT * FROM set_log WHERE workoutId = :workoutId ORDER BY id")
    suspend fun sets(workoutId: Long): List<SetLogEntity>

    @Query("SELECT * FROM set_log")
    suspend fun allSets(): List<SetLogEntity>

    @Query("SELECT MAX(done) FROM set_log WHERE exerciseId IN (:ids)")
    suspend fun maxDone(ids: List<String>): Int?
}

@Dao
interface PhotoDao {
    @Query("SELECT * FROM photo ORDER BY cycle, day, angle")
    fun observePhotos(): Flow<List<PhotoEntity>>

    @Query("SELECT * FROM photo ORDER BY cycle, day, angle")
    suspend fun photos(): List<PhotoEntity>

    @Query("SELECT * FROM photo WHERE angle = :angle ORDER BY cycle DESC, day DESC LIMIT 1")
    suspend fun lastPhoto(angle: String): PhotoEntity?

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun insert(photo: PhotoEntity)
}

@Dao
interface MeasureDao {
    @Query("SELECT * FROM test_result ORDER BY cycle, day")
    fun observeTests(): Flow<List<TestResultEntity>>

    @Query("SELECT * FROM test_result ORDER BY cycle, day")
    suspend fun tests(): List<TestResultEntity>

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun insertTest(result: TestResultEntity)

    @Query("SELECT * FROM measurement ORDER BY date")
    fun observeMeasurements(): Flow<List<MeasurementEntity>>

    @Query("SELECT * FROM measurement ORDER BY date")
    suspend fun measurements(): List<MeasurementEntity>

    @Insert
    suspend fun insertMeasurement(measurement: MeasurementEntity)
}

@Dao
interface BackupDao {
    @Query("DELETE FROM set_log")
    suspend fun clearSets()

    @Query("DELETE FROM workout_log")
    suspend fun clearWorkouts()

    @Query("DELETE FROM pattern_progress")
    suspend fun clearPatternProgress()

    @Query("DELETE FROM weight_progress")
    suspend fun clearWeightProgress()

    @Query("DELETE FROM test_result")
    suspend fun clearTests()

    @Query("DELETE FROM measurement")
    suspend fun clearMeasurements()

    @Query("DELETE FROM program_state")
    suspend fun clearState()

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun insertWorkouts(items: List<WorkoutLogEntity>)

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun insertTests(items: List<TestResultEntity>)

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun insertMeasurements(items: List<MeasurementEntity>)
}

@Database(
    entities = [
        ProgramStateEntity::class,
        PatternProgressEntity::class,
        WeightProgressEntity::class,
        WorkoutLogEntity::class,
        SetLogEntity::class,
        PhotoEntity::class,
        TestResultEntity::class,
        MeasurementEntity::class,
    ],
    version = 1,
    exportSchema = false,
)
abstract class AppDatabase : RoomDatabase() {
    abstract fun programDao(): ProgramDao
    abstract fun logDao(): LogDao
    abstract fun photoDao(): PhotoDao
    abstract fun measureDao(): MeasureDao
    abstract fun backupDao(): BackupDao

    companion object {
        @Volatile
        private var instance: AppDatabase? = null

        /** Общий экземпляр: нужен и Hilt, и WorkManager. */
        fun get(context: Context): AppDatabase =
            instance ?: synchronized(this) {
                instance ?: Room.databaseBuilder(context.applicationContext, AppDatabase::class.java, "prokachka.db")
                    .build()
                    .also { instance = it }
            }
    }
}
