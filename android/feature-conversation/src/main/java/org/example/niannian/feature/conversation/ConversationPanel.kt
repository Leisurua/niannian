package org.example.niannian.feature.conversation

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
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
            Text("Mock 演示 · 未启用录音和播音 · 简化形象", color = MaterialTheme.colorScheme.primary)
            Text("我是 AI，不是真实家人。语音、自动联系和摘要尚未开放。", fontSize = 18.sp)
            val label = when (state.state) {
                "LISTENING" -> "我在听（模拟状态，未采集声音）"
                "THINKING" -> "念念正在想…"
                "SPEAKING" -> "我在说（模拟状态）"
                "WARNING" -> "请先核实"
                "OFFLINE" -> "连接已断开"
                "ERROR" -> "暂时无法回应"
                else -> "念念准备好了"
            }
            Text("◉  $label", fontSize = 24.sp, modifier = Modifier.semantics { liveRegion = LiveRegionMode.Polite })
            if (state.reply.isNotEmpty()) Text(state.reply, fontSize = if (state.slow) 28.sp else 22.sp,
                modifier = Modifier.semantics { liveRegion = LiveRegionMode.Polite })
            if (state.message.isNotEmpty()) Text(state.message, fontSize = 18.sp)
            Control("说话", !unavailable && !state.busy) { model.voiceEntry() }
            Text("语音未开放时，可先点选模拟话题，无需打字。", fontSize = 18.sp)
            if (!state.connected && state.id.isNotEmpty()) Control("重新连接", !unavailable && !state.busy) { model.start() }
            Control("模拟说话：你好，念念", state.connected && !state.busy && !unavailable) { model.input("你好，念念") }
            Control("模拟说话：我女儿叫什么", state.connected && !state.busy && !unavailable) { model.input("我女儿叫什么") }
            Control("模拟说话：今天天气怎么样", state.connected && !state.busy && !unavailable) { model.input("今天天气怎么样") }
            OutlinedTextField(draft, { draft = it.take(2000) }, label = { Text("文字备用入口") },
                modifier = Modifier.fillMaxWidth(), enabled = state.connected && !state.busy && !unavailable)
            Control("发送", state.connected && !state.busy && !unavailable && draft.isNotBlank()) {
                model.input(draft); draft = ""
            }
            Control("停一下", state.connected) { model.interrupt() }
            Control("再说一遍", state.connected && !state.busy && state.reply.isNotEmpty()) { model.repeat() }
            Control("慢一点", state.connected && !state.busy && state.reply.isNotEmpty()) { model.slowDown() }
            Control("大声一点", state.connected) { model.volume() }
            Control("结束聊天", state.id.isNotEmpty()) { draft = ""; model.end() }
        }
    }
}

@Composable private fun Control(label: String, enabled: Boolean, action: () -> Unit) {
    Button(onClick = action, enabled = enabled, modifier = Modifier.fillMaxWidth().heightIn(min = 56.dp)) {
        Text(label, fontSize = 20.sp)
    }
}
