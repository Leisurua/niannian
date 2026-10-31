package org.example.niannian.feature.conversation

import android.Manifest
import android.content.Context
import android.content.SharedPreferences
import android.content.pm.PackageManager
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.clickable
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
import androidx.compose.ui.Alignment
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.stateDescription
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.compose.LocalLifecycleOwner
import org.json.JSONObject

@Composable
fun ConversationPanel(model: ConversationModel, familyId: String, userId: String, unavailable: Boolean,
    startWithVoice: Boolean = false) {
    val state by model.state.collectAsState()
    val owner = LocalLifecycleOwner.current
    val context = LocalContext.current
    val weatherPrefs = remember(context) { context.getSharedPreferences("home-weather", Context.MODE_PRIVATE) }
    val weatherProfile = "$userId:$familyId:$userId"
    fun updateWeatherCity() {
        model.setWeatherCity(runCatching {
            JSONObject(weatherPrefs.getString(weatherProfile, null) ?: "").optInt("id").takeIf { it > 0 }
        }.getOrNull())
    }
    val voice = remember(context) { AndroidConversationVoice(context) }
    var draft by remember(familyId, userId) { mutableStateOf("") }
    var permissionSession by remember(familyId, userId) { mutableStateOf<String?>(null) }
    var pendingVoiceEntry by remember(familyId, userId) { mutableStateOf(startWithVoice) }
    val microphone = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
        val requestedSession = permissionSession
        permissionSession = null
        if (requestedSession != null && model.state.value.id == requestedSession && model.state.value.family == familyId
            && model.state.value.user == userId && owner.lifecycle.currentState.isAtLeast(Lifecycle.State.STARTED)) {
            if (granted) model.voiceEntry() else model.voicePermissionDenied()
        }
    }
    val chatScroll = rememberScrollState()
    fun requestVoice() {
        if (!model.state.value.connected || unavailable || permissionSession != null) return
        if (!model.state.value.voiceAllowed || context.checkSelfPermission(Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED) {
            model.voiceEntry()
        } else {
            model.interrupt()
            permissionSession = model.state.value.id
            microphone.launch(Manifest.permission.RECORD_AUDIO)
        }
    }
    LaunchedEffect(state.connected, unavailable) {
        if (pendingVoiceEntry && state.connected && !unavailable) {
            pendingVoiceEntry = false
            requestVoice()
        }
    }
    LaunchedEffect(state.messages) { chatScroll.animateScrollTo(chatScroll.maxValue) }
    LaunchedEffect(familyId, userId) { model.bind(familyId, userId); updateWeatherCity() }
    DisposableEffect(weatherPrefs, weatherProfile, model) {
        val listener = SharedPreferences.OnSharedPreferenceChangeListener { _, key ->
            if (key == weatherProfile) updateWeatherCity()
        }
        weatherPrefs.registerOnSharedPreferenceChangeListener(listener)
        onDispose { weatherPrefs.unregisterOnSharedPreferenceChangeListener(listener) }
    }
    DisposableEffect(model, voice) {
        model.attachVoice(voice)
        onDispose { model.detachVoice(voice) }
    }
    DisposableEffect(owner, familyId, userId) {
        val observer = LifecycleEventObserver { _, event ->
            if (event == Lifecycle.Event.ON_STOP) { pendingVoiceEntry = false; permissionSession = null; draft = ""; model.clear() }
            if (event == Lifecycle.Event.ON_START) { model.bind(familyId, userId); updateWeatherCity() }
        }
        owner.lifecycle.addObserver(observer)
        onDispose { owner.lifecycle.removeObserver(observer); permissionSession = null; draft = ""; model.clear() }
    }
    if (state.family != familyId || state.user != userId) return
    Card(Modifier.fillMaxSize()) {
        Column(Modifier.fillMaxSize().padding(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text("念念 AI 陪伴", fontSize = 26.sp)
            val phase = state.companionPhase
            val canSpeak = state.connected && !unavailable && permissionSession == null
            Row(verticalAlignment = Alignment.CenterVertically) {
                CompanionAvatar(size = 136.dp, phase = phase, modifier = Modifier
                    .semantics { contentDescription = "念念 AI 陪伴形象"; stateDescription = phase.label }
                    .clickable(enabled = canSpeak, role = Role.Button, onClickLabel = "开始说话") {
                        if (!state.recording) requestVoice()
                    })
                Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text(phase.label, fontSize = 24.sp,
                        modifier = Modifier.semantics { liveRegion = LiveRegionMode.Polite })
                    Text(when {
                        state.recording -> "您说，我在听"
                        state.recognizing -> "正在识别您说的话"
                        state.speechPending -> "正在准备朗读"
                        state.speaking -> "可以随时点停止"
                        state.busy && state.connected -> "正在想您的话"
                        state.busy -> "正在连接…"
                        !state.connected -> "请先连接聊天"
                        else -> "点我的形象说话"
                    }, fontSize = 18.sp)
                }
            }
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Button(onClick = { if (state.recording) model.finishListening() else requestVoice() },
                    enabled = canSpeak, modifier = Modifier.weight(1f).heightIn(min = 56.dp)) {
                    Text(if (state.recording) "说完了" else if (state.busy || state.voiceActive) "打断并说话" else "点击说话", fontSize = 20.sp)
                }
                Button(onClick = { pendingVoiceEntry = false; permissionSession = null; model.interrupt() },
                    enabled = state.connected && (state.busy || state.voiceActive || permissionSession != null),
                    modifier = Modifier.weight(1f).heightIn(min = 56.dp)) { Text("停止", fontSize = 20.sp) }
            }
            Column(Modifier.weight(1f).verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                Text(when (state.llmMode) {
                    "real" -> "AI 对话 · 支持语音和文字"
                    "mock" -> "闲聊为 Mock 演示 · 日期、天气和提醒查询使用实际数据"
                    else -> "连接后可说话或打字"
                }, color = MaterialTheme.colorScheme.primary)
                org.example.niannian.feature.voice.LocalVoiceProfiles.current?.let {
                    org.example.niannian.feature.voice.VoicePicker(it, model, familyId, userId)
                }
                Text("我是 AI，不是真实家人。会话回顾需要本人明确授权；不会自动联系家人。", fontSize = 18.sp)
                Text("可以问“今天几号”“今天会下雨吗”“今天有什么安排”，再说“第一项完成了”或“第一项稍后处理”。天气使用首页选择的城市。", fontSize = 18.sp)
                Text("点击说话后可说“再说一遍”“慢一点”“恢复语速”“停一下”或“结束聊天”。播放时不收音，请先点“打断并说话”；也可以直接点停止。", fontSize = 18.sp)
                Text("点击说话会使用设备语音服务，可能联网处理声音和朗读内容。应用不保存录音；控制口令直接执行，其他文字用于查询或 AI 对话。请勿说出密码或验证码。", fontSize = 18.sp)
                Column(Modifier.fillMaxWidth().heightIn(max = 360.dp).verticalScroll(chatScroll),
                    verticalArrangement = Arrangement.spacedBy(12.dp)) {
                    state.messages.forEach { item ->
                        Text("${if (item.fromUser) "您" else "念念 AI"}：${item.text}",
                            fontSize = if (state.slow) 28.sp else 22.sp,
                            modifier = Modifier.semantics { liveRegion = LiveRegionMode.Polite })
                        if (item.sourceLabels.isNotEmpty()) Text("来源：${item.sourceLabels.joinToString("、")}", fontSize = 16.sp)
                    }
                }
                if (state.message.isNotEmpty()) Text(state.message, fontSize = 18.sp)
                if (!state.connected) Control(if (state.id.isEmpty()) "开始聊天" else "重新连接",
                    !unavailable && !state.busy) { model.start() }
                if (state.partialTranscript.isNotEmpty()) Text("听到：${state.partialTranscript}", fontSize = 22.sp)
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
                if (state.connected) {
                    Control(if (state.voiceEnabled) "关闭朗读" else "开启朗读", !unavailable && state.voiceAllowed) { model.toggleSpeech() }
                    Control("再说一遍", !unavailable && !state.busy && !state.recording && !state.recognizing && state.reply.isNotEmpty()) { model.repeat() }
                    Control(if (state.slowSpeech) "恢复语速" else "说慢一点", !unavailable) { model.toggleSpeechRate() }
                    Text("朗读音量可用手机音量键调整。", fontSize = 18.sp)
                }
                Control(if (state.slow) "恢复字号" else "放大文字", !state.busy) { model.slowDown() }
                Control("结束聊天", state.id.isNotEmpty() && !unavailable) { draft = ""; model.end() }
                AvatarControls()
            }
        }
    }
}

@Composable private fun Control(label: String, enabled: Boolean, action: () -> Unit) {
    Button(onClick = action, enabled = enabled, modifier = Modifier.fillMaxWidth().heightIn(min = 64.dp)) {
        Text(label, fontSize = 20.sp)
    }
}
