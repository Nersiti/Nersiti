package com.nersiti.prokachka.core

import kotlinx.serialization.json.Json

class ExerciseCatalog(val exercises: List<Exercise>) {

    private val byId = exercises.associateBy { it.id }
    private val byPattern = exercises.groupBy { it.pattern }

    init {
        require(byId.size == exercises.size) { "В базе упражнений есть повторяющиеся id" }
    }

    operator fun get(id: String): Exercise =
        byId[id] ?: throw IllegalArgumentException("Нет упражнения с id=$id")

    fun find(id: String): Exercise? = byId[id]

    fun forPattern(pattern: Pattern): List<Exercise> = byPattern[pattern].orEmpty()

    /** Основная лестница паттерна, от лёгкого к сложному. */
    fun ladder(pattern: Pattern, excluded: Set<InjuryTag> = emptySet()): List<Exercise> =
        forPattern(pattern)
            .filter { it.ladder && it.avoid.none(excluded::contains) }
            .sortedBy { it.difficulty }

    /** Следующая ступень после [exercise] или null, если выше некуда. */
    fun nextOnLadder(exercise: Exercise, excluded: Set<InjuryTag> = emptySet()): Exercise? =
        ladder(exercise.pattern, excluded).firstOrNull { it.difficulty > exercise.difficulty }

    /** Номер ступени, начиная с 1: так считается «уровень прокачки». */
    fun ladderLevel(exercise: Exercise): Int =
        ladder(exercise.pattern).indexOfFirst { it.difficulty >= exercise.difficulty }
            .let { if (it < 0) ladder(exercise.pattern).size else it + 1 }

    companion object {
        private val json = Json { ignoreUnknownKeys = true }

        fun parse(text: String): ExerciseCatalog = ExerciseCatalog(json.decodeFromString(text))

        /** База из ресурса exercises.json внутри модуля. */
        val default: ExerciseCatalog by lazy {
            val stream = ExerciseCatalog::class.java.getResourceAsStream("/exercises.json")
                ?: error("Не найден exercises.json")
            parse(stream.bufferedReader(Charsets.UTF_8).use { it.readText() })
        }
    }
}
