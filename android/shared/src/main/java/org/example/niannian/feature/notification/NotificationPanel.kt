package org.example.niannian.feature.notification

import android.content.Intent
import android.net.Uri
import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.lifecycle.compose.LocalLifecycleOwner
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver

@Composable
fun NotificationPanel(model: NotificationModel, family: String, user: String, subjects: List<Pair<String, String>>,
    unavailable: Boolean, authorizationKey: String, elder: Boolean = false, initialNotificationId: String = "") {
    var selected by remember(family, subjects) { mutableStateOf(subjects.firstOrNull()?.first.orEmpty()) }
    val state by model.state.collectAsState()
    val lifecycle = LocalLifecycleOwner.current.lifecycle
    val context = LocalContext.current
    var contactNotice by remember(family, selected) { mutableStateOf("") }
    var confirmation by remember(state.event, family, selected) { mutableStateOf<String?>(null) }
    DisposableEffect(lifecycle, family, selected, user, unavailable, authorizationKey) {
        fun activate() {
            model.clear()
            if (!unavailable && selected.isNotBlank()) {
                model.bind(family, selected, user)
                if (initialNotificationId.isNotBlank()) model.openNotification(initialNotificationId)
                model.startPolling()
            }
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
    var sms by remember(state.sms) { mutableStateOf(state.sms) }
    var phone by remember(state.phone) { mutableStateOf(state.phone) }
    var zone by remember(state.timezone) { mutableStateOf(state.timezone) }
    var quietStart by remember(state.quietStart) { mutableStateOf(state.quietStart) }
    var quietEnd by remember(state.quietEnd) { mutableStateOf(state.quietEnd) }
    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Text(if (elder) "家人的处理进度" else "家人关注事件", fontSize = 24.sp)
            Text("前台每 30 秒同步。识别提示不代表事实，处理结果由家属核实。")
            if (!elder) subjects.forEach { (id, name) -> OutlinedButton(onClick = { selected = id }, enabled = !state.busy) { Text(name) } }
            Text(state.message)
            Button(onClick = { model.refresh() }, enabled = !state.busy) { Text("刷新关注事件") }
            if (state.loaded && state.items.isEmpty() && state.detail.isEmpty()) Text("当前没有可查看的关注事件。")
            state.items.forEach { item ->
                Text(item.explanation, fontSize = 20.sp)
                Text("处理状态：${signalStatusLabel(item.eventStatus)}")
                if (!elder && item.deliveries.isEmpty()) Text("暂无已发布的通知，可直接处理事件")
                item.deliveries.forEach { Text(it) }
                Button(onClick = { model.read(item) }, enabled = !state.busy) { Text("查看事件") }
            }
            if (state.detail.isNotEmpty()) Text(state.detail, fontSize = 20.sp)
            state.event?.let { event ->
                Text("处理状态：${signalStatusLabel(event.status)}", fontSize = 20.sp)
                if (event.actionedAt.isNotBlank()) Text("最近处理：${event.actionedAt}")
                if (event.resolvedAt.isNotBlank()) Text("解决时间：${event.resolvedAt}")
                event.history.forEach { Text(it) }
                if ("ACKNOWLEDGE" in event.actions) Button(onClick = { model.handle("ACKNOWLEDGE") }, enabled = !state.busy) { Text("确认关注") }
                if (event.canHandle && event.status in listOf("ACKNOWLEDGED", "CONTACTED")) {
                    if (event.contacts.isEmpty()) Text("尚无可用的共享联系人。请长辈或紧急联系人在家庭设置中登记本人号码并允许分享。")
                    event.contacts.forEach { contact ->
                        Text("${contact.name}${if (contact.emergency) " · 紧急联系人" else ""}")
                        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            OutlinedButton(onClick = {
                                contactNotice = try {
                                    context.startActivity(Intent(Intent.ACTION_DIAL, Uri.fromParts("tel", contact.phone, null)))
                                    "已打开拨号。返回后请刷新并人工记录实际联系结果。"
                                } catch (_: Exception) { "此设备没有可用的拨号应用。" }
                            }, enabled = !state.busy) { Text("拨号") }
                            OutlinedButton(onClick = {
                                contactNotice = try {
                                    context.startActivity(Intent(Intent.ACTION_SENDTO, Uri.fromParts("smsto", contact.phone, null)))
                                    "已打开短信编辑器，请自行编辑并发送；返回后记录实际结果。"
                                } catch (_: Exception) { "此设备没有可用的短信应用。" }
                            }, enabled = !state.busy) { Text("发短信") }
                        }
                    }
                }
                if ("CONTACT" in event.actions) Button(onClick = { confirmation = "CONTACT" }, enabled = !state.busy) { Text("记录已联系") }
                if ("RESOLVE" in event.actions) Button(onClick = { confirmation = "RESOLVE" }, enabled = !state.busy) { Text("标记解决") }
                if ("FALSE_POSITIVE" in event.actions) OutlinedButton(onClick = { confirmation = "FALSE_POSITIVE" }, enabled = !state.busy) { Text("标记误报") }
                if (!elder && !event.canHandle) Text("当前仅可查看，处理需要家庭创建者或获授关注事件处理权限的家属。")
            }
            if (contactNotice.isNotBlank()) Text(contactNotice)
            if (state.loaded && !elder) {
                Text("我的通知偏好", fontSize = 20.sp)
                Text("选择渠道不会开启长辈授权。短信/电话使用本人登记号码；关闭所有渠道可停止新通知。外部服务可能计费。")
                Row { Checkbox(inApp, { inApp = it }, enabled = !state.busy); Text("应用内") }
                Row { Checkbox(push, { push = it }, enabled = !state.busy && (push || state.pushMode != "DISABLED")); Text(when (state.pushMode) {
                    "MOCK" -> "Mock 推送（仅演示）"; "AVAILABLE" -> "ntfy 推送（需订阅本人主题）"; else -> "推送（外发关闭或未配置）" }) }
                Row { Checkbox(sms, { sms = it }, enabled = !state.busy && (sms || state.smsAvailable)); Text("短信" + if (state.smsAvailable) "" else "（外发关闭或未配置）") }
                Row { Checkbox(phone, { phone = it }, enabled = !state.busy && (phone || state.phoneAvailable)); Text("自动语音电话" + if (state.phoneAvailable) "" else "（外发关闭或未配置）") }
                OutlinedTextField(zone, { zone = it }, label = { Text("时区，例如 Asia/Shanghai") }, enabled = !state.busy)
                OutlinedTextField(quietStart, { quietStart = it }, label = { Text("免打扰开始 HH:mm，可留空") }, enabled = !state.busy)
                OutlinedTextField(quietEnd, { quietEnd = it }, label = { Text("免打扰结束 HH:mm，可留空") }, enabled = !state.busy)
                Button(onClick = { model.save(inApp, push, zone, quietStart, quietEnd, sms, phone) }, enabled = !state.busy) { Text("保存通知偏好") }
            }
        }
    }
    confirmation?.let { action ->
        AlertDialog(onDismissRequest = { confirmation = null },
            title = { Text(signalActionLabel(action)) },
            text = { Text(if (action == "CONTACT") "请确认您已经通过电话、留言或当面等方式与长辈取得联系。这是您的人工记录，应用无法确认电话是否接通。"
                else if (action == "FALSE_POSITIVE") "请确认此提示属于误报。系统会保存处理历史并取消尚未发送的通知。"
                else "请在实际核实后标记解决；系统会保存您的确认及处理时间。") },
            confirmButton = { TextButton(onClick = { confirmation = null; model.handle(action) }) { Text("确认保存") } },
            dismissButton = { TextButton(onClick = { confirmation = null }) { Text("取消") } })
    }
}

fun signalStatusLabel(status: String) = when (status) {
    "ACKNOWLEDGED" -> "已确认关注"
    "CONTACTED" -> "已联系（人工记录）"
    "RESOLVED" -> "已解决（人工确认）"
    "FALSE_POSITIVE" -> "已标记误报"
    "VALIDATED", "NOTIFIED", "NOTIFICATION_FAILED" -> "待确认关注"
    else -> "待刷新核对"
}
