package org.example.niannian.feature.conversation

import android.Manifest
import android.content.pm.PackageManager
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.compose.LocalLifecycleOwner

@Composable
fun ConversationPanel(model: ConversationModel, familyId: String, userId: String, unavailable: Boolean) {
    val state by model.state.collectAsState()
    val owner = LocalLifecycleOwner.current
    val context = LocalContext.current
    val voice = remember(context) { AndroidConversationVoice(context) }
    var draft by remember(familyId, userId) { mutableStateOf("") }
    var permissionSession by remember(familyId, userId) { mutableStateOf<String?>(null) }
    val microphone = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
        val requestedSession = permissionSession
        permissionSession = null
        if (requestedSession != null && model.state.value.id == requestedSession && model.state.value.family == familyId
            && model.state.value.user == userId && owner.lifecycle.currentState.isAtLeast(Lifecycle.State.STARTED)) {
            if (granted) model.voiceEntry() else model.voicePermissionDenied()
        }
    }
    val chatScroll = rememberScrollState()
    LaunchedEffect(state.messages) { chatScroll.animateScrollTo(chatScroll.maxValue) }
    LaunchedEffect(familyId, userId) { model.bind(familyId, userId) }
    DisposableEffect(model, voice) {
        model.attachVoice(voice)
        onDispose { model.detachVoice(voice) }
    }
    DisposableEffect(owner, familyId, userId) {
        val observer = LifecycleEventObserver { _, event ->
            if (event == Lifecycle.Event.ON_STOP) { permissionSession = null; draft = ""; model.clear() }
            if (event == Lifecycle.Event.ON_START) model.bind(familyId, userId)
        }
        owner.lifecycle.addObserver(observer)
        onDispose { owner.lifecycle.removeObserver(observer); permissionSession = null; draft = ""; model.clear() }
    }
    if (state.family != familyId || state.user != userId) return
    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Text("和念念聊聊", fontSize = 26.sp)
            Text(when (state.llmMode) {
                "real" -> "AI 对话 · 支持语音和文字"
                "mock" -> "Mock 演示 · 固定模拟回复"
                else -> "连接后可说话或打字"
            }, color = MaterialTheme.colorScheme.primary)
            Text("我是 AI，不是真实家人。会话回顾需要本人明确授权；不会自动联系家人。", fontSize = 18.sp)
            Text("点击说话会使用设备语音服务，可能联网处理声音和朗读内容。应用不保存录音；识别文字交给 AI。请勿说出密码或验证码。", fontSize = 18.sp)
            val label = when (state.state) {
                "LISTENING" -> if (state.recording) "正在听您说话…" else "可以说话或打字"
                "THINKING" -> if (state.recognizing) "正在识别…" else "念念正在想…"
                "SPEAKING" -> "念念正在说话"
                "WARNING" -> "请先核实"
                "OFFLINE" -> "连接已断开"
                "ERROR" -> "暂时无法回应"
                else -> "念念准备好了"
            }
            Text("◉  $label", fontSize = 24.sp, modifier = Modifier.semantics { liveRegion = LiveRegionMode.Polite })
            Column(Modifier.fillMaxWidth().heightIn(max = 360.dp).verticalScroll(chatScroll),
                verticalArrangement = Arrangement.spacedBy(12.dp)) {
                state.messages.forEach { item ->
                    Text("${if (item.fromUser) "您" else "念念 AI"}：${item.text}",
                        fontSize = if (state.slow) 28.sp else 22.sp,
                        modifier = Modifier.semantics { liveRegion = LiveRegionMode.Polite })
                }
            }
            if (state.message.isNotEmpty()) Text(state.message, fontSize = 18.sp)
            if (!state.connected) Control(if (state.id.isEmpty()) "开始聊天" else "重新连接",
                !unavailable && !state.busy) { model.start() }
            if (state.partialTranscript.isNotEmpty()) Text("听到：${state.partialTranscript}", fontSize = 22.sp)
            if (state.connected) {
                if (state.recording) Control("说完了", !unavailable) { model.finishListening() }
                else Control(if (state.busy || state.speaking || state.recognizing) "打断并说话" else "点击说话", !unavailable && state.voiceAllowed) {
                    if (context.checkSelfPermission(Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED) {
                        model.voiceEntry()
                    } else {
                        model.interrupt()
                        permissionSession = state.id
                        microphone.launch(Manifest.permission.RECORD_AUDIO)
                    }
                }
            }
            if (state.connected && !state.voiceAllowed)
                Text("语音尚未授权：请在“家庭与授权设置 → 用于我与念念的交流”中允许语音处理。文字聊天仍可使用。", fontSize = 18.sp)
            OutlinedTextField(draft, { draft = it.take(2000) }, label = { Text("想和念念聊些什么？") },
                textStyle = MaterialTheme.typography.bodyLarge.copy(fontSize = 22.sp),
                modifier = Modifier.fillMaxWidth(), enabled = !state.busy && !state.recording && !state.recognizing && !unavailable)
            Control("发送", state.connected && !state.busy && !state.recording && !state.recognizing && !unavailable && draft.isNotBlank()) {
                if (model.input(draft)) draft = ""
            }
            if (state.connected && !state.busy && state.message.isNotEmpty() && state.retryText.isNotEmpty())
                Control("重新编辑上一条", !unavailable) { draft = state.retryText }
            if ((state.busy || state.recording || state.recognizing || state.speaking) && state.connected)
                Control("停止", true) { model.interrupt() }
            if (state.connected) {
                Control(if (state.voiceEnabled) "关闭朗读" else "开启朗读", !unavailable && state.voiceAllowed) { model.toggleSpeech() }
                Control("再说一遍", !unavailable && !state.busy && !state.recording && !state.recognizing && state.reply.isNotEmpty()) { model.repeat() }
                Control(if (state.slowSpeech) "恢复语速" else "说慢一点", !unavailable) { model.toggleSpeechRate() }
                Text("朗读音量可用手机音量键调整。", fontSize = 18.sp)
            }
            Control(if (state.slow) "恢复字号" else "放大文字", !state.busy) { model.slowDown() }
            Control("结束聊天", state.id.isNotEmpty() && !unavailable) { draft = ""; model.end() }
        }
    }
}

@Composable private fun Control(label: String, enabled: Boolean, action: () -> Unit) {
    Button(onClick = action, enabled = enabled, modifier = Modifier.fillMaxWidth().heightIn(min = 64.dp)) {
        Text(label, fontSize = 20.sp)
    }
}
