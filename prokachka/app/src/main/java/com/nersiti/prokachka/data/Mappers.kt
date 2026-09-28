package com.nersiti.prokachka.data

import com.nersiti.prokachka.core.InjuryTag
import com.nersiti.prokachka.core.Mode
import com.nersiti.prokachka.core.Pattern
import com.nersiti.prokachka.core.PatternProgress
import com.nersiti.prokachka.core.ProgramState
import com.nersiti.prokachka.core.TestResult
import com.nersiti.prokachka.core.WeightProgress
import java.time.LocalDate

fun ProgramStateEntity.toDomain() = ProgramState(
    mode = Mode.valueOf(mode),
    cycle = cycle,
    day = day,
    adjustment = adjustment,
    dayStartedOn = LocalDate.ofEpochDay(dayStartedOn),
    doneOn = doneOn?.let(LocalDate::ofEpochDay),
    breakPenaltyDay = breakPenaltyDay,
    excluded = excluded.split(',').filter { it.isNotBlank() }.map(InjuryTag::valueOf).toSet(),
)

fun ProgramState.toEntity() = ProgramStateEntity(
    mode = mode.name,
    cycle = cycle,
    day = day,
    adjustment = adjustment,
    dayStartedOn = dayStartedOn.toEpochDay(),
    doneOn = doneOn?.toEpochDay(),
    breakPenaltyDay = breakPenaltyDay,
    excluded = excluded.joinToString(",") { it.name },
)

fun PatternProgressEntity.toDomain() = PatternProgress(Pattern.valueOf(pattern), exerciseId, base, startDay)

fun PatternProgress.toEntity() = PatternProgressEntity(pattern.name, exerciseId, base, startDay)

fun WeightProgressEntity.toDomain() = WeightProgress(exerciseId, weightKg, startDay)

fun WeightProgress.toEntity() = WeightProgressEntity(exerciseId, weightKg, startDay)

fun TestResultEntity.toDomain() = TestResult(pushups, squats, pullups, plankSec)
