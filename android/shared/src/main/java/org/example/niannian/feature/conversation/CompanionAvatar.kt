package org.example.niannian.feature.conversation

import android.graphics.BitmapFactory
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.*
import androidx.compose.material3.Button
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.OutlinedButton
import androidx.compose.foundation.Image
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.ImageBitmap
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.IntOffset
import androidx.compose.ui.unit.IntSize
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.compose.LocalLifecycleOwner
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.withContext
import kotlinx.coroutines.CancellationException

val LocalAvatarModel = staticCompositionLocalOf<AvatarModel?> { null }
private val LocalAvatarImport = staticCompositionLocalOf<(() -> Unit)?> { null }
private val LocalPhotoPicker = staticCompositionLocalOf<(() -> Unit)?> { null }
private val LocalAvatarGeneration = staticCompositionLocalOf<AvatarGenerationModel?> { null }

@Composable
fun AvatarHost(model: AvatarModel?, family: String, user: String, usable: Boolean, busy: Boolean,
    consentKey: String, generationModel: AvatarGenerationModel? = null, content: @Composable () -> Unit) {
    if (model == null) { content(); return }
    val lifecycle = LocalLifecycleOwner.current.lifecycle
    var foreground by remember(lifecycle) { mutableStateOf(lifecycle.currentState.isAtLeast(Lifecycle.State.STARTED)) }
    var checkedKey by remember(family, user) { mutableStateOf<String?>(null) }
    val state by model.state.collectAsState()
    val context = LocalContext.current
    val generationState = generationModel?.state?.collectAsState()?.value
    var pendingPhoto by remember(family, user) { mutableStateOf<android.net.Uri?>(null) }
    var photoOwner by remember(family, user) { mutableStateOf<String?>(null) }
    val photoPicker = rememberLauncherForActivityResult(ActivityResultContracts.GetContent()) { uri -> pendingPhoto = uri }
    LaunchedEffect(pendingPhoto, foreground, generationState?.available, generationState?.family, generationState?.user) {
        val uri = pendingPhoto
        if (uri != null && foreground && usable && generationState?.available == true
            && generationState.family == family && generationState.user == user) {
            pendingPhoto = null
            if (photoOwner != "$family:$user") return@LaunchedEffect
            try {
                val bytes = withContext(Dispatchers.IO) { prepareAvatarPhoto(context, uri) }
                val snapshot = generationModel?.state?.value
                if (snapshot?.family == family && snapshot.user == user) generationModel.selectedPhoto(bytes)
            } catch (cancelled: CancellationException) { throw cancelled }
            catch (_: Exception) { generationModel?.photoFailed() }
        }
    }
    var foregroundPackBinding by remember(family, user) { mutableStateOf<Pair<String, Int>?>(null) }
    var pendingForegroundPackUri by remember(family, user) { mutableStateOf<android.net.Uri?>(null) }
    val packPicker = rememberLauncherForActivityResult(ActivityResultContracts.GetContent()) { uri ->
        pendingForegroundPackUri = uri
        if (uri == null) foregroundPackBinding = null
    }
    LaunchedEffect(pendingForegroundPackUri, state.family, state.user, state.grantId, state.allowed, foreground) {
        val uri = pendingForegroundPackUri
        val binding = foregroundPackBinding
        if (uri != null && foreground && state.allowed) {
            pendingForegroundPackUri = null; foregroundPackBinding = null
            if (binding != ("${state.family}:${state.user}:${state.grantId}" to model.storageRevision.value)) return@LaunchedEffect
            model.importPack {
                context.contentResolver.openInputStream(uri)?.use { AvatarPack.readLimited(it) }
                    ?: throw IllegalArgumentException("Cannot read avatar pack")
            }
        }
    }
    DisposableEffect(lifecycle, model, family, user) {
        val observer = LifecycleEventObserver { _, event ->
            if (event == Lifecycle.Event.ON_STOP) { foreground = false; model.hide(); generationModel?.hide() }
            if (event == Lifecycle.Event.ON_START) { foreground = true; checkedKey = null }
        }
        lifecycle.addObserver(observer)
        onDispose { lifecycle.removeObserver(observer); model.hide(); generationModel?.hide() }
    }
    LaunchedEffect(foreground, usable, busy, family, user, consentKey) {
        if (!foreground || !usable) { model.hide(); generationModel?.hide() }
        else if (!busy) {
            if (checkedKey != consentKey) { checkedKey = consentKey; model.recheck(family, user) }
            else model.bind(family, user)
            generationModel?.bind(family, user)
        }
    }
    CompositionLocalProvider(LocalAvatarModel provides model, LocalAvatarImport provides {
        val snapshot = model.state.value
        if (snapshot.allowed && !snapshot.busy) {
            foregroundPackBinding = "${snapshot.family}:${snapshot.user}:${snapshot.grantId}" to model.storageRevision.value
            packPicker.launch("application/zip")
        }
    }, LocalAvatarGeneration provides generationModel, LocalPhotoPicker provides {
        photoOwner = "$family:$user"
        photoPicker.launch("image/*")
    }, content = content)
}

@Composable
fun CompanionAvatar(size: Dp = 148.dp, phase: CompanionPhase = CompanionPhase.IDLE, modifier: Modifier = Modifier,
    previewPack: AvatarPack? = null) {
    val model = LocalAvatarModel.current
    val state = model?.state?.collectAsState()?.value
    val revision = model?.storageRevision?.collectAsState()?.value
    val pack = previewPack ?: state?.pack?.takeIf { state.allowed && revision == state.storageRevision }
    var decoded by remember(pack) { mutableStateOf<Map<CompanionPhase, ImageBitmap>?>(null) }
    LaunchedEffect(pack) {
        decoded = if (pack == null) null else withContext(Dispatchers.IO) {
            runCatching { pack.clips.mapValues { (_, clip) ->
                val bitmap = checkNotNull(BitmapFactory.decodeByteArray(clip.png, 0, clip.png.size))
                check(bitmap.width == clip.width && bitmap.height == clip.height)
                bitmap.asImageBitmap()
            } }.getOrNull()
        }
    }
    val image = decoded?.get(phase)
    if (pack == null) {
        PersimmonCompanionOrb(size, phase, modifier)
        return
    }
    if (image == null) { Box(modifier.size(size)) { Text("正在读取角色图片…") }; return }
    val clip = pack.clips.getValue(phase)
    var frame by remember(pack, phase) { mutableIntStateOf(0) }
    LaunchedEffect(pack, phase) {
        val started = System.nanoTime()
        while (true) { delay(1000L / clip.fps); frame = clip.frameAt((System.nanoTime() - started) / 1_000_000) }
    }
    Canvas(modifier.size(size)) {
        drawImage(image, srcOffset = IntOffset((frame % 4) * 256, (frame / 4) * 256), srcSize = IntSize(256, 256),
            dstSize = IntSize(this.size.width.toInt(), this.size.height.toInt()))
    }
}

@Composable
fun AvatarControls() {
    val model = LocalAvatarModel.current ?: return
    val state by model.state.collectAsState()
    val importAvatar = LocalAvatarImport.current
    Text("陪伴形象", fontSize = 22.sp)
    PhotoAvatarControls()
    Text("也可导入本机角色包。使用人物外观仍由念念 AI 回答。", fontSize = 18.sp)
    if (state.message.isNotBlank()) Text(state.message, fontSize = 18.sp)
    Button(onClick = { importAvatar?.invoke() }, enabled = state.allowed && !state.busy,
        modifier = Modifier.fillMaxWidth().heightIn(min = 56.dp)) {
        Text(if (state.busy) "正在导入…" else "导入角色包", fontSize = 20.sp)
    }
    TextButton(onClick = { model.remove() }, modifier = Modifier.fillMaxWidth().heightIn(min = 48.dp)) {
        Text("删除本机形象并恢复默认", fontSize = 18.sp)
    }
    state.pack?.let { Text(it.credits, fontSize = 14.sp) }
}

@Composable
private fun PhotoAvatarControls() {
    val model = LocalAvatarGeneration.current ?: return
    val state by model.state.collectAsState()
    val appearance = LocalAvatarModel.current?.state?.collectAsState()?.value
    val selectPhoto = LocalPhotoPicker.current
    var phase by remember(state.job?.id) { mutableStateOf(CompanionPhase.IDLE) }
    val running = state.job?.status in listOf("UPLOADING", "QUEUED", "STYLIZING", "PREPARING", "RENDERING")
    Text(if (state.available) "选择照片，授权制作，预览满意后再启用。" else "照片制作服务暂未开放或无法连接，可继续使用默认形象。", fontSize = 18.sp)
    Button(onClick = { selectPhoto?.invoke() }, enabled = state.available && !state.busy && !running,
        modifier = Modifier.fillMaxWidth().heightIn(min = 56.dp)) { Text("选择照片制作形象", fontSize = 20.sp) }
    if (state.message.isNotBlank()) Text(state.message, fontSize = 18.sp)
    state.job?.let { job ->
        Text(job.label, fontSize = 20.sp)
        if (job.error.isNotBlank()) Text("可以取消此任务并重新选择照片；如持续失败，请联系管理员。")
        state.preview?.takeIf { appearance?.allowed == true && appearance.grantId == job.grantId }?.let { preview ->
            CompanionAvatar(size = 240.dp, phase = phase, previewPack = preview)
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                CompanionPhase.entries.forEach { option ->
                    TextButton(onClick = { phase = option }, modifier = Modifier.weight(1f)) {
                        Text(when (option) { CompanionPhase.IDLE -> "待机"; CompanionPhase.LISTENING -> "倾听"; CompanionPhase.THINKING -> "思考"; else -> "说话" })
                    }
                }
            }
            Text("请核对形象是否满意。此处说话动作为无声预览，启用后才跟随实际播音。")
            Button(onClick = model::confirm, enabled = !state.busy,
                modifier = Modifier.fillMaxWidth().heightIn(min = 56.dp)) { Text("确认并启用这个形象", fontSize = 20.sp) }
        }
        OutlinedButton(onClick = model::cancel, enabled = !state.busy) { Text("取消任务并删除服务端资源") }
    }
    state.photo?.let { bytes ->
        val image = remember(bytes) { BitmapFactory.decodeByteArray(bytes, 0, bytes.size)?.asImageBitmap() }
        AlertDialog(onDismissRequest = model::dismissPhoto,
            title = { Text("授权使用这张照片制作形象") },
            text = { Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                image?.let { Image(it, contentDescription = "待制作的人物照片", modifier = Modifier.fillMaxWidth().heightIn(max = 200.dp)) }
                Text("处理服务：${state.providerLabel}")
                Text(state.notice)
                Text("请使用本人或已获本人同意的照片。上传不会自动启用形象。")
            } },
            confirmButton = { TextButton(onClick = model::create, enabled = state.available && !state.busy && !running) { Text("同意并开始制作") } },
            dismissButton = { TextButton(onClick = model::dismissPhoto) { Text("取消") } })
    }
}
