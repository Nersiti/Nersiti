package com.nersiti.prokachka.ui.inventory

import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AssistChip
import androidx.compose.material3.Button
import androidx.compose.material3.FilterChip
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.ViewModel
import com.nersiti.prokachka.core.Equipment
import com.nersiti.prokachka.core.Inventory
import com.nersiti.prokachka.data.ProgramRepository
import com.nersiti.prokachka.data.SettingsRepository
import com.nersiti.prokachka.data.WorkoutSession
import com.nersiti.prokachka.ui.components.AppTopBar
import com.nersiti.prokachka.ui.components.SectionCard
import dagger.hilt.android.lifecycle.HiltViewModel
import javax.inject.Inject
import kotlinx.coroutines.launch

@HiltViewModel
class InventoryViewModel @Inject constructor(
    private val repository: ProgramRepository,
    private val settings: SettingsRepository,
    private val session: WorkoutSession,
) : ViewModel() {

    /** Вчерашний выбор подставляется сам. */
    suspend fun lastInventory(): Inventory = settings.current().lastInventory ?: Inventory.NOTHING

    suspend fun prepare(inventory: Inventory) {
        settings.setInventory(inventory)
        val (request, generated) = repository.generate(inventory)
        session.start(request, generated)
    }
}

private val presets = listOf(
    "Дома" to Inventory.HOME,
    "Площадка" to Inventory.PLAYGROUND,
    "Зал" to Inventory.GYM,
    "Ничего" to Inventory.NOTHING,
)

@Composable
fun InventoryScreen(onBack: () -> Unit, onReady: () -> Unit, viewModel: InventoryViewModel = hiltViewModel()) {
    var items by rememberSaveable { mutableStateOf(setOf<Equipment>()) }
    var dumbbells by rememberSaveable { mutableStateOf("") }
    var kettlebells by rememberSaveable { mutableStateOf("") }
    var loaded by rememberSaveable { mutableStateOf(false) }
    var busy by rememberSaveable { mutableStateOf(false) }
    val scope = rememberCoroutineScope()

    fun load(inventory: Inventory) {
        items = inventory.items
        dumbbells = inventory.dumbbellsKg.joinToString(", ") { formatWeight(it) }
        kettlebells = inventory.kettlebellsKg.joinToString(", ") { formatWeight(it) }
    }

    LaunchedEffect(Unit) {
        if (!loaded) {
            load(viewModel.lastInventory())
            loaded = true
        }
    }

    Scaffold(topBar = { AppTopBar("Что есть сегодня?", onBack = onBack) }) { padding ->
        Column(
            Modifier
                .fillMaxSize()
                .padding(padding)
                .verticalScroll(rememberScrollState())
                .padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                presets.forEach { (title, preset) ->
                    AssistChip(onClick = { load(preset) }, label = { Text(title) })
                }
            }
            SectionCard {
                Text("Инвентарь", style = MaterialTheme.typography.titleMedium)
                FilterChip(
                    selected = items.isEmpty(),
                    onClick = { items = emptySet() },
                    label = { Text("Ничего") },
                )
                Equipment.entries.forEach { equipment ->
                    FilterChip(
                        selected = equipment in items,
                        onClick = { items = if (equipment in items) items - equipment else items + equipment },
                        label = { Text(equipment.title) },
                    )
                }
            }
            if (Equipment.DUMBBELLS in items) {
                WeightsField("Гантели, кг", dumbbells) { dumbbells = it }
            }
            if (Equipment.KETTLEBELL in items) {
                WeightsField("Гири, кг", kettlebells) { kettlebells = it }
            }
            Text(
                "Без инвентаря тоже можно: у каждого движения есть вариант с весом тела.",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            Button(
                enabled = !busy,
                onClick = {
                    busy = true
                    scope.launch {
                        val inventory = Inventory(
                            items = items,
                            dumbbellsKg = if (Equipment.DUMBBELLS in items) parseWeights(dumbbells) else emptyList(),
                            kettlebellsKg = if (Equipment.KETTLEBELL in items) parseWeights(kettlebells) else emptyList(),
                        )
                        viewModel.prepare(inventory)
                        busy = false
                        onReady()
                    }
                },
                modifier = Modifier.fillMaxWidth(),
            ) { Text("Дальше: фото") }
        }
    }
}

@Composable
private fun WeightsField(label: String, value: String, onChange: (String) -> Unit) {
    OutlinedTextField(
        value = value,
        onValueChange = onChange,
        label = { Text(label) },
        supportingText = { Text("Через запятую: 4, 6, 8. Без весов упражнения с ними не подберутся.") },
        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal),
        modifier = Modifier.fillMaxWidth(),
    )
}

internal fun parseWeights(text: String): List<Double> =
    text.split(',', ';', ' ')
        .mapNotNull { it.trim().replace(',', '.').toDoubleOrNull() }
        .filter { it > 0 }
        .distinct()
        .sorted()

internal fun formatWeight(kg: Double): String =
    if (kg % 1.0 == 0.0) kg.toInt().toString() else kg.toString()
