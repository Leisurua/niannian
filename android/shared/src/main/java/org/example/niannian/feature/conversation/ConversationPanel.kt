package org.example.niannian.feature.conversation

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
    var draft by remember(familyId, userId) { mutableStateOf("") }
    val chatScroll = rememberScrollState()
    LaunchedEffect(state.messages) { chatScroll.animateScrollTo(chatScroll.maxValue) }
    LaunchedEffect(familyId, userId) { model.bind(familyId, userId) }
    DisposableEffect(owner, familyId, userId) {
        val observer = LifecycleEventObserver { _, event ->
            if (event == Lifecycle.Event.ON_STOP) { draft = ""; model.clear() }
            if (event == Lifecycle.Event.ON_START) model.bind(familyId, userId)
        }
        owner.lifecycle.addObserver(observer)
        onDispose { owner.lifecycle.removeObserver(observer); draft = ""; model.clear() }
    }
    if (state.family != familyId || state.user != userId) return
    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Text("和念念聊聊", fontSize = 26.sp)
            Text(when (state.llmMode) {
                "real" -> "AI 文字对话 · 未启用录音和播音"
                "mock" -> "Mock 演示 · 固定模拟回复"
                else -> "文字对话 · 连接后显示服务状态"
            }, color = MaterialTheme.colorScheme.primary)
            Text("我是 AI，不是真实家人。语音和自动联系尚未开放；会话回顾需要本人明确授权。", fontSize = 18.sp)
            Text("发送文字后，由服务器配置的 AI 服务处理。请勿发送密码或验证码。", fontSize = 18.sp)
            val label = when (state.state) {
                "LISTENING" -> "可以输入想聊的话"
                "THINKING" -> "念念正在想…"
                "SPEAKING" -> "我在说（模拟状态）"
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
            OutlinedTextField(draft, { draft = it.take(2000) }, label = { Text("想和念念聊些什么？") },
                textStyle = MaterialTheme.typography.bodyLarge.copy(fontSize = 22.sp),
                modifier = Modifier.fillMaxWidth(), enabled = !state.busy && !unavailable)
            Control("发送", state.connected && !state.busy && !unavailable && draft.isNotBlank()) {
                if (model.input(draft)) draft = ""
            }
            if (state.connected && !state.busy && state.message.isNotEmpty() && state.retryText.isNotEmpty())
                Control("重新编辑上一条", !unavailable) { draft = state.retryText }
            if (state.busy && state.connected) Control("停止回复", true) { model.interrupt() }
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
