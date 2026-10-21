package org.example.niannian.feature.notification

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
fun NotificationPanel(model: NotificationModel, family: String, user: String, subjects: List<Pair<String, String>>,
    unavailable: Boolean, authorizationKey: String) {
    var selected by remember(family, subjects) { mutableStateOf(subjects.firstOrNull()?.first.orEmpty()) }
    val state by model.state.collectAsState()
    val lifecycle = LocalLifecycleOwner.current.lifecycle
    DisposableEffect(lifecycle, family, selected, user, unavailable, authorizationKey) {
        fun activate() {
            model.clear()
            if (!unavailable && selected.isNotBlank()) { model.bind(family, selected, user); model.startPolling() }
        }
        val observer = LifecycleEventObserver { _, event ->
            if (event == Lifecycle.Event.ON_STOP) model.clear()
            if (event == Lifecycle.Event.ON_START) activate()
        }
        lifecycle?.addObserver(observer)
        if (lifecycle?.currentState?.isAtLeast(Lifecycle.State.STARTED) == true) activate() else model.clear()
        onDispose { lifecycle?.removeObserver(observer); model.clear() }
    }
    if (unavailable || state.family != family || state.owner != selected || state.user != user) return
    var inApp by remember(state.inApp) { mutableStateOf(state.inApp) }
    var push by remember(state.push) { mutableStateOf(state.push) }
    var zone by remember(state.timezone) { mutableStateOf(state.timezone) }
    var quietStart by remember(state.quietStart) { mutableStateOf(state.quietStart) }
    var quietEnd by remember(state.quietEnd) { mutableStateOf(state.quietEnd) }
    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Text("家人关注提示", fontSize = 24.sp)
            Text("Mock 演示 · 前台每 30 秒同步 · 未验证设备推送到达。")
            subjects.forEach { (id, name) -> OutlinedButton(onClick = { selected = id }, enabled = !state.busy) { Text(name) } }
            Text(state.message)
            Button(onClick = { model.refresh() }, enabled = !state.busy) { Text("刷新通知") }
            if (state.loaded && state.items.isEmpty() && state.detail.isEmpty()) Text("当前没有可查看的通知。")
            state.items.forEach { item ->
                Text(item.explanation, fontSize = 20.sp)
                Text(when (item.status) {
                    "READ" -> "已读"
                    "FAILED" -> "发送失败"
                    else -> if (item.channel == "IN_APP") "应用内可查看" else "模拟发送，未验证送达"
                })
                if (item.status != "FAILED") Button(onClick = { model.read(item) }, enabled = !state.busy) { Text("查看并标记已读") }
            }
            if (state.detail.isNotEmpty()) Text(state.detail, fontSize = 20.sp)
            if (state.loaded) {
                Text("我的通知偏好", fontSize = 20.sp)
                Text("选择渠道不会开启授权；交流摘要与关注通知分别由长辈决定。关闭两项可停止新通知。")
                Row { Checkbox(inApp, { inApp = it }, enabled = !state.busy); Text("应用内") }
                Row { Checkbox(push, { push = it }, enabled = !state.busy); Text("Mock 推送（仅演示）") }
                OutlinedTextField(zone, { zone = it }, label = { Text("时区，例如 Asia/Shanghai") }, enabled = !state.busy)
                OutlinedTextField(quietStart, { quietStart = it }, label = { Text("免打扰开始 HH:mm，可留空") }, enabled = !state.busy)
                OutlinedTextField(quietEnd, { quietEnd = it }, label = { Text("免打扰结束 HH:mm，可留空") }, enabled = !state.busy)
                Button(onClick = { model.save(inApp, push, zone, quietStart, quietEnd) }, enabled = !state.busy) { Text("保存通知偏好") }
            }
        }
    }
}
