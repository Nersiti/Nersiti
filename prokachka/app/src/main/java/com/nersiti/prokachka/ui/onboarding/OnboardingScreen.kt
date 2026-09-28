package com.nersiti.prokachka.ui.onboarding

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Checkbox
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.ViewModel
import com.nersiti.prokachka.core.InjuryTag
import com.nersiti.prokachka.core.Mode
import com.nersiti.prokachka.data.ProgramRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import javax.inject.Inject
import kotlinx.coroutines.launch

@HiltViewModel
class OnboardingViewModel @Inject constructor(private val repository: ProgramRepository) : ViewModel() {
    suspend fun start(mode: Mode, excluded: Set<InjuryTag>) = repository.startProgram(mode, excluded)
}

@Composable
fun OnboardingScreen(onStarted: () -> Unit, viewModel: OnboardingViewModel = hiltViewModel()) {
    var step by rememberSaveable { mutableIntStateOf(0) }
    var mode by rememberSaveable { mutableStateOf(Mode.MEDIUM) }
    var noJumps by rememberSaveable { mutableStateOf(false) }
    var saveKnees by rememberSaveable { mutableStateOf(false) }
    val scope = rememberCoroutineScope()

    Column(
        Modifier
            .fillMaxSize()
            .safeDrawingPadding()
            .verticalScroll(rememberScrollState())
            .padding(20.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        when (step) {
            0 -> {
                Spacer(Modifier.height(24.dp))
                Text("Прокачка", style = MaterialTheme.typography.displaySmall, color = MaterialTheme.colorScheme.primary)
                Text("30 дней на массу. Каждый день программа подбирает упражнения под то, что у тебя есть под рукой.")
                InfoCard(
                    "Честно о результатах",
                    "За месяц сильнее всего растёт сила, мышцы растут умеренно. Поэтому рядом с фото мы " +
                        "показываем результаты тестов и еженедельные замеры — прогресс будет виден, даже когда " +
                        "в зеркале его ещё не заметно.",
                )
                InfoCard(
                    "Как это работает",
                    "День 1 — тест и первое фото. Дальше каждая тренировка чуть тяжелее прошлой, а в дни отдыха " +
                        "10 минут растяжки. Мышцы растут во время восстановления, поэтому отдых — часть программы.",
                )
                Button(onClick = { step = 1 }, Modifier.fillMaxWidth()) { Text("Дальше") }
            }

            1 -> {
                Text("Выбери режим", style = MaterialTheme.typography.headlineSmall)
                Mode.entries.forEach { item ->
                    ModeCard(item, selected = item == mode, onClick = { mode = item })
                }
                Button(onClick = { step = 2 }, Modifier.fillMaxWidth()) { Text("Дальше") }
                TextButton(onClick = { step = 0 }) { Text("Назад") }
            }

            else -> {
                Text("Есть ограничения?", style = MaterialTheme.typography.headlineSmall)
                Text(
                    "Отмеченные упражнения не попадут в тренировки. Изменить можно в настройках.",
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
                CheckRow(InjuryTag.JUMPS.title, noJumps) { noJumps = it }
                CheckRow("${InjuryTag.KNEES.title}: без выпадов и «пистолетов»", saveKnees) { saveKnees = it }
                InfoCard(
                    "Дальше — тест",
                    "Сделай фото и тест: максимум отжиманий, приседаний (до 50), подтягиваний и планку на время. " +
                        "По ним подберутся стартовые упражнения.",
                )
                Button(
                    onClick = {
                        val excluded = buildSet {
                            if (noJumps) add(InjuryTag.JUMPS)
                            if (saveKnees) add(InjuryTag.KNEES)
                        }
                        scope.launch {
                            viewModel.start(mode, excluded)
                            onStarted()
                        }
                    },
                    Modifier.fillMaxWidth(),
                ) { Text("Начать: фото и тест") }
                TextButton(onClick = { step = 1 }) { Text("Назад") }
            }
        }
    }
}

@Composable
private fun InfoCard(title: String, text: String) {
    Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceContainer)) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Text(title, style = MaterialTheme.typography.titleMedium)
            Text(text, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
    }
}

@Composable
private fun ModeCard(mode: Mode, selected: Boolean, onClick: () -> Unit) {
    val border = if (selected) BorderStroke(2.dp, MaterialTheme.colorScheme.primary) else null
    Card(
        modifier = Modifier.fillMaxWidth().clickable(onClick = onClick),
        border = border,
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceContainer),
    ) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Text("${mode.emoji} ${mode.title}", style = MaterialTheme.typography.titleLarge)
            Text(
                "${mode.workoutsPerWeek} тренировки в неделю · ~${mode.minutes} мин · ${describe(mode)}",
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            Text(
                "Неделя: ${mode.week.map { if (it == 'Т') "Т" else "о" }.joinToString(" ")} · отдых ${mode.restSec} с · " +
                    "+${"%.1f".format(mode.k * 100).removeSuffix(",0").removeSuffix(".0")}% в день",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
}

private fun describe(mode: Mode) = when (mode) {
    Mode.SMOOTH -> "всё тело"
    Mode.MEDIUM -> "верх / низ"
    Mode.FAST -> "жим / тяга / ноги / верх / низ"
}

@Composable
private fun CheckRow(text: String, checked: Boolean, onChange: (Boolean) -> Unit) {
    Row(
        Modifier.fillMaxWidth().clickable { onChange(!checked) },
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Checkbox(checked = checked, onCheckedChange = onChange)
        Text(text)
    }
}
