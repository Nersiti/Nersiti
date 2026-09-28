package com.nersiti.prokachka.ui.workout

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.SwapHoriz
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.nersiti.prokachka.core.Exercise
import com.nersiti.prokachka.core.PlannedExercise
import com.nersiti.prokachka.core.Rating
import com.nersiti.prokachka.core.Workout
import com.nersiti.prokachka.ui.components.AppTopBar
import com.nersiti.prokachka.ui.components.NumberStepper
import com.nersiti.prokachka.ui.components.SectionCard
import com.nersiti.prokachka.ui.components.formatTime

@Composable
fun WorkoutScreen(onExit: () -> Unit, onFinished: () -> Unit, viewModel: WorkoutViewModel = hiltViewModel()) {
    val ui by viewModel.ui.collectAsStateWithLifecycle()
    var confirmExit by remember { mutableStateOf(false) }
    var replacing by remember { mutableStateOf<List<Exercise>?>(null) }
    val workout = ui.workout

    BackHandler { confirmExit = true }
    LaunchedEffect(ui.phase) { if (ui.phase is Phase.Finished) onFinished() }

    Scaffold(topBar = { AppTopBar(workout?.title ?: "Тренировка", onBack = { confirmExit = true }) }) { padding ->
        Column(
            Modifier
                .fillMaxSize()
                .padding(padding)
                .verticalScroll(rememberScrollState())
                .padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            if (workout == null) {
                Text("Тренировка не найдена. Начни её заново с экрана «Сегодня».")
                Button(onClick = onExit) { Text("На главную") }
                return@Column
            }
            Progress(workout, ui.phase)
            when (val phase = ui.phase) {
                is Phase.Warmup -> TimerCard(
                    title = "Разминка",
                    text = "Суставная гимнастика, прыжки на месте или бег, 10 лёгких приседаний и отжиманий.",
                    seconds = phase.secondsLeft,
                    action = "Пропустить",
                    onAction = viewModel::skipWarmup,
                )

                is Phase.Working -> ExerciseCard(
                    planned = workout.exercises[phase.index],
                    set = phase.set,
                    holdLeft = ui.holdLeft,
                    onStartHold = viewModel::startHold,
                    onDone = viewModel::completeSet,
                    onReplace = { replacing = viewModel.alternatives() },
                )

                is Phase.Resting -> {
                    val next = workout.exercises[phase.next.index]
                    TimerCard(
                        title = "Отдых",
                        text = "Дальше: ${next.exercise.name}, подход ${phase.next.set + 1} из ${next.sets}",
                        seconds = phase.secondsLeft,
                        action = "Хватит отдыхать",
                        onAction = viewModel::skipRest,
                    )
                }

                is Phase.Cooldown -> TimerCard(
                    title = "Заминка",
                    text = "Спокойная ходьба и растяжка мышц, которые работали сегодня.",
                    seconds = phase.secondsLeft,
                    action = "Завершить",
                    onAction = viewModel::finishCooldown,
                )

                Phase.Finished -> Unit
            }
            Plan(workout, ui.phase)
        }
    }

    if (confirmExit) {
        AlertDialog(
            onDismissRequest = { confirmExit = false },
            title = { Text("Прервать тренировку?") },
            text = { Text("Сделанные подходы не сохранятся, день не засчитается.") },
            confirmButton = { TextButton(onClick = onExit) { Text("Прервать") } },
            dismissButton = { TextButton(onClick = { confirmExit = false }) { Text("Продолжить") } },
        )
    }

    replacing?.let { options ->
        AlertDialog(
            onDismissRequest = { replacing = null },
            title = { Text("Заменить упражнение") },
            text = {
                Column(Modifier.verticalScroll(rememberScrollState())) {
                    if (options.isEmpty()) Text("Под сегодняшний инвентарь замен нет.")
                    options.forEach { exercise ->
                        Text(
                            exercise.name,
                            modifier = Modifier
                                .fillMaxWidth()
                                .clickable {
                                    viewModel.replace(exercise)
                                    replacing = null
                                }
                                .padding(vertical = 12.dp),
                        )
                        HorizontalDivider()
                    }
                }
            },
            confirmButton = { TextButton(onClick = { replacing = null }) { Text("Отмена") } },
        )
    }
}

@Composable
private fun Progress(workout: Workout, phase: Phase) {
    val total = workout.exercises.sumOf { it.sets }.coerceAtLeast(1)
    val done = when (phase) {
        is Phase.Warmup -> 0
        is Phase.Working -> workout.exercises.take(phase.index).sumOf { it.sets } + phase.set
        is Phase.Resting -> workout.exercises.take(phase.next.index).sumOf { it.sets } + phase.next.set
        else -> total
    }
    LinearProgressIndicator(progress = { done / total.toFloat() }, modifier = Modifier.fillMaxWidth())
}

@Composable
private fun TimerCard(title: String, text: String, seconds: Int, action: String, onAction: () -> Unit) {
    SectionCard {
        Text(title, style = MaterialTheme.typography.titleLarge)
        Text(text, color = MaterialTheme.colorScheme.onSurfaceVariant)
        Text(formatTime(seconds), style = MaterialTheme.typography.displaySmall)
        OutlinedButton(onClick = onAction) { Text(action) }
    }
}

@Composable
private fun ExerciseCard(
    planned: PlannedExercise,
    set: Int,
    holdLeft: Int?,
    onStartHold: () -> Unit,
    onDone: (Int) -> Unit,
    onReplace: () -> Unit,
) {
    var done by remember(planned, set) { mutableIntStateOf(planned.target) }
    SectionCard {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(planned.exercise.name, style = MaterialTheme.typography.titleLarge, modifier = Modifier.weight(1f))
            TextButton(onClick = onReplace) {
                Icon(Icons.Default.SwapHoriz, contentDescription = null)
                Text("Заменить")
            }
        }
        Text("Подход ${set + 1} из ${planned.sets} · цель ${planned.summary}", fontWeight = FontWeight.SemiBold)
        val notes = buildList {
            planned.exercise.tempo?.let { add("Темп: $it") }
            if (planned.slowNegative) add("Медленный негатив: 3 с вниз")
            if (planned.compensated) add("Вариант легче твоего уровня, поэтому +1 подход")
            if (planned.lastSetToFailure && set == planned.sets - 1) add("Последний подход — на максимум!")
        }
        notes.forEach { Text("• $it", color = MaterialTheme.colorScheme.primary) }
        Text(planned.exercise.tip, color = MaterialTheme.colorScheme.onSurfaceVariant)

        if (planned.isTime) {
            if (holdLeft != null) {
                Text(formatTime(holdLeft), style = MaterialTheme.typography.displaySmall)
            } else {
                OutlinedButton(onClick = onStartHold) { Text("Старт удержания ${planned.target} с") }
            }
        }
        Text(if (planned.isTime) "Удержал, секунд:" else "Сделал повторов:")
        NumberStepper(done, { done = it }, step = if (planned.isTime) 5 else 1)
        Button(onClick = { onDone(done) }, Modifier.fillMaxWidth()) { Text("Подход выполнен") }
    }
}

@Composable
private fun Plan(workout: Workout, phase: Phase) {
    val active = when (phase) {
        is Phase.Working -> phase.index
        is Phase.Resting -> phase.next.index
        else -> -1
    }
    SectionCard {
        Text("План на сегодня · отдых ${formatTime(workout.restSec)}", style = MaterialTheme.typography.titleMedium)
        workout.exercises.forEachIndexed { i, planned ->
            Text(
                "${i + 1}. ${planned.exercise.name} — ${planned.summary}",
                fontWeight = if (i == active) FontWeight.Bold else FontWeight.Normal,
                color = if (i == active) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.onSurface,
            )
        }
    }
}

@Composable
fun SummaryScreen(onDone: () -> Unit, viewModel: SummaryViewModel = hiltViewModel()) {
    val ui by viewModel.ui.collectAsStateWithLifecycle()
    BackHandler(enabled = ui.unlocked == null) { }

    Scaffold(topBar = { AppTopBar("Итог") }) { padding ->
        Column(
            Modifier
                .fillMaxSize()
                .padding(padding)
                .verticalScroll(rememberScrollState())
                .padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            val workout = ui.workout
            if (workout == null) {
                Text("Тренировка уже сохранена.")
                Button(onClick = onDone) { Text("На главную") }
                return@Column
            }
            SectionCard {
                Text("💪 Тренировка «${workout.title}» готова", style = MaterialTheme.typography.titleLarge)
                Text("Время: ${formatTime(ui.durationSec)} · подходов: ${ui.sets.size}")
                workout.exercises.forEach { planned ->
                    val done = ui.sets.filter { it.exerciseId == planned.exercise.id }.map { it.done }
                    if (done.isNotEmpty()) Text("• ${planned.exercise.name}: ${done.joinToString(" / ")}")
                }
            }
            Text("Как прошло?", style = MaterialTheme.typography.titleMedium)
            Text(
                "Оценка двигает нагрузку: «Легко» — следующая тренировка тяжелее, «Не смог» — легче.",
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            Rating.entries.forEach { rating ->
                OutlinedButton(
                    onClick = { viewModel.rate(rating) },
                    enabled = !ui.saving,
                    modifier = Modifier.fillMaxWidth(),
                ) { Text(rating.title) }
            }
        }
    }

    ui.unlocked?.let { unlocked ->
        if (unlocked.isEmpty()) {
            LaunchedEffect(Unit) { onDone() }
        } else {
            AlertDialog(
                onDismissRequest = onDone,
                title = { Text("🏅 Новая ачивка!") },
                text = {
                    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        unlocked.forEach { Text("${it.title} — ${it.description}") }
                    }
                },
                confirmButton = { TextButton(onClick = onDone) { Text("Круто!") } },
            )
        }
    }
}
