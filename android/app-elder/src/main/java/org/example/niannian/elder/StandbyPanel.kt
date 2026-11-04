package org.example.niannian.elder

import android.Manifest
import android.content.pm.PackageManager
import android.view.WindowManager
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.Checkbox
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalView
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import androidx.compose.ui.window.DialogWindowProvider
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.compose.LocalLifecycleOwner
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import org.example.niannian.feature.conversation.AndroidConversationVoice
import org.example.niannian.feature.reminder.ReminderStorage

@Composable
internal fun StandbySettings(store: ReminderStorage, savedUser: () -> String, family: String?) {
    var open by remember { mutableStateOf(false) }
    DeviceButton("打开念念待机页") { open = true }
    if (open) StandbyPanel(store, savedUser, family) { open = false }
}

@Composable
private fun StandbyPanel(store: ReminderStorage, savedUser: () -> String, family: String?, close: () -> Unit) {
    val context = LocalContext.current
    val lifecycle = LocalLifecycleOwner.current.lifecycle
    val lifecycleState by lifecycle.currentStateFlow.collectAsState()
    val scope = rememberCoroutineScope()
    val wakeAvailable = remember { hasWakeModel(context) }
    val voice = remember { AndroidConversationVoice(context, offlineOnly = true) }
    var wakeJob by remember { mutableStateOf<Job?>(null) }
    var readJob by remember { mutableStateOf<Job?>(null) }
    var permissionPending by remember { mutableStateOf<String?>(null) }
    var startAfterPermission by remember { mutableStateOf<String?>(null) }
    var camera by remember { mutableStateOf<CameraPresence?>(null) }
    var cameraStatus by remember { mutableStateOf("") }
    var waiting by remember { mutableStateOf(false) }
    var awake by remember { mutableStateOf(false) }
    var readAfterWake by remember { mutableStateOf(false) }
    var reading by remember { mutableStateOf(false) }
    var status by remember { mutableStateOf("") }

    fun stopAudio() {
        wakeJob?.cancel()
        readJob?.cancel()
        voice.stop()
        waiting = false
        reading = false
    }

    fun readReminders() {
        if (reading || !lifecycle.currentState.isAtLeast(Lifecycle.State.RESUMED)) return
        readJob?.cancel()
        reading = true
        status = "正在读取有效的本人提醒…"
        readJob = scope.launch {
            try {
                wakeJob?.join()
                val owner = savedUser()
                val valid = store.readCurrentDueTitles(owner, family) { titles ->
                    if (owner != savedUser() || !lifecycle.currentState.isAtLeast(Lifecycle.State.RESUMED)) {
                        reading = false
                    } else if (titles.isEmpty()) {
                        status = "当前没有到期且待处理的缓存提醒。"
                        reading = false
                    } else {
                        status = "正在本机朗读到期提醒。"
                        voice.speak("现在有以下提醒。" + titles.joinToString("。") + "。", slow = true, started = {},
                            finished = { reading = false; status = "朗读结束。可返回首页查看详情。" },
                            failed = { reading = false; status = "设备没有可用的离线中文声音，请查看文字提醒。" })
                    }
                }
                if (!valid) {
                    status = "没有可用的本人缓存，请联网同步提醒。"
                    reading = false
                } else if (reading) {
                    delay(60_000)
                    if (reading) {
                        voice.stop()
                        reading = false
                        status = "朗读超时，请查看文字提醒。"
                    }
                }
            } catch (cancelled: CancellationException) {
                throw cancelled
            } catch (_: Exception) {
                reading = false
                status = "暂时无法读取缓存，请查看提醒或联网重试。"
            }
        }
    }

    fun wake() {
        wakeJob?.cancel()
        camera?.close()
        camera = null
        cameraStatus = ""
        startAfterPermission = null
        permissionPending = null
        waiting = false
        awake = true
        status = "念念已唤醒。断网时可查看已缓存提醒，在线交流需要网络。"
        if (readAfterWake) readReminders()
    }

    fun startListening() {
        if (!wakeAvailable || wakeJob?.isActive == true || !lifecycle.currentState.isAtLeast(Lifecycle.State.RESUMED)) return
        waiting = true
        status = "正在加载离线唤醒模型…"
        wakeJob = scope.launch {
            try {
                waitForWakePhrase(context) { status = "语音待机中。请说“你好，小念”。" }
                wake()
            } catch (cancelled: CancellationException) {
                throw cancelled
            } catch (_: Exception) {
                waiting = false
                status = "本机语音待机不可用，请点击唤醒。"
            } catch (_: LinkageError) {
                waiting = false
                status = "设备不支持此离线引擎，请点击唤醒。"
            }
        }
    }

    fun startCamera() {
        if (awake || camera != null || !lifecycle.currentState.isAtLeast(Lifecycle.State.RESUMED)) return
        cameraStatus = "正在打开前置摄像头…"
        val detection = CameraPresence(context,
            ready = { cameraStatus = "接近唤醒已开启。靠近并停留片刻即可唤醒。" },
            failed = { message -> camera = null; cameraStatus = message }, detected = ::wake)
        camera = detection
        detection.open()
    }

    val permission = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
        val requested = permissionPending
        permissionPending = null
        if (requested != null) {
            if (granted) startAfterPermission = requested
            else if (requested == Manifest.permission.CAMERA) cameraStatus = "摄像头权限未开启，请点击唤醒。"
            else status = "麦克风权限未开启，请点击唤醒。"
        }
    }
    LaunchedEffect(startAfterPermission, lifecycleState) {
        if (lifecycleState == Lifecycle.State.RESUMED) {
            val requested = startAfterPermission
            startAfterPermission = null
            if (requested == Manifest.permission.CAMERA) startCamera()
            if (requested == Manifest.permission.RECORD_AUDIO) startListening()
        }
    }
    fun requestDevicePermission(requested: String, start: () -> Unit) {
        if (permissionPending != null) return
        if (context.checkSelfPermission(requested) == PackageManager.PERMISSION_GRANTED) start()
        else {
            permissionPending = requested
            permission.launch(requested)
        }
    }
    DisposableEffect(lifecycle, voice) {
        val observer = LifecycleEventObserver { _, event ->
            if (event == Lifecycle.Event.ON_PAUSE) {
                stopAudio()
                camera?.close()
                camera = null
                cameraStatus = ""
                awake = false
                status = ""
            }
            if (event == Lifecycle.Event.ON_STOP) {
                permissionPending = null
                startAfterPermission = null
            }
        }
        lifecycle.addObserver(observer)
        onDispose {
            lifecycle.removeObserver(observer)
            stopAudio()
            camera?.close()
            voice.close()
        }
    }

    Dialog(onDismissRequest = close, properties = DialogProperties(usePlatformDefaultWidth = false, decorFitsSystemWindows = false)) {
        val window = (LocalView.current.parent as? DialogWindowProvider)?.window
        DisposableEffect(window, awake) {
            val brightness = window?.attributes?.screenBrightness
            if (!awake && window != null) {
                window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
                window.attributes = window.attributes.apply { screenBrightness = 0.12f }
            }
            onDispose {
                window?.clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
                if (window != null && brightness != null) window.attributes = window.attributes.apply { screenBrightness = brightness }
            }
        }
        Surface(Modifier.fillMaxSize()) {
            Column(Modifier.safeDrawingPadding().verticalScroll(rememberScrollState()).padding(24.dp),
                verticalArrangement = Arrangement.spacedBy(16.dp)) {
                Text(if (awake) "您好，我是念念 AI" else "念念待机", fontSize = 28.sp)
                if (status.isNotBlank()) Text(status, fontSize = 20.sp)
                if (cameraStatus.isNotBlank()) Text(cameraStatus, fontSize = 18.sp)
                if (!awake) {
                    Text("可点击唤醒。开启语音待机后，麦克风只在此页由本机识别唤醒词。", fontSize = 20.sp)
                    Checkbox(checked = readAfterWake, onCheckedChange = { readAfterWake = it })
                    Text("唤醒后，用离线中文声音朗读本人已到期的提醒标题", fontSize = 18.sp)
                    DeviceButton("点击唤醒", action = ::wake)
                    if (wakeAvailable) {
                        DeviceButton(if (waiting) "关闭语音待机" else "开启语音待机") {
                            if (waiting) {
                                stopAudio()
                                status = "语音待机已关闭。"
                            } else requestDevicePermission(Manifest.permission.RECORD_AUDIO, ::startListening)
                        }
                    } else Text("此安装包未包含离线唤醒模型，仍可点击唤醒。", fontSize = 18.sp)
                    Text("接近唤醒默认关闭。开启后，前置摄像头仅在此页检测是否有人靠近。", fontSize = 18.sp)
                    DeviceButton(if (camera != null) "关闭接近唤醒" else "开启接近唤醒") {
                        if (camera != null) {
                            camera?.close()
                            camera = null
                            cameraStatus = "接近唤醒已关闭。"
                        } else requestDevicePermission(Manifest.permission.CAMERA, ::startCamera)
                    }
                } else {
                    DeviceButton(if (reading) "停止朗读" else "朗读离线提醒") {
                        if (reading) { stopAudio(); status = "已停止朗读。" } else readReminders()
                    }
                }
                OutlinedButton(onClick = close, modifier = Modifier.fillMaxWidth().heightIn(min = 56.dp)) {
                    Text("退出待机页", fontSize = 20.sp)
                }
            }
        }
    }
}

@Composable
internal fun DeviceButton(label: String, action: () -> Unit) {
    Button(onClick = action, modifier = Modifier.fillMaxWidth().heightIn(min = 56.dp)) { Text(label, fontSize = 20.sp) }
}
