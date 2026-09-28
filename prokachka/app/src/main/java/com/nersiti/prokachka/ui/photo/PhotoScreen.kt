package com.nersiti.prokachka.ui.photo

import android.Manifest
import android.content.pm.PackageManager
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.camera.core.CameraSelector
import androidx.camera.core.ImageCapture
import androidx.camera.core.ImageCaptureException
import androidx.camera.core.Preview
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.camera.view.PreviewView
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Cameraswitch
import androidx.compose.material3.Button
import androidx.compose.material3.FilledTonalButton
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Slider
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.core.content.ContextCompat
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.ViewModel
import androidx.lifecycle.compose.LocalLifecycleOwner
import coil.compose.AsyncImage
import com.nersiti.prokachka.core.Schedule
import com.nersiti.prokachka.data.PhotoAngle
import com.nersiti.prokachka.data.PhotoStorage
import com.nersiti.prokachka.data.ProgramRepository
import com.nersiti.prokachka.ui.components.AppTopBar
import com.nersiti.prokachka.ui.components.vibrate
import dagger.hilt.android.lifecycle.HiltViewModel
import java.io.File
import java.time.LocalDate
import javax.inject.Inject
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.launch

/** Кнопки громкости из Activity передаются экрану фото. */
object HardwareKeys {
    @Volatile
    var captureEnabled = false
    val events = MutableSharedFlow<Unit>(extraBufferCapacity = 1)
}

@HiltViewModel
class PhotoViewModel @Inject constructor(
    private val repository: ProgramRepository,
    private val storage: PhotoStorage,
) : ViewModel() {

    data class Plan(val cycle: Int, val day: Int, val angles: List<PhotoAngle>)

    /** Фронт каждый день, бок и спина — в дни 1, 10, 20 и 30. */
    suspend fun plan(): Plan {
        val state = checkNotNull(repository.sync())
        val all = if (state.day in Schedule.fullPhotoDays) PhotoAngle.entries else listOf(PhotoAngle.FRONT)
        val taken = storage.taken(state.cycle, state.day)
        return Plan(state.cycle, state.day, all.filter { it !in taken })
    }

    suspend fun ghost(angle: PhotoAngle): String? = storage.last(angle)?.path

    fun newFile(plan: Plan, angle: PhotoAngle): File = storage.newFile(plan.cycle, plan.day, angle)

    suspend fun save(plan: Plan, angle: PhotoAngle, file: File) =
        storage.save(plan.cycle, plan.day, angle, file, LocalDate.now())
}

@Composable
fun PhotoScreen(onBack: () -> Unit, onDone: () -> Unit, viewModel: PhotoViewModel = hiltViewModel()) {
    val context = LocalContext.current
    var granted by remember {
        mutableStateOf(ContextCompat.checkSelfPermission(context, Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED)
    }
    var denied by remember { mutableStateOf(false) }
    val permission = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) {
        granted = it
        denied = !it
    }
    var plan by remember { mutableStateOf<PhotoViewModel.Plan?>(null) }
    var index by remember { mutableIntStateOf(0) }

    LaunchedEffect(Unit) {
        val loaded = viewModel.plan()
        if (loaded.angles.isEmpty()) onDone() else plan = loaded
        if (!granted) permission.launch(Manifest.permission.CAMERA)
    }

    Scaffold(topBar = { AppTopBar("Фото прогресса", onBack = onBack) }) { padding ->
        Box(Modifier.fillMaxSize().padding(padding)) {
            val current = plan
            when {
                current == null -> Unit
                !granted -> PermissionNeeded(
                    denied = denied,
                    onRequest = { permission.launch(Manifest.permission.CAMERA) },
                    onSkip = onDone,
                )
                else -> {
                    val angle = current.angles[index]
                    CameraCapture(
                        title = "${angle.title} · ${index + 1} из ${current.angles.size}",
                        angle = angle,
                        viewModel = viewModel,
                        plan = current,
                        onSaved = {
                            if (index + 1 < current.angles.size) index++ else onDone()
                        },
                    )
                }
            }
        }
    }
}

@Composable
private fun PermissionNeeded(denied: Boolean, onRequest: () -> Unit, onSkip: () -> Unit) {
    Column(
        Modifier.fillMaxSize().padding(24.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp, Alignment.CenterVertically),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Text("Нужен доступ к камере", style = MaterialTheme.typography.titleLarge)
        Text(
            "Фото хранятся только внутри приложения и не попадают в галерею.",
            textAlign = TextAlign.Center,
        )
        Button(onClick = onRequest) { Text("Разрешить") }
        if (denied) TextButton(onClick = onSkip) { Text("Продолжить без фото") }
    }
}

@Composable
private fun CameraCapture(
    title: String,
    angle: PhotoAngle,
    viewModel: PhotoViewModel,
    plan: PhotoViewModel.Plan,
    onSaved: () -> Unit,
) {
    val context = LocalContext.current
    val lifecycleOwner = LocalLifecycleOwner.current
    val scope = rememberCoroutineScope()
    val previewView = remember { PreviewView(context).apply { scaleType = PreviewView.ScaleType.FILL_CENTER } }
    val capture = remember { ImageCapture.Builder().setCaptureMode(ImageCapture.CAPTURE_MODE_MINIMIZE_LATENCY).build() }
    var front by remember { mutableStateOf(true) }
    var ghost by remember(angle) { mutableStateOf<String?>(null) }
    var ghostAlpha by remember { mutableFloatStateOf(0.35f) }
    var countdown by remember { mutableIntStateOf(0) }
    var busy by remember { mutableStateOf(false) }

    LaunchedEffect(angle) { ghost = viewModel.ghost(angle) }

    DisposableEffect(front) {
        val future = ProcessCameraProvider.getInstance(context)
        future.addListener({
            val provider = future.get()
            val preview = Preview.Builder().build().also { it.setSurfaceProvider(previewView.surfaceProvider) }
            val selector = if (front) CameraSelector.DEFAULT_FRONT_CAMERA else CameraSelector.DEFAULT_BACK_CAMERA
            runCatching {
                provider.unbindAll()
                provider.bindToLifecycle(lifecycleOwner, selector, preview, capture)
            }
        }, ContextCompat.getMainExecutor(context))
        onDispose { runCatching { future.get().unbindAll() } }
    }

    fun shoot() {
        if (busy) return
        busy = true
        val file = viewModel.newFile(plan, angle)
        val metadata = ImageCapture.Metadata().apply { isReversedHorizontal = front }
        val options = ImageCapture.OutputFileOptions.Builder(file).setMetadata(metadata).build()
        capture.takePicture(
            options,
            ContextCompat.getMainExecutor(context),
            object : ImageCapture.OnImageSavedCallback {
                override fun onImageSaved(output: ImageCapture.OutputFileResults) {
                    vibrate(context, 150)
                    scope.launch {
                        viewModel.save(plan, angle, file)
                        busy = false
                        onSaved()
                    }
                }

                override fun onError(exception: ImageCaptureException) {
                    busy = false
                }
            },
        )
    }

    // Таймер 10 секунд: можно поставить телефон на полку.
    LaunchedEffect(countdown) {
        if (countdown > 0) {
            delay(1000)
            countdown--
            if (countdown == 0) shoot()
        }
    }

    DisposableEffect(Unit) {
        HardwareKeys.captureEnabled = true
        onDispose { HardwareKeys.captureEnabled = false }
    }
    LaunchedEffect(angle) { HardwareKeys.events.collect { shoot() } }

    Box(Modifier.fillMaxSize().background(Color.Black)) {
        AndroidView(factory = { previewView }, modifier = Modifier.fillMaxSize())
        ghost?.let { path ->
            AsyncImage(
                model = File(path),
                contentDescription = "Прошлый снимок",
                contentScale = ContentScale.Crop,
                modifier = Modifier.fillMaxSize().alpha(ghostAlpha),
            )
        }
        Silhouette(Modifier.fillMaxSize())

        Column(Modifier.align(Alignment.TopCenter).fillMaxWidth().background(Color(0x88000000)).padding(12.dp)) {
            Text(title, color = Color.White, style = MaterialTheme.typography.titleMedium)
            Text(
                "Встань в контур и совмести позу с прошлым снимком. Съёмка — таймером или кнопкой громкости.",
                color = Color.White,
                style = MaterialTheme.typography.bodySmall,
            )
            if (ghost != null) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text("Призрак", color = Color.White, style = MaterialTheme.typography.bodySmall)
                    Slider(value = ghostAlpha, onValueChange = { ghostAlpha = it }, valueRange = 0f..0.8f)
                }
            }
        }

        if (countdown > 0) {
            Text(
                "$countdown",
                modifier = Modifier.align(Alignment.Center),
                color = Color.White,
                style = MaterialTheme.typography.displayLarge,
            )
        }

        Row(
            Modifier.align(Alignment.BottomCenter).fillMaxWidth().background(Color(0x88000000)).padding(12.dp),
            horizontalArrangement = Arrangement.SpaceEvenly,
            verticalAlignment = Alignment.CenterVertically,
        ) {
            IconButton(onClick = { front = !front }) {
                Icon(Icons.Default.Cameraswitch, contentDescription = "Сменить камеру", tint = Color.White)
            }
            FilledTonalButton(onClick = { countdown = 10 }, enabled = countdown == 0 && !busy) { Text("Таймер 10 с") }
            Button(onClick = { shoot() }, enabled = !busy) { Text("Снять") }
        }
    }
}

/** Контур силуэта: помогает каждый раз вставать на одно и то же место. */
@Composable
private fun Silhouette(modifier: Modifier) {
    Canvas(modifier) {
        val stroke = Stroke(width = 3.dp.toPx(), pathEffect = PathEffect.dashPathEffect(floatArrayOf(24f, 16f)))
        val color = Color.White.copy(alpha = 0.7f)
        val cx = size.width / 2
        val top = size.height * 0.16f
        val head = size.height * 0.055f
        drawCircle(color, radius = head, center = Offset(cx, top + head), style = stroke)
        val shoulders = size.width * 0.34f
        val torsoTop = top + head * 2.3f
        val torsoHeight = size.height * 0.3f
        drawRoundRect(
            color,
            topLeft = Offset(cx - shoulders / 2, torsoTop),
            size = Size(shoulders, torsoHeight),
            cornerRadius = CornerRadius(40f, 40f),
            style = stroke,
        )
        val legTop = torsoTop + torsoHeight
        val legBottom = size.height * 0.95f
        drawLine(color, Offset(cx - shoulders * 0.25f, legTop), Offset(cx - shoulders * 0.32f, legBottom), strokeWidth = stroke.width, pathEffect = stroke.pathEffect)
        drawLine(color, Offset(cx + shoulders * 0.25f, legTop), Offset(cx + shoulders * 0.32f, legBottom), strokeWidth = stroke.width, pathEffect = stroke.pathEffect)
        drawLine(color, Offset(cx - shoulders / 2, torsoTop + 20f), Offset(cx - shoulders * 0.8f, legTop), strokeWidth = stroke.width, pathEffect = stroke.pathEffect)
        drawLine(color, Offset(cx + shoulders / 2, torsoTop + 20f), Offset(cx + shoulders * 0.8f, legTop), strokeWidth = stroke.width, pathEffect = stroke.pathEffect)
    }
}
