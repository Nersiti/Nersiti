package com.nersiti.prokachka.ui.progress

import android.content.Context
import android.content.ContextWrapper
import androidx.biometric.BiometricManager
import androidx.biometric.BiometricManager.Authenticators.BIOMETRIC_WEAK
import androidx.biometric.BiometricManager.Authenticators.DEVICE_CREDENTIAL
import androidx.biometric.BiometricPrompt
import androidx.compose.foundation.background
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilterChip
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.PrimaryTabRow
import androidx.compose.material3.Slider
import androidx.compose.material3.Tab
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.drawWithContent
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.drawscope.clipRect
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.core.content.ContextCompat
import androidx.fragment.app.FragmentActivity
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.ViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewModelScope
import coil.compose.AsyncImage
import com.nersiti.prokachka.core.Achievement
import com.nersiti.prokachka.core.DayKind
import com.nersiti.prokachka.core.MuscleGroup
import com.nersiti.prokachka.core.ProgramState
import com.nersiti.prokachka.core.Schedule
import com.nersiti.prokachka.data.MeasurementEntity
import com.nersiti.prokachka.data.PhotoAngle
import com.nersiti.prokachka.data.PhotoEntity
import com.nersiti.prokachka.data.PhotoStorage
import com.nersiti.prokachka.data.ProgramRepository
import com.nersiti.prokachka.data.SettingsRepository
import com.nersiti.prokachka.data.TestResultEntity
import com.nersiti.prokachka.data.WorkoutLogEntity
import com.nersiti.prokachka.ui.components.LineChart
import com.nersiti.prokachka.ui.components.SectionCard
import dagger.hilt.android.lifecycle.HiltViewModel
import java.io.File
import java.time.LocalDate
import javax.inject.Inject
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch

data class ProgressUi(
    val state: ProgramState? = null,
    val photos: List<PhotoEntity> = emptyList(),
    val tests: List<TestResultEntity> = emptyList(),
    val measurements: List<MeasurementEntity> = emptyList(),
    val workouts: List<WorkoutLogEntity> = emptyList(),
    val levels: Map<MuscleGroup, Int> = emptyMap(),
    val achievements: List<Achievement> = emptyList(),
    val lockPhotos: Boolean = true,
)

@HiltViewModel
class ProgressViewModel @Inject constructor(
    private val repository: ProgramRepository,
    photos: PhotoStorage,
    settings: SettingsRepository,
) : ViewModel() {

    val ui = combine(
        combine(repository.state, photos.photos, repository.tests) { a, b, c -> Triple(a, b, c) },
        combine(repository.measurements, repository.workouts, repository.levels) { a, b, c -> Triple(a, b, c) },
        repository.achievements,
        settings.settings,
    ) { (state, photoList, tests), (measurements, workouts, levels), achievements, prefs ->
        ProgressUi(state, photoList, tests, measurements, workouts, levels, achievements, prefs.lockPhotos)
    }.stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), ProgressUi())

    fun addMeasurement(weight: Double?, chest: Double?, waist: Double?, arm: Double?, hips: Double?) =
        viewModelScope.launch {
            repository.addMeasurement(
                MeasurementEntity(
                    date = LocalDate.now().toEpochDay(),
                    weightKg = weight,
                    chestCm = chest,
                    waistCm = waist,
                    armCm = arm,
                    hipsCm = hips,
                ),
            )
        }
}

private val tabTitles = listOf("Фото", "Графики", "Календарь", "Ачивки")

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ProgressScreen(viewModel: ProgressViewModel = hiltViewModel()) {
    val ui by viewModel.ui.collectAsStateWithLifecycle()
    var tab by rememberSaveable { mutableIntStateOf(0) }

    Column(Modifier.fillMaxSize().statusBarsPadding()) {
        PrimaryTabRow(selectedTabIndex = tab) {
            tabTitles.forEachIndexed { index, title ->
                Tab(selected = tab == index, onClick = { tab = index }, text = { Text(title) })
            }
        }
        Column(
            Modifier
                .fillMaxSize()
                .verticalScroll(rememberScrollState())
                .padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            when (tab) {
                0 -> PhotosTab(ui)
                1 -> ChartsTab(ui, viewModel)
                2 -> CalendarTab(ui)
                else -> AchievementsTab(ui)
            }
        }
    }
}

// ---------- Фото ----------

@Composable
private fun PhotosTab(ui: ProgressUi) {
    val context = LocalContext.current
    var unlocked by rememberSaveable { mutableStateOf(false) }
    var note by remember { mutableStateOf<String?>(null) }

    if (ui.lockPhotos && !unlocked) {
        SectionCard {
            Text("🔒 Фото под замком", style = MaterialTheme.typography.titleMedium)
            Text("Раздел открывается отпечатком или PIN-кодом телефона.")
            Button(onClick = {
                unlock(context, onSuccess = { unlocked = true }, onUnavailable = {
                    unlocked = true
                    note = "На телефоне не настроена блокировка экрана, поэтому замок не работает."
                })
            }) { Text("Открыть") }
        }
        return
    }
    note?.let { Text(it, color = MaterialTheme.colorScheme.error) }

    var angle by rememberSaveable { mutableStateOf(PhotoAngle.FRONT) }
    val photos = ui.photos.filter { it.angle == angle.name }
    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        PhotoAngle.entries.forEach {
            FilterChip(selected = angle == it, onClick = { angle = it }, label = { Text(it.title) })
        }
    }
    if (photos.isEmpty()) {
        Text("Фото пока нет. Они появятся после первого дня.", color = MaterialTheme.colorScheme.onSurfaceVariant)
        return
    }

    BeforeAfter(photos)
    Timelapse(photos)

    Text("Все снимки", style = MaterialTheme.typography.titleMedium)
    photos.chunked(3).forEach { row ->
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            row.forEach { photo ->
                Column(Modifier.weight(1f)) {
                    PhotoImage(photo, Modifier.fillMaxWidth().aspectRatio(3f / 4f).clip(RoundedCornerShape(8.dp)))
                    Text(label(photo), style = MaterialTheme.typography.labelSmall)
                }
            }
            repeat(3 - row.size) { Box(Modifier.weight(1f)) }
        }
    }
}

@Composable
private fun BeforeAfter(photos: List<PhotoEntity>) {
    val first = photos.first()
    var selected by remember(photos) { mutableStateOf(photos.last()) }
    var split by remember { mutableFloatStateOf(0.5f) }
    SectionCard {
        Text("До / после", style = MaterialTheme.typography.titleMedium)
        Box(Modifier.fillMaxWidth().aspectRatio(3f / 4f).clip(RoundedCornerShape(8.dp))) {
            PhotoImage(selected, Modifier.fillMaxSize())
            PhotoImage(
                first,
                Modifier
                    .fillMaxSize()
                    .drawWithContent {
                        clipRect(right = size.width * split) { this@drawWithContent.drawContent() }
                    },
            )
            Text(
                label(first),
                color = Color.White,
                modifier = Modifier.align(Alignment.TopStart).background(Color(0x88000000)).padding(6.dp),
            )
            Text(
                label(selected),
                color = Color.White,
                modifier = Modifier.align(Alignment.TopEnd).background(Color(0x88000000)).padding(6.dp),
            )
        }
        Slider(value = split, onValueChange = { split = it })
        Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            photos.drop(1).forEach { photo ->
                FilterChip(selected = selected == photo, onClick = { selected = photo }, label = { Text(label(photo)) })
            }
        }
    }
}

@Composable
private fun Timelapse(photos: List<PhotoEntity>) {
    var playing by remember { mutableStateOf(false) }
    var frame by remember(photos) { mutableIntStateOf(0) }
    LaunchedEffect(playing) {
        while (playing) {
            delay(350)
            frame = (frame + 1) % photos.size
        }
    }
    SectionCard {
        Text("Таймлапс", style = MaterialTheme.typography.titleMedium)
        if (playing) {
            val photo = photos[frame.coerceIn(0, photos.lastIndex)]
            Box(Modifier.fillMaxWidth().aspectRatio(3f / 4f).clip(RoundedCornerShape(8.dp))) {
                PhotoImage(photo, Modifier.fillMaxSize())
                Text(label(photo), color = Color.White, modifier = Modifier.background(Color(0x88000000)).padding(6.dp))
            }
        }
        OutlinedButton(onClick = { playing = !playing }) { Text(if (playing) "Стоп" else "Смотреть ${photos.size} снимков подряд") }
    }
}

@Composable
private fun PhotoImage(photo: PhotoEntity, modifier: Modifier) {
    AsyncImage(model = File(photo.path), contentDescription = label(photo), contentScale = ContentScale.Crop, modifier = modifier)
}

private fun label(photo: PhotoEntity) = if (photo.cycle > 1) "Ц${photo.cycle} · день ${photo.day}" else "День ${photo.day}"

private fun unlock(context: Context, onSuccess: () -> Unit, onUnavailable: () -> Unit) {
    val activity = context.findActivity() ?: return onUnavailable()
    val authenticators = BIOMETRIC_WEAK or DEVICE_CREDENTIAL
    if (BiometricManager.from(activity).canAuthenticate(authenticators) != BiometricManager.BIOMETRIC_SUCCESS) {
        onUnavailable()
        return
    }
    val prompt = BiometricPrompt(
        activity,
        ContextCompat.getMainExecutor(activity),
        object : BiometricPrompt.AuthenticationCallback() {
            override fun onAuthenticationSucceeded(result: BiometricPrompt.AuthenticationResult) = onSuccess()
        },
    )
    val info = BiometricPrompt.PromptInfo.Builder()
        .setTitle("Фото прогресса")
        .setSubtitle("Подтверди, что это ты")
        .setAllowedAuthenticators(authenticators)
        .build()
    prompt.authenticate(info)
}

private tailrec fun Context.findActivity(): FragmentActivity? = when (this) {
    is FragmentActivity -> this
    is ContextWrapper -> baseContext.findActivity()
    else -> null
}

// ---------- Графики ----------

@Composable
private fun ChartsTab(ui: ProgressUi, viewModel: ProgressViewModel) {
    var adding by remember { mutableStateOf(false) }
    if (ui.tests.isNotEmpty()) {
        SectionCard {
            Text("Тесты", style = MaterialTheme.typography.titleMedium)
            ui.tests.forEach { test ->
                val title = if (test.day == 1) "Цикл ${test.cycle}, старт" else "Цикл ${test.cycle}, финал"
                Text("$title: отжимания ${test.pushups}, приседания ${test.squats}, подтягивания ${test.pullups}, планка ${test.plankSec} с")
            }
        }
        if (ui.tests.size > 1) {
            ChartCard("Отжимания в тестах", ui.tests.map { it.pushups.toFloat() })
            ChartCard("Подтягивания в тестах", ui.tests.map { it.pullups.toFloat() })
        }
    }

    val reps = ui.workouts.filter { it.kind == DayKind.WORKOUT.name }.reversed()
    if (reps.size > 1) ChartCard("Длительность тренировок, мин", reps.map { it.durationSec / 60f })

    SectionCard {
        Text("Замеры", style = MaterialTheme.typography.titleMedium)
        Text(
            "Раз в неделю: вес и обхваты. Мышцы за месяц растут умеренно, а сантиметры покажут прогресс раньше зеркала.",
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        ui.measurements.takeLast(5).forEach { m ->
            Text(
                "${LocalDate.ofEpochDay(m.date)}: " + listOfNotNull(
                    m.weightKg?.let { "вес $it кг" },
                    m.chestCm?.let { "грудь $it" },
                    m.waistCm?.let { "талия $it" },
                    m.armCm?.let { "рука $it" },
                    m.hipsCm?.let { "бёдра $it" },
                ).joinToString(", "),
            )
        }
        Button(onClick = { adding = true }) { Text("Добавить замер") }
    }
    val weights = ui.measurements.mapNotNull { it.weightKg?.toFloat() }
    if (weights.size > 1) ChartCard("Вес, кг", weights)
    val arms = ui.measurements.mapNotNull { it.armCm?.toFloat() }
    if (arms.size > 1) ChartCard("Обхват руки, см", arms)

    if (adding) MeasurementDialog(onDismiss = { adding = false }) { w, c, wa, a, h ->
        viewModel.addMeasurement(w, c, wa, a, h)
        adding = false
    }
}

@Composable
private fun ChartCard(title: String, values: List<Float>) {
    SectionCard {
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
            Text(title, style = MaterialTheme.typography.titleMedium)
            Text("${fmt(values.first())} → ${fmt(values.last())}", fontWeight = FontWeight.Bold)
        }
        LineChart(values)
    }
}

private fun fmt(value: Float) = if (value % 1f == 0f) value.toInt().toString() else "%.1f".format(value)

@Composable
private fun MeasurementDialog(
    onDismiss: () -> Unit,
    onSave: (Double?, Double?, Double?, Double?, Double?) -> Unit,
) {
    val fields = remember { List(5) { mutableStateOf("") } }
    val titles = listOf("Вес, кг", "Грудь, см", "Талия, см", "Рука, см", "Бёдра, см")
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Замер") },
        text = {
            Column(Modifier.verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                fields.forEachIndexed { i, field ->
                    OutlinedTextField(
                        value = field.value,
                        onValueChange = { field.value = it },
                        label = { Text(titles[i]) },
                        singleLine = true,
                        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal),
                    )
                }
            }
        },
        confirmButton = {
            TextButton(onClick = {
                val values = fields.map { it.value.replace(',', '.').toDoubleOrNull() }
                onSave(values[0], values[1], values[2], values[3], values[4])
            }) { Text("Сохранить") }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Отмена") } },
    )
}

// ---------- Календарь ----------

@Composable
private fun CalendarTab(ui: ProgressUi) {
    val state = ui.state ?: return
    val logs = ui.workouts.filter { it.cycle == state.cycle }.associateBy { it.day }
    SectionCard {
        Text("Цикл ${state.cycle}", style = MaterialTheme.typography.titleMedium)
        (1..Schedule.DAYS).chunked(7).forEach { week ->
            Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                week.forEach { day ->
                    val log = logs[day]
                    val color = when {
                        log?.kind == DayKind.STRETCH.name -> MaterialTheme.colorScheme.secondary
                        log != null -> MaterialTheme.colorScheme.primary
                        day == state.day -> MaterialTheme.colorScheme.outline
                        else -> MaterialTheme.colorScheme.surfaceVariant
                    }
                    Box(
                        Modifier.size(36.dp).clip(RoundedCornerShape(8.dp)).background(color),
                        contentAlignment = Alignment.Center,
                    ) {
                        val training = Schedule.isTraining(state.mode, day)
                        Text("$day", fontWeight = if (training) FontWeight.Bold else FontWeight.Normal)
                    }
                }
            }
        }
        Legend(MaterialTheme.colorScheme.primary, "тренировка или тест")
        Legend(MaterialTheme.colorScheme.secondary, "растяжка в день отдыха")
        Legend(MaterialTheme.colorScheme.outline, "сегодня")
        Text("Жирным — тренировочные дни.", style = MaterialTheme.typography.bodySmall)
    }
    val history = ui.workouts.take(10)
    if (history.isNotEmpty()) {
        SectionCard {
            Text("Журнал", style = MaterialTheme.typography.titleMedium)
            history.forEach { log ->
                Text("${LocalDate.ofEpochDay(log.date)} · день ${log.day} · ${log.title}")
            }
        }
    }
}

@Composable
private fun Legend(color: Color, text: String) {
    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        Box(Modifier.size(14.dp).clip(RoundedCornerShape(3.dp)).background(color))
        Text(text, style = MaterialTheme.typography.bodySmall)
    }
}

// ---------- Ачивки и уровни ----------

@Composable
private fun AchievementsTab(ui: ProgressUi) {
    SectionCard {
        Text("Уровни прокачки", style = MaterialTheme.typography.titleMedium)
        ui.levels.forEach { (group, level) ->
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                Text(group.title)
                Text("ур. $level", fontWeight = FontWeight.Bold, color = MaterialTheme.colorScheme.primary)
            }
        }
    }
    SectionCard {
        Text("Ачивки", style = MaterialTheme.typography.titleMedium)
        Achievement.entries.forEach { achievement ->
            val open = achievement in ui.achievements
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                Text(if (open) "🏅" else "🔒", style = MaterialTheme.typography.titleLarge)
                Column {
                    Text(achievement.title, fontWeight = FontWeight.Bold)
                    Text(achievement.description, color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
            }
        }
    }
}
