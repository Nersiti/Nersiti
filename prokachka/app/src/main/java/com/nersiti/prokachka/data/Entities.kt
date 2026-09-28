package com.nersiti.prokachka.data

import androidx.room.Entity
import androidx.room.ForeignKey
import androidx.room.Index
import androidx.room.PrimaryKey
import kotlinx.serialization.Serializable

/** Состояние программы: одна строка с id = 1. */
@Serializable
@Entity(tableName = "program_state")
data class ProgramStateEntity(
    @PrimaryKey val id: Int = 1,
    val mode: String,
    val cycle: Int,
    val day: Int,
    val adjustment: Int,
    /** Даты хранятся как LocalDate.toEpochDay(). */
    val dayStartedOn: Long,
    val doneOn: Long?,
    val breakPenaltyDay: Int?,
    /** Ограничения через запятую: JUMPS, KNEES. */
    val excluded: String,
)

@Serializable
@Entity(tableName = "pattern_progress")
data class PatternProgressEntity(
    @PrimaryKey val pattern: String,
    val exerciseId: String,
    val base: Int,
    val startDay: Int,
)

@Serializable
@Entity(tableName = "weight_progress")
data class WeightProgressEntity(
    @PrimaryKey val exerciseId: String,
    val weightKg: Double,
    val startDay: Int,
)

@Serializable
@Entity(tableName = "workout_log")
data class WorkoutLogEntity(
    @PrimaryKey(autoGenerate = true) val id: Long = 0,
    val date: Long,
    val cycle: Int,
    val day: Int,
    /** DayKind: TEST, FINAL_TEST, WORKOUT, STRETCH. */
    val kind: String,
    val title: String,
    val rating: String?,
    val durationSec: Int,
)

@Serializable
@Entity(
    tableName = "set_log",
    foreignKeys = [
        ForeignKey(
            entity = WorkoutLogEntity::class,
            parentColumns = ["id"],
            childColumns = ["workoutId"],
            onDelete = ForeignKey.CASCADE,
        ),
    ],
    indices = [Index("workoutId"), Index("exerciseId")],
)
data class SetLogEntity(
    @PrimaryKey(autoGenerate = true) val id: Long = 0,
    val workoutId: Long,
    val exerciseId: String,
    val setIndex: Int,
    val target: Int,
    val done: Int,
    val weightKg: Double?,
)

@Serializable
@Entity(tableName = "photo", indices = [Index(value = ["cycle", "day", "angle"], unique = true)])
data class PhotoEntity(
    @PrimaryKey(autoGenerate = true) val id: Long = 0,
    val cycle: Int,
    val day: Int,
    /** FRONT, SIDE, BACK. */
    val angle: String,
    val path: String,
    val takenOn: Long,
)

@Serializable
@Entity(tableName = "test_result", indices = [Index(value = ["cycle", "day"], unique = true)])
data class TestResultEntity(
    @PrimaryKey(autoGenerate = true) val id: Long = 0,
    val cycle: Int,
    val day: Int,
    val date: Long,
    val pushups: Int,
    val squats: Int,
    val pullups: Int,
    val plankSec: Int,
)

@Serializable
@Entity(tableName = "measurement")
data class MeasurementEntity(
    @PrimaryKey(autoGenerate = true) val id: Long = 0,
    val date: Long,
    val weightKg: Double?,
    val chestCm: Double?,
    val waistCm: Double?,
    val armCm: Double?,
    val hipsCm: Double?,
)
