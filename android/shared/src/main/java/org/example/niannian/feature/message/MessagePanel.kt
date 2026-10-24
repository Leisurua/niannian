package org.example.niannian.feature.message

import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.compose.LocalLifecycleOwner

@Composable
fun MessagePanel(model: MessageModel, family: String, user: String, elder: Boolean, unavailable: Boolean,
    manageLifecycle: Boolean = true) {
    val state by model.state.collectAsState()
    val lifecycle = LocalLifecycleOwner.current.lifecycle
    var draft by remember(family, user) { mutableStateOf("") }
    LaunchedEffect(state.sentVersion) { if (state.sentVersion > 0) draft = "" }
    if (manageLifecycle) DisposableEffect(lifecycle, family, user, unavailable) {
        fun activate() { if (!unavailable) model.bind(family, user) else model.clear() }
        val observer = LifecycleEventObserver { _, event ->
            if (event == Lifecycle.Event.ON_STOP) model.clear()
            if (event == Lifecycle.Event.ON_START) activate()
        }
        lifecycle.addObserver(observer)
        if (lifecycle.currentState.isAtLeast(Lifecycle.State.STARTED)) activate() else model.clear()
        onDispose { lifecycle.removeObserver(observer); model.clear() }
    }
    if (unavailable || state.family != family || state.user != user) return
    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Text("家人留言", fontSize = 24.sp)
            Text("前台每 3 秒同步，离线后重新连接可补收。已读需要本人点击确认。")
            OutlinedTextField(draft, { draft = it.take(2000) }, modifier = Modifier.fillMaxWidth(),
                label = { Text(if (elder) "给子女回复" else "给长辈留言") }, enabled = !state.busy)
            Button(onClick = { model.send(draft) }, enabled = !state.busy && draft.isNotBlank(),
                modifier = Modifier.heightIn(min = 56.dp)) { Text("发送留言", fontSize = 20.sp) }
            if (elder) Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlinedButton(onClick = { draft = "我很好，不用担心。" }, enabled = !state.busy) { Text("我很好") }
                OutlinedButton(onClick = { draft = "方便时请给我打个电话。" }, enabled = !state.busy) { Text("请给我打电话") }
            }
            if (state.notice.isNotBlank()) Text(state.notice, fontSize = 18.sp)
            if (state.error.isNotBlank()) Text(state.error, color = MaterialTheme.colorScheme.error)
            if (state.loaded && state.items.isEmpty()) Text("还没有家人留言。")
            OutlinedButton(onClick = { model.refresh() }, enabled = !state.busy) { Text("刷新收发箱") }
            state.items.forEach { item ->
                HorizontalDivider()
                Text((if (item.outgoing) "我发出的留言" else "家人发来的留言") + " · " + item.time)
                Text(item.text, fontSize = if (elder) 24.sp else 20.sp)
                Text(item.receipts.joinToString("、") { (_, status) -> when (status) {
                    "READ" -> "已读"; "RECEIVED" -> "已接收"; else -> "等待接收"
                } })
                if (!item.outgoing && item.receipts.any { it.second != "READ" })
                    Button(onClick = { model.read(item) }, enabled = !state.busy,
                        modifier = Modifier.heightIn(min = 56.dp)) { Text("我已读完这条", fontSize = 20.sp) }
            }
        }
    }
}
