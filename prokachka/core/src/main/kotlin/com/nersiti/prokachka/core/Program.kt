package com.nersiti.prokachka.core

import java.time.LocalDate
import java.time.temporal.ChronoUnit

enum class DayKind {
    /** Калибровочный тест 1-го дня первого цикла. */
    TEST,

    /** Финальный тест 30-го дня. */
    FINAL_TEST,
    WORKOUT,

    /** День отдыха: 10 минут растяжки, засчитываются в серию. */
    STRETCH,
}

/** Расписание 30-дневного цикла. */
object Schedule {
    const val DAYS = 30

    /** Первые дни второго и следующих циклов облегчены. */
    const val LIGHT_DAYS = 2

    fun kind(mode: Mode, day: Int, cycle: Int = 1): DayKind = when {
        day == 1 && cycle == 1 -> DayKind.TEST
        day == DAYS -> DayKind.FINAL_TEST
        isTraining(mode, day) -> DayKind.WORKOUT
        else -> DayKind.STRETCH
    }

    fun isTraining(mode: Mode, day: Int): Boolean =
        day == 1 || day == DAYS || mode.week[(day - 1) % 7] == 'Т'

    /** Шаблон тренировки: по порядку тренировочного дня внутри недели. */
    fun template(mode: Mode, day: Int): DayTemplate {
        val position = (day - 1) % 7
        val index = mode.week.take(position).count { it == 'Т' }
        return mode.templates[index.coerceAtMost(mode.templates.lastIndex)]
    }

    /** Сколько раз этот шаблон уже встречался до [day]: по нему чередуются слоты. */
    fun occurrence(mode: Mode, day: Int): Int {
        val template = template(mode, day)
        return (1 until day).count { mode.week[(it - 1) % 7] == 'Т' && template(mode, it) == template }
    }

    fun sets(mode: Mode, day: Int, cycle: Int = 1): Int {
        val extra = if (mode.extraSetFromDay15 && day >= 15) 1 else 0
        val light = if (isLight(day, cycle)) 1 else 0
        return mode.baseSets + extra - light
    }

    fun isLight(day: Int, cycle: Int): Boolean = cycle > 1 && day <= LIGHT_DAYS

    /** Дни с фото сбоку и со спины, в остальные дни — только фронт. */
    val fullPhotoDays = setOf(1, 10, 20, 30)
}

/**
 * Состояние программы. Тренировочный день засчитывается после выполнения,
 * день отдыха проходит сам с календарём.
 */
data class ProgramState(
    val mode: Mode,
    val cycle: Int = 1,
    val day: Int = 1,
    /** Суммарная поправка от оценок и перерывов. */
    val adjustment: Int = 0,
    /** Дата, с которой начался текущий день программы. */
    val dayStartedOn: LocalDate,
    /** Когда текущий день завершён, или null. */
    val doneOn: LocalDate? = null,
    /** День, за перерыв перед которым уже поставлена поправка −2. */
    val breakPenaltyDay: Int? = null,
    val excluded: Set<InjuryTag> = emptySet(),
) {
    val isDone: Boolean get() = doneOn != null
    val kind: DayKind get() = Schedule.kind(mode, day, cycle)
    val isCycleFinished: Boolean get() = day == Schedule.DAYS && isDone
}

object ProgramCalendar {

    fun start(mode: Mode, today: LocalDate, excluded: Set<InjuryTag> = emptySet()): ProgramState =
        ProgramState(mode = mode, dayStartedOn = today, excluded = excluded)

    /** Сдвигает программу к сегодняшней дате. */
    fun sync(state: ProgramState, today: LocalDate): ProgramState {
        var s = state
        while (true) {
            val doneOn = s.doneOn
            s = when {
                doneOn != null && s.day < Schedule.DAYS && today.isAfter(doneOn) ->
                    s.copy(day = s.day + 1, doneOn = null, dayStartedOn = doneOn.plusDays(1))

                doneOn == null && s.kind == DayKind.STRETCH && today.isAfter(s.dayStartedOn) ->
                    s.copy(doneOn = s.dayStartedOn)

                else -> break
            }
        }
        val missed = ChronoUnit.DAYS.between(s.dayStartedOn, today)
        if (!s.isDone && s.kind != DayKind.STRETCH && missed >= ProgressionEngine.BREAK_DAYS && s.breakPenaltyDay != s.day) {
            s = s.copy(adjustment = s.adjustment + ProgressionEngine.BREAK_PENALTY, breakPenaltyDay = s.day)
        }
        return s
    }

    /** Отмечает текущий день выполненным; оценка добавляет поправку. */
    fun complete(state: ProgramState, today: LocalDate, rating: Rating? = null): ProgramState {
        val synced = sync(state, today)
        if (synced.isDone) return synced
        return synced.copy(
            doneOn = today,
            adjustment = synced.adjustment + (rating?.adjustment ?: 0),
        )
    }

    /** Кнопка «Продолжить» после 30-го дня: новый цикл, режим можно сменить. */
    fun nextCycle(state: ProgramState, today: LocalDate, mode: Mode = state.mode): ProgramState =
        ProgramState(
            mode = mode,
            cycle = state.cycle + 1,
            day = 1,
            adjustment = 0,
            dayStartedOn = today,
            excluded = state.excluded,
        )
}
