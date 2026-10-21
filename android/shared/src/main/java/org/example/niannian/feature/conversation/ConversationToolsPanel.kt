package org.example.niannian.feature.conversation

import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.lifecycle.compose.LocalLifecycleOwner
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver

@Composable
fun ConversationToolsPanel(model: ConversationToolsModel, family: String, subjects: List<Pair<String, String>>, elder: Boolean, unavailable: Boolean, conversationId: String = "") {
    var selected by remember(family, subjects) { mutableStateOf(subjects.firstOrNull()?.first.orEmpty()) }
    val state by model.state.collectAsState()
    val lifecycle = LocalLifecycleOwner.current.lifecycle
    var cid by remember(family, selected, conversationId) { mutableStateOf(conversationId) }
    var reason by remember(family, selected) { mutableStateOf<String?>(null) }
    LaunchedEffect(family, selected, unavailable) {
        if (unavailable) model.clear() else model.bind(family, selected)
    }
    DisposableEffect(lifecycle, family, selected) {
        val observer = LifecycleEventObserver { _, event ->
            if (event == Lifecycle.Event.ON_STOP) { cid = ""; reason = null; model.clear() }
            if (event == Lifecycle.Event.ON_START) model.bind(family, selected)
        }
        lifecycle?.addObserver(observer)
        onDispose { lifecycle?.removeObserver(observer); model.clear() }
    }
    if (state.family != family || state.owner != selected) return
    var zone by remember(state.timezone) { mutableStateOf(state.timezone) }
    var start by remember(state.start) { mutableStateOf(state.start) }
    var end by remember(state.end) { mutableStateOf(state.end) }
    var quietStart by remember(state.quietStart) { mutableStateOf(state.quietStart) }
    var quietEnd by remember(state.quietEnd) { mutableStateOf(state.quietEnd) }
    var cap by remember(state.cap) { mutableStateOf(state.cap.toString()) }
    val enabled = !unavailable && !state.busy
    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Text("主动陪伴与会话回顾", fontSize = 24.sp)
            Text("Mock · 仅在线文字邀请；不会后台唤醒、播音或通知家人。")
            if (!elder) subjects.forEach { (id, name) -> OutlinedButton(onClick = { selected = id }, enabled = enabled) { Text(name) } }
            if (selected.isEmpty()) Text("当前没有可选择的长辈。")
            Button(onClick = { model.refresh() }, enabled = enabled && selected.isNotEmpty(), modifier = Modifier.fillMaxWidth().heightIn(min = if (elder) 64.dp else 48.dp)) { Text("读取当前设置") }
            if (state.loaded) {
                Text("时间窗 ${state.start}—${state.end}，每日上限 ${state.cap}；" + if (state.confirmed) "长辈已确认" else "等待长辈确认")
                if (state.paused.isNotEmpty()) Text("最近暂停日期：${state.paused}")
                if (elder) {
                    Button(onClick = { model.confirm() }, enabled = enabled && !state.confirmed, modifier = Modifier.fillMaxWidth().heightIn(min = 64.dp)) { Text("确认家人提出的设置", fontSize = 20.sp) }
                    Button(onClick = { model.pause() }, enabled = enabled, modifier = Modifier.fillMaxWidth().heightIn(min = 64.dp)) { Text("今天少打扰我", fontSize = 20.sp) }
                } else {
                    OutlinedTextField(zone, { zone = it }, label = { Text("时区，例如 Asia/Shanghai") }, enabled = enabled)
                    OutlinedTextField(start, { start = it }, label = { Text("开始 HH:mm") }, enabled = enabled)
                    OutlinedTextField(end, { end = it }, label = { Text("结束 HH:mm") }, enabled = enabled)
                    OutlinedTextField(quietStart, { quietStart = it }, label = { Text("免打扰开始（可留空）") }, enabled = enabled)
                    OutlinedTextField(quietEnd, { quietEnd = it }, label = { Text("免打扰结束（可留空）") }, enabled = enabled)
                    OutlinedTextField(cap, { cap = it.take(1) }, label = { Text("每日上限 0—3；0 关闭") }, enabled = enabled)
                    Button(onClick = { model.propose(zone, start, end, quietStart, quietEnd, cap) }, enabled = enabled) { Text("提出设置，等待长辈确认") }
                }
            }
            Text(if (elder) "回顾本次会话" else "回顾已知会话（无历史列表）", fontSize = 20.sp)
            if (!elder) OutlinedTextField(cid, { cid = it.take(36) }, label = { Text("本次会话编号") }, enabled = enabled)
            else if (cid.isBlank()) Text("先与念念聊聊，本次会话会自动显示在这里。")
            if (!elder) {
                Text("每次查看选择理由；有效授权不需要重复申请。")
                Row {
                    OutlinedButton(onClick = { reason = "FAMILY_CHECK_IN" }, enabled = enabled) { Text(if (reason == "FAMILY_CHECK_IN") "✓ 关心近况" else "关心近况") }
                    OutlinedButton(onClick = { reason = "FOLLOW_UP" }, enabled = enabled) { Text(if (reason == "FOLLOW_UP") "✓ 跟进交流" else "跟进交流") }
                }
            }
            Button(onClick = { model.summary(cid, if (elder) null else reason); reason = null }, enabled = enabled && cid.isNotBlank() && (elder || reason != null), modifier = Modifier.fillMaxWidth().heightIn(min = if (elder) 64.dp else 48.dp)) { Text("查看本次摘要") }
            if (elder) Button(onClick = { model.summary(cid, null, true) }, enabled = enabled && cid.isNotBlank(), modifier = Modifier.fillMaxWidth().heightIn(min = 64.dp)) { Text("请求生成本次摘要") }
            if (state.summary.isNotEmpty()) Text(state.summary, fontSize = 22.sp)
            if (state.message.isNotEmpty()) Text(state.message, fontSize = 18.sp)
        }
    }
}
