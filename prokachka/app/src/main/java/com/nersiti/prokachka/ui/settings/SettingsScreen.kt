package com.nersiti.prokachka.ui.settings

import android.Manifest
import android.content.Context
import android.os.Build
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.FilterChip
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.ViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewModelScope
import com.nersiti.prokachka.core.InjuryTag
import com.nersiti.prokachka.core.ProgramState
import com.nersiti.prokachka.data.BackupManager
import com.nersiti.prokachka.data.ProgramRepository
import com.nersiti.prokachka.data.Settings
import com.nersiti.prokachka.data.SettingsRepository
import com.nersiti.prokachka.data.ThemeMode
import com.nersiti.prokachka.ui.components.NumberStepper
import com.nersiti.prokachka.ui.components.SectionCard
import com.nersiti.prokachka.work.Reminders
import dagger.hilt.android.lifecycle.HiltViewModel
import dagger.hilt.android.qualifiers.ApplicationContext
import javax.inject.Inject
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch

@HiltViewModel
class SettingsViewModel @Inject constructor(
    @ApplicationContext private val context: Context,
    private val settings: SettingsRepository,
    private val repository: ProgramRepository,
    private val backup: BackupManager,
) : ViewModel() {

    val ui = combine(settings.settings, repository.state) { prefs, state -> prefs to state }
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), Settings() to null)

    fun setReminders(enabled: Boolean, minutes: Int) = viewModelScope.launch {
        settings.setReminders(enabled, minutes)
        Reminders.schedule(context, enabled, minutes)
    }

    fun setLock(enabled: Boolean) = viewModelScope.launch { settings.setLock(enabled) }

    fun setTheme(theme: ThemeMode) = viewModelScope.launch { settings.setTheme(theme) }

    fun setBodyWeight(kg: Float?) = viewModelScope.launch { settings.setBodyWeight(kg) }

    fun setExcluded(excluded: Set<InjuryTag>) = viewModelScope.launch { repository.updateExcluded(excluded) }

    suspend fun exportBackup(): String = backup.export()

    suspend fun importBackup(text: String) = backup.import(text)

    suspend fun reset() = repository.reset()
}

@Composable
fun SettingsScreen(onRestarted: () -> Unit, viewModel: SettingsViewModel = hiltViewModel()) {
    val pair by viewModel.ui.collectAsStateWithLifecycle()
    val (settings, state) = pair
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var message by remember { mutableStateOf<String?>(null) }
    var confirmReset by remember { mutableStateOf(false) }

    val notifications = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { }
    val exporter = rememberLauncherForActivityResult(ActivityResultContracts.CreateDocument("application/json")) { uri ->
        if (uri == null) return@rememberLauncherForActivityResult
        scope.launch {
            val text = viewModel.exportBackup()
            context.contentResolver.openOutputStream(uri)?.use { it.write(text.toByteArray()) }
            message = "Резервная копия сохранена. Фото в неё не входят."
        }
    }
    val importer = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocument()) { uri ->
        if (uri == null) return@rememberLauncherForActivityResult
        scope.launch {
            message = runCatching {
                val text = context.contentResolver.openInputStream(uri)?.use { it.readBytes().decodeToString() }.orEmpty()
                viewModel.importBackup(text)
                "Данные восстановлены."
            }.getOrElse { "Не удалось прочитать файл: ${it.message}" }
        }
    }

    Column(
        Modifier
            .fillMaxSize()
            .statusBarsPadding()
            .verticalScroll(rememberScrollState())
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Text("Настройки", style = MaterialTheme.typography.headlineMedium)
        message?.let { Text(it, color = MaterialTheme.colorScheme.primary) }

        state?.let { ProgramCard(it) }

        SectionCard {
            SwitchRow("Напоминания", settings.remindersEnabled) { enabled ->
                if (enabled && Build.VERSION.SDK_INT >= 33) notifications.launch(Manifest.permission.POST_NOTIFICATIONS)
                viewModel.setReminders(enabled, settings.reminderMinutes)
            }
            if (settings.remindersEnabled) {
                Text("Время: %02d:%02d".format(settings.reminderMinutes / 60, settings.reminderMinutes % 60))
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text("Часы", Modifier.padding(end = 8.dp))
                    NumberStepper(settings.reminderMinutes / 60, { h ->
                        viewModel.setReminders(true, h * 60 + settings.reminderMinutes % 60)
                    }, max = 23)
                }
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text("Минуты", Modifier.padding(end = 8.dp))
                    NumberStepper(settings.reminderMinutes % 60, { m ->
                        viewModel.setReminders(true, settings.reminderMinutes / 60 * 60 + m)
                    }, step = 15, max = 45)
                }
            }
        }

        SectionCard {
            SwitchRow("Замок на фото (отпечаток или PIN)", settings.lockPhotos, viewModel::setLock)
            Text("Тема", style = MaterialTheme.typography.titleSmall)
            Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                ThemeMode.entries.forEach { theme ->
                    FilterChip(selected = settings.theme == theme, onClick = { viewModel.setTheme(theme) }, label = { Text(theme.title) })
                }
            }
        }

        SectionCard {
            Text("Вес тела", style = MaterialTheme.typography.titleSmall)
            var weight by remember(settings.bodyWeightKg) { mutableStateOf(settings.bodyWeightKg?.toString().orEmpty()) }
            OutlinedTextField(
                value = weight,
                onValueChange = {
                    weight = it
                    viewModel.setBodyWeight(it.replace(',', '.').toFloatOrNull())
                },
                label = { Text("кг — для нормы белка") },
                singleLine = true,
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal),
                modifier = Modifier.fillMaxWidth(),
            )
        }

        state?.let { program ->
            SectionCard {
                Text("Ограничения", style = MaterialTheme.typography.titleSmall)
                InjuryTag.entries.forEach { tag ->
                    SwitchRow(tag.title, tag in program.excluded) { on ->
                        viewModel.setExcluded(if (on) program.excluded + tag else program.excluded - tag)
                    }
                }
            }
        }

        SectionCard {
            Text("Резервная копия", style = MaterialTheme.typography.titleSmall)
            Text(
                "Журнал, тесты, замеры и прогресс в файле JSON. Фото в копию не входят.",
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlinedButton(onClick = { exporter.launch("prokachka-backup.json") }) { Text("Сохранить") }
                OutlinedButton(onClick = { importer.launch(arrayOf("application/json", "text/*")) }) { Text("Восстановить") }
            }
        }

        TextButton(onClick = { confirmReset = true }) {
            Text("Начать программу заново", color = MaterialTheme.colorScheme.error)
        }
    }

    if (confirmReset) {
        AlertDialog(
            onDismissRequest = { confirmReset = false },
            title = { Text("Начать заново?") },
            text = { Text("Текущий цикл сбросится. Журнал, тесты и фото сохранятся.") },
            confirmButton = {
                TextButton(onClick = {
                    confirmReset = false
                    scope.launch {
                        viewModel.reset()
                        onRestarted()
                    }
                }) { Text("Сбросить") }
            },
            dismissButton = { TextButton(onClick = { confirmReset = false }) { Text("Отмена") } },
        )
    }
}

@Composable
private fun ProgramCard(state: ProgramState) {
    SectionCard {
        Text("Программа", style = MaterialTheme.typography.titleSmall)
        Text("${state.mode.emoji} ${state.mode.title} · цикл ${state.cycle} · день ${state.day}")
        Text(
            "Режим можно сменить после 30-го дня, при запуске следующего цикла.",
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
    }
}

@Composable
private fun SwitchRow(title: String, checked: Boolean, onChange: (Boolean) -> Unit) {
    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
        Text(title, Modifier.weight(1f))
        Switch(checked = checked, onCheckedChange = onChange)
    }
}
