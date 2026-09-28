package com.nersiti.prokachka.data

import com.nersiti.prokachka.core.Exercise
import com.nersiti.prokachka.core.GeneratedWorkout
import com.nersiti.prokachka.core.GenerationRequest
import javax.inject.Inject
import javax.inject.Singleton

/** Текущая тренировка между экранами «Инвентарь → Фото → Тренировка → Итог». */
@Singleton
class WorkoutSession @Inject constructor() {
    var request: GenerationRequest? = null
        private set
    var generated: GeneratedWorkout? = null
        private set
    val sets = mutableListOf<DoneSet>()
    var startedAt: Long = 0L
        private set

    fun start(request: GenerationRequest, generated: GeneratedWorkout) {
        this.request = request
        this.generated = generated
        sets.clear()
        startedAt = System.currentTimeMillis()
    }

    /** Кнопка «Заменить упражнение». */
    fun replace(index: Int, exercise: Exercise, repository: ProgramRepository) {
        val request = request ?: return
        val current = generated ?: return
        val planned = current.workout.exercises[index]
        val result = repository.generator.replace(request, planned, exercise)
        val exercises = current.workout.exercises.toMutableList().also { it[index] = result.planned }
        val weights = result.weight?.let { current.weights + (it.exerciseId to it) } ?: current.weights
        generated = current.copy(workout = current.workout.copy(exercises = exercises), weights = weights)
    }

    val durationSec: Int get() = ((System.currentTimeMillis() - startedAt) / 1000).toInt()

    fun clear() {
        request = null
        generated = null
        sets.clear()
    }
}
