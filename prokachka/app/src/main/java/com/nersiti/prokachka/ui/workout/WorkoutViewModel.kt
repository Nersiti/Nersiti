package com.nersiti.prokachka.ui.workout

import android.content.Context
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.nersiti.prokachka.core.Achievement
import com.nersiti.prokachka.core.Exercise
import com.nersiti.prokachka.core.PlannedExercise
import com.nersiti.prokachka.core.Rating
import com.nersiti.prokachka.core.Workout
import com.nersiti.prokachka.core.WorkoutGenerator
import com.nersiti.prokachka.data.DoneSet
import com.nersiti.prokachka.data.ProgramRepository
import com.nersiti.prokachka.data.WorkoutSession
import com.nersiti.prokachka.ui.components.vibrate
import dagger.hilt.android.lifecycle.HiltViewModel
import dagger.hilt.android.qualifiers.ApplicationContext
import javax.inject.Inject
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

sealed interface Phase {
    data class Warmup(val secondsLeft: Int) : Phase

    /** Подход [set] (с нуля) упражнения [index]. */
    data class Working(val index: Int, val set: Int) : Phase

    data class Resting(val secondsLeft: Int, val next: Working) : Phase

    data class Cooldown(val secondsLeft: Int) : Phase

    data object Finished : Phase
}

data class WorkoutUi(
    val workout: Workout? = null,
    val phase: Phase = Phase.Warmup(WorkoutGenerator.WARMUP_MIN * 60),
    /** Секундомер для упражнений на время. */
    val holdLeft: Int? = null,
)

@HiltViewModel
class WorkoutViewModel @Inject constructor(
    @ApplicationContext private val context: Context,
    private val session: WorkoutSession,
    private val repository: ProgramRepository,
) : ViewModel() {

    private val _ui = MutableStateFlow(WorkoutUi(workout = session.generated?.workout))
    val ui: StateFlow<WorkoutUi> = _ui.asStateFlow()

    private var timer: Job? = null

    init {
        startTimer()
    }

    val current: PlannedExercise?
        get() = (ui.value.phase as? Phase.Working)?.let { ui.value.workout?.exercises?.getOrNull(it.index) }

    fun skipWarmup() = moveTo(firstWorking())

    fun skipRest() {
        val phase = ui.value.phase as? Phase.Resting ?: return
        moveTo(phase.next)
    }

    fun finishCooldown() = moveTo(Phase.Finished)

    /** Подход сделан: пишем в журнал, дальше отдых или следующее упражнение. */
    fun completeSet(done: Int) {
        val phase = ui.value.phase as? Phase.Working ?: return
        val workout = ui.value.workout ?: return
        val planned = workout.exercises[phase.index]
        session.sets += DoneSet(planned.exercise.id, phase.set, planned.target, done, planned.weightKg)

        val next = when {
            phase.set + 1 < planned.sets -> Phase.Working(phase.index, phase.set + 1)
            phase.index + 1 < workout.exercises.size -> Phase.Working(phase.index + 1, 0)
            else -> null
        }
        moveTo(if (next == null) Phase.Cooldown(WorkoutGenerator.COOLDOWN_MIN * 60) else Phase.Resting(workout.restSec, next))
    }

    /** Секундомер удержания для упражнений на время. */
    fun startHold() {
        val planned = current ?: return
        _ui.update { it.copy(holdLeft = planned.target) }
        timer?.cancel()
        timer = viewModelScope.launch {
            while ((ui.value.holdLeft ?: 0) > 0) {
                delay(1000)
                _ui.update { it.copy(holdLeft = (it.holdLeft ?: 1) - 1) }
            }
            vibrate(context, 500)
        }
    }

    fun alternatives(): List<Exercise> {
        val request = session.request ?: return emptyList()
        val planned = current ?: return emptyList()
        return repository.generator.alternatives(request, planned)
    }

    fun replace(exercise: Exercise) {
        val phase = ui.value.phase as? Phase.Working ?: return
        session.replace(phase.index, exercise, repository)
        _ui.update { it.copy(workout = session.generated?.workout, holdLeft = null) }
    }

    private fun firstWorking(): Phase =
        if (ui.value.workout?.exercises.isNullOrEmpty()) Phase.Cooldown(WorkoutGenerator.COOLDOWN_MIN * 60) else Phase.Working(0, 0)

    private fun moveTo(phase: Phase) {
        _ui.update { it.copy(phase = phase, holdLeft = null) }
        startTimer()
    }

    /** Обратный отсчёт разминки, отдыха и заминки. В конце отдыха — вибрация. */
    private fun startTimer() {
        timer?.cancel()
        timer = viewModelScope.launch {
            while (true) {
                delay(1000)
                val phase = ui.value.phase
                val next: Phase = when (phase) {
                    is Phase.Warmup -> if (phase.secondsLeft <= 1) firstWorking() else phase.copy(secondsLeft = phase.secondsLeft - 1)
                    is Phase.Resting -> if (phase.secondsLeft <= 1) {
                        vibrate(context, 600)
                        phase.next
                    } else {
                        phase.copy(secondsLeft = phase.secondsLeft - 1)
                    }
                    is Phase.Cooldown -> if (phase.secondsLeft <= 1) Phase.Finished else phase.copy(secondsLeft = phase.secondsLeft - 1)
                    else -> return@launch
                }
                _ui.update { it.copy(phase = next) }
            }
        }
    }
}

data class SummaryUi(
    val workout: Workout? = null,
    val sets: List<DoneSet> = emptyList(),
    val durationSec: Int = 0,
    val saving: Boolean = false,
    val unlocked: List<Achievement>? = null,
)

@HiltViewModel
class SummaryViewModel @Inject constructor(
    private val session: WorkoutSession,
    private val repository: ProgramRepository,
) : ViewModel() {

    private val _ui = MutableStateFlow(
        SummaryUi(session.generated?.workout, session.sets.toList(), session.durationSec),
    )
    val ui: StateFlow<SummaryUi> = _ui.asStateFlow()

    fun rate(rating: Rating) {
        val generated = session.generated ?: return
        if (ui.value.saving) return
        _ui.update { it.copy(saving = true) }
        viewModelScope.launch {
            val unlocked = repository.finishWorkout(generated, session.sets.toList(), ui.value.durationSec, rating)
            session.clear()
            _ui.update { it.copy(unlocked = unlocked) }
        }
    }
}
