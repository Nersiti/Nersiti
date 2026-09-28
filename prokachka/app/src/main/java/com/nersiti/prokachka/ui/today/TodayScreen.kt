package com.nersiti.prokachka.ui.today

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.Checkbox
import androidx.compose.material3.FilterChip
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.ViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewModelScope
import com.nersiti.prokachka.core.DailyChecklist
import com.nersiti.prokachka.core.DayKind
import com.nersiti.prokachka.core.Inventory
import com.nersiti.prokachka.core.Mode
import com.nersiti.prokachka.core.MuscleGroup
import com.nersiti.prokachka.core.ProgramState
import com.nersiti.prokachka.core.Schedule
import com.nersiti.prokachka.core.Workout
import com.nersiti.prokachka.data.ChecklistItem
import com.nersiti.prokachka.data.ProgramRepository
import com.nersiti.prokachka.data.Settings
import com.nersiti.prokachka.data.SettingsRepository
import com.nersiti.prokachka.data.TestResultEntity
import com.nersiti.prokachka.ui.components.SectionCard
import com.nersiti.prokachka.ui.components.formatTime
import dagger.hilt.android.lifecycle.HiltViewModel
import java.time.LocalDate
import javax.inject.Inject
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch

data class TodayUi(
    val state: ProgramState? = null,
    val streak: Int = 0,
    val levels: Map<MuscleGroup, Int> = emptyMap(),
    val settings: Settings = Settings(),
    val preview: Workout? = null,
    val tests: List<TestResultEntity> = emptyList(),
)

@HiltViewModel
class TodayViewModel @Inject constructor(
    private val repository: ProgramRepository,
    private val settingsRepository: SettingsRepository,
) : ViewModel() {

    private val preview = MutableStateFlow<Workout?>(null)

    val ui = combine(
        repository.state,
        repository.streak,
        repository.levels,
        settingsRepository.settings,
        combine(preview, repository.tests) { workout, tests -> workout to tests },
    ) { state, streak, levels, settings, (workout, tests) ->
        TodayUi(state, streak, levels, settings, workout, tests)
    }.stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), TodayUi())

    fun refresh() = viewModelScope.launch {
        val state = repository.sync() ?: return@launch
        preview.value = if (state.kind == DayKind.WORKOUT && !state.isDone) {
            val inventory = settingsRepository.current().lastInventory ?: Inventory.NOTHING
            repository.generate(inventory).second.workout
        } else {
            null
        }
    }

    fun toggle(item: ChecklistItem) = viewModelScope.launch {
        settingsRepository.toggleChecklist(item, LocalDate.now())
    }

    fun nextCycle(mode: Mode) = viewModelScope.launch {
        repository.nextCycle(mode)
        refresh()
    }
}

@Composable
fun TodayScreen(
    onStartTest: () -> Unit,
    onStartWorkout: () -> Unit,
    onStartStretch: () -> Unit,
    viewModel: TodayViewModel = hiltViewModel(),
) {
    val ui by viewModel.ui.collectAsStateWithLifecycle()
    LaunchedEffect(Unit) { viewModel.refresh() }
    val state = ui.state ?: return

    Column(
        Modifier
            .fillMaxSize()
            .statusBarsPadding()
            .verticalScroll(rememberScrollState())
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        val cycle = if (state.cycle > 1) "Цикл ${state.cycle} · " else ""
        Text("${cycle}День ${state.day}/${Schedule.DAYS}", style = MaterialTheme.typography.headlineMedium)
        LinearProgressIndicator(
            progress = { state.day / Schedule.DAYS.toFloat() },
            modifier = Modifier.fillMaxWidth(),
        )
        Text(
            "🔥 Серия: ${ui.streak} ${daysWord(ui.streak)} · ${state.mode.emoji} ${state.mode.title}",
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )

        when {
            state.isCycleFinished -> CycleFinished(state, ui.tests, viewModel::nextCycle)
            state.isDone -> DoneCard(state)
            else -> TodayCard(state, ui.preview, onStartTest, onStartWorkout, onStartStretch)
        }

        Checklist(ui.settings, viewModel::toggle)

        if (ui.levels.isNotEmpty()) {
            SectionCard {
                Text("Уровни прокачки", style = MaterialTheme.typography.titleMedium)
                ui.levels.forEach { (group, level) ->
                    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                        Text(group.title)
                        Text("ур. $level", fontWeight = FontWeight.Bold, color = MaterialTheme.colorScheme.primary)
                    }
                }
            }
        }
    }
}

@Composable
private fun TodayCard(
    state: ProgramState,
    preview: Workout?,
    onStartTest: () -> Unit,
    onStartWorkout: () -> Unit,
    onStartStretch: () -> Unit,
) {
    SectionCard {
        when (state.kind) {
            DayKind.TEST -> {
                Text("Тест и первое фото", style = MaterialTheme.typography.titleLarge)
                Text("Максимум отжиманий, приседаний, подтягиваний и планка на время. По ним подберутся стартовые упражнения.")
                Button(onClick = onStartTest, Modifier.fillMaxWidth()) { Text("Начать") }
            }

            DayKind.FINAL_TEST -> {
                Text("Финальный тест", style = MaterialTheme.typography.titleLarge)
                Text("Те же упражнения, что в первый день, и фото «после». Посмотрим, сколько ты прокачался!")
                Button(onClick = onStartTest, Modifier.fillMaxWidth()) { Text("Начать") }
            }

            DayKind.STRETCH -> {
                Text("День отдыха", style = MaterialTheme.typography.titleLarge)
                Text("Мышцы растут во время восстановления. 10 минут растяжки засчитываются в серию.")
                Button(onClick = onStartStretch, Modifier.fillMaxWidth()) { Text("Растяжка · 10 мин") }
            }

            DayKind.WORKOUT -> {
                val template = Schedule.template(state.mode, state.day)
                Text("Тренировка «${template.title}»", style = MaterialTheme.typography.titleLarge)
                if (preview != null) {
                    Text(
                        "~${preview.estimatedMinutes} мин · ${preview.exercises.size} упражнений · отдых ${formatTime(preview.restSec)}" +
                            if (preview.light) " · облегчённый день" else "",
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                    preview.exercises.forEach { Text("• ${it.exercise.name} — ${it.summary}") }
                    Text(
                        "Упражнения уточнятся под инвентарь на следующем шаге.",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
                Button(onClick = onStartWorkout, Modifier.fillMaxWidth()) { Text("Начать тренировку") }
            }
        }
    }
}

@Composable
private fun DoneCard(state: ProgramState) {
    SectionCard {
        Text("✅ День выполнен", style = MaterialTheme.typography.titleLarge)
        val next = state.day + 1
        val text = when {
            next > Schedule.DAYS -> "Цикл завершён!"
            next == Schedule.DAYS -> "Завтра финальный тест."
            Schedule.isTraining(state.mode, next) ->
                "Завтра тренировка «${Schedule.template(state.mode, next).title}»."
            else -> "Завтра отдых и растяжка."
        }
        Text("$text До встречи!")
    }
}

@Composable
private fun CycleFinished(state: ProgramState, tests: List<TestResultEntity>, onContinue: (Mode) -> Unit) {
    val cycleTests = tests.filter { it.cycle == state.cycle }
    val before = cycleTests.firstOrNull()
    val after = cycleTests.lastOrNull()?.takeIf { it.day == Schedule.DAYS }
    var mode by rememberSaveable { mutableStateOf(state.mode) }
    SectionCard {
        Text("🏆 30/30 — цикл пройден!", style = MaterialTheme.typography.titleLarge)
        if (before != null && after != null) {
            Text("Было → стало", style = MaterialTheme.typography.titleMedium)
            CompareRow("Отжимания", before.pushups, after.pushups)
            CompareRow("Приседания", before.squats, after.squats)
            CompareRow("Подтягивания", before.pullups, after.pullups)
            CompareRow("Планка, с", before.plankSec, after.plankSec)
        }
        Text("Фото «до/после» — во вкладке «Прогресс».", color = MaterialTheme.colorScheme.onSurfaceVariant)
        Text("Режим следующего цикла", style = MaterialTheme.typography.titleMedium)
        Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Mode.entries.forEach { item ->
                FilterChip(selected = mode == item, onClick = { mode = item }, label = { Text("${item.emoji} ${item.title}") })
            }
        }
        Text(
            "База пересчитается от финального теста, первые 2 дня будут облегчёнными.",
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        Button(onClick = { onContinue(mode) }, Modifier.fillMaxWidth()) { Text("Продолжить: цикл ${state.cycle + 1}") }
    }
}

@Composable
private fun CompareRow(title: String, before: Int, after: Int) {
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
        Text(title)
        val diff = after - before
        val sign = if (diff > 0) "+" else ""
        Text("$before → $after ($sign$diff)", fontWeight = FontWeight.Bold)
    }
}

@Composable
private fun Checklist(settings: Settings, onToggle: (ChecklistItem) -> Unit) {
    val done = settings.checklistFor(LocalDate.now())
    SectionCard {
        Text("Восстановление", style = MaterialTheme.typography.titleMedium)
        ChecklistItem.entries.forEach { item ->
            val label = when (item) {
                ChecklistItem.SLEEP -> DailyChecklist.SLEEP
                ChecklistItem.PROTEIN -> DailyChecklist.protein(settings.bodyWeightKg?.toDouble())
                ChecklistItem.WATER -> DailyChecklist.WATER
            }
            Row(
                Modifier.fillMaxWidth().clickable { onToggle(item) },
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Checkbox(checked = item in done, onCheckedChange = { onToggle(item) })
                Text(label)
            }
        }
    }
}

private fun daysWord(n: Int): String {
    val mod100 = n % 100
    val mod10 = n % 10
    return when {
        mod100 in 11..14 -> "дней"
        mod10 == 1 -> "день"
        mod10 in 2..4 -> "дня"
        else -> "дней"
    }
}
