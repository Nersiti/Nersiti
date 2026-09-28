package com.nersiti.prokachka.ui.onboarding

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
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
import com.nersiti.prokachka.core.DayKind
import com.nersiti.prokachka.core.ProgressionEngine
import com.nersiti.prokachka.core.TestResult
import com.nersiti.prokachka.data.ProgramRepository
import com.nersiti.prokachka.ui.components.AppTopBar
import com.nersiti.prokachka.ui.components.NumberStepper
import com.nersiti.prokachka.ui.components.SectionCard
import com.nersiti.prokachka.ui.components.formatTime
import dagger.hilt.android.lifecycle.HiltViewModel
import javax.inject.Inject
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

@HiltViewModel
class TestViewModel @Inject constructor(private val repository: ProgramRepository) : ViewModel() {
    suspend fun isFinal(): Boolean = repository.sync()?.kind == DayKind.FINAL_TEST
    suspend fun save(result: TestResult) = repository.saveTest(result)
}

/** Тест 1-го дня (калибровка) и 30-го (финал): одинаковые упражнения на максимум. */
@Composable
fun TestScreen(onDone: () -> Unit, viewModel: TestViewModel = hiltViewModel()) {
    var final by rememberSaveable { mutableStateOf(false) }
    var pushups by rememberSaveable { mutableIntStateOf(0) }
    var squats by rememberSaveable { mutableIntStateOf(0) }
    var pullups by rememberSaveable { mutableIntStateOf(0) }
    var plank by rememberSaveable { mutableIntStateOf(0) }
    var running by rememberSaveable { mutableStateOf(false) }
    val scope = rememberCoroutineScope()

    LaunchedEffect(Unit) { final = viewModel.isFinal() }
    LaunchedEffect(running) {
        while (running) {
            delay(1000)
            plank++
        }
    }

    Scaffold(topBar = { AppTopBar(if (final) "Финальный тест" else "Тест: калибровка") }) { padding ->
        Column(
            Modifier
                .fillMaxSize()
                .padding(padding)
                .verticalScroll(rememberScrollState())
                .padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Text(
                "Делай каждое упражнение на максимум с чистой техникой. Отдыхай между ними 2–3 минуты.",
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            TestItem("Отжимания", "Классические, до отказа. Уровень груди и плеч.") {
                NumberStepper(pushups, { pushups = it })
            }
            TestItem("Приседания", "До ${ProgressionEngine.SQUAT_TEST_LIMIT}. Уровень ног.") {
                NumberStepper(squats, { squats = it }, max = ProgressionEngine.SQUAT_TEST_LIMIT)
            }
            TestItem("Подтягивания", "Нет турника или не получается — оставь 0, начнём с негативов.") {
                NumberStepper(pullups, { pullups = it })
            }
            TestItem("Планка", "На локтях, на время. Уровень пресса.") {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(formatTime(plank), style = MaterialTheme.typography.headlineMedium, modifier = Modifier.padding(end = 16.dp))
                    OutlinedButton(onClick = {
                        if (!running) plank = 0
                        running = !running
                    }) { Text(if (running) "Стоп" else "Старт") }
                }
                NumberStepper(plank, { plank = it }, step = 5, suffix = " с")
            }
            Button(
                onClick = {
                    running = false
                    scope.launch {
                        viewModel.save(TestResult(pushups, squats, pullups, plank))
                        onDone()
                    }
                },
                modifier = Modifier.fillMaxWidth(),
            ) { Text("Сохранить результаты") }
        }
    }
}

@Composable
private fun TestItem(title: String, hint: String, content: @Composable () -> Unit) {
    SectionCard {
        Text(title, style = MaterialTheme.typography.titleMedium)
        Text(hint, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        content()
    }
}
