package com.nersiti.prokachka.ui.today

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.ViewModel
import com.nersiti.prokachka.core.Stretching
import com.nersiti.prokachka.data.ProgramRepository
import com.nersiti.prokachka.ui.components.AppTopBar
import com.nersiti.prokachka.ui.components.SectionCard
import com.nersiti.prokachka.ui.components.formatTime
import com.nersiti.prokachka.ui.components.vibrate
import dagger.hilt.android.lifecycle.HiltViewModel
import javax.inject.Inject
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

@HiltViewModel
class StretchViewModel @Inject constructor(private val repository: ProgramRepository) : ViewModel() {
    suspend fun finish(durationSec: Int) = repository.finishStretch(durationSec)
}

/** Растяжка дня отдыха: упражнения идут по таймеру одно за другим. */
@Composable
fun StretchScreen(onBack: () -> Unit, onDone: () -> Unit, viewModel: StretchViewModel = hiltViewModel()) {
    val routine = Stretching.routine
    var index by rememberSaveable { mutableIntStateOf(0) }
    var side by rememberSaveable { mutableIntStateOf(0) }
    var left by rememberSaveable { mutableIntStateOf(routine.first().seconds) }
    var running by rememberSaveable { mutableStateOf(false) }
    var elapsed by rememberSaveable { mutableIntStateOf(0) }
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val finished = index >= routine.size
    val finish: () -> Unit = remember {
        {
            scope.launch {
                viewModel.finish(elapsed)
                onDone()
            }
            Unit
        }
    }

    LaunchedEffect(running, index, side) {
        while (running && index < routine.size) {
            delay(1000)
            elapsed++
            left--
            if (left <= 0) {
                vibrate(context, 300)
                val stretch = routine[index]
                if (stretch.perSide && side == 0) {
                    side = 1
                } else {
                    side = 0
                    index++
                }
                left = routine.getOrNull(index)?.seconds ?: 0
            }
        }
    }

    Scaffold(topBar = { AppTopBar("Растяжка", onBack = onBack) }) { padding ->
        Column(
            Modifier
                .fillMaxSize()
                .padding(padding)
                .verticalScroll(rememberScrollState())
                .padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            LinearProgressIndicator(progress = { index / routine.size.toFloat() }, modifier = Modifier.fillMaxWidth())
            if (!finished) {
                val stretch = routine[index]
                SectionCard {
                    Text("${index + 1} из ${routine.size}", color = MaterialTheme.colorScheme.onSurfaceVariant)
                    Text(stretch.name, style = MaterialTheme.typography.titleLarge)
                    if (stretch.perSide) Text(if (side == 0) "Первая сторона" else "Вторая сторона")
                    Text(stretch.tip, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    Text(formatTime(left), style = MaterialTheme.typography.displaySmall)
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        Button(onClick = { running = !running }) { Text(if (running) "Пауза" else "Старт") }
                        OutlinedButton(onClick = {
                            side = 0
                            index++
                            left = routine.getOrNull(index)?.seconds ?: 0
                        }) { Text("Пропустить") }
                    }
                }
            } else {
                SectionCard {
                    Text("Готово! Серия продолжается 🔥", style = MaterialTheme.typography.titleLarge)
                }
            }
            Button(onClick = finish, modifier = Modifier.fillMaxWidth()) { Text("Завершить растяжку") }
        }
    }
}
