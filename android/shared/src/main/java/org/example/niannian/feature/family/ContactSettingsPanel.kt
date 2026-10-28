package org.example.niannian.feature.family

import android.content.Intent
import android.net.Uri
import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.compose.LocalLifecycleOwner
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.launch
import org.json.JSONObject
import org.json.JSONArray
import org.example.niannian.feature.notification.validPushSubscription

@Composable
internal fun ContactSettingsPanel(model: CompanionModel, family: String, unavailable: Boolean) {
    val lifecycle = LocalLifecycleOwner.current.lifecycle
    var foreground by remember(lifecycle) { mutableStateOf(lifecycle.currentState.isAtLeast(Lifecycle.State.STARTED)) }
    DisposableEffect(lifecycle) {
        val observer = LifecycleEventObserver { _, event ->
            if (event == Lifecycle.Event.ON_STOP) foreground = false
            if (event == Lifecycle.Event.ON_START) foreground = true
        }
        lifecycle.addObserver(observer)
        onDispose { lifecycle.removeObserver(observer) }
    }
    if (foreground && !unavailable) key(family) { ContactEditor(model, family) }
}

@Composable
private fun ContactEditor(model: CompanionModel, family: String) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var version by remember { mutableStateOf<Long?>(null) }
    var phone by remember { mutableStateOf("") }
    var topic by remember { mutableStateOf("") }
    var pushStatus by remember { mutableStateOf("DISABLED") }
    var subscription by remember { mutableStateOf<String?>(null) }
    var share by remember { mutableStateOf(false) }
    var emergency by remember { mutableStateOf(false) }
    var busy by remember { mutableStateOf(false) }
    var message by remember { mutableStateOf("") }
    var recipients by remember { mutableStateOf<List<JSONObject>>(emptyList()) }
    var consentChange by remember { mutableStateOf<Triple<String, String, String?>?>(null) }
    fun apply(value: JSONObject) {
        version = value.getLong("version"); phone = value.getString("phone"); topic = value.getString("ntfy_topic")
        share = value.getBoolean("share_phone"); emergency = value.getBoolean("emergency")
        pushStatus = value.optString("push_status", "DISABLED")
        subscription = validPushSubscription(value.optString("push_subscription_url"))
        val entries = value.optJSONArray("recipients") ?: JSONArray()
        recipients = (0 until entries.length()).map { entries.getJSONObject(it) }
    }
    fun execute(method: String = "GET") {
        if (busy) return
        busy = true
        scope.launch {
            try {
                val body = if (method == "PUT") JSONObject().put("phone", phone.trim()).put("ntfy_topic", topic.trim())
                    .put("share_phone", share).put("emergency", emergency) else null
                val result = model.contact(family, method, body, if (method == "PUT") version else null)
                if (method == "DELETE") { version = 0; phone = ""; topic = ""; share = false; emergency = false; subscription = null }
                else apply(result)
                message = when (method) { "PUT" -> "联系方式已保存。"; "DELETE" -> "联系方式已删除。"; else -> "已同步本人的联系方式。" }
            } catch (cancelled: CancellationException) { throw cancelled }
            catch (_: Exception) { version = null; phone = ""; topic = ""; subscription = null; message = "操作结果未确认，请刷新核对网络或服务端联系人配置。" }
            finally { busy = false }
        }
    }
    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text("我的联系方式与紧急联系")
            Text("仅登记本人号码；允许分享后，获长辈授权且有处理权限的家属可在事件中拨号。可随时删除。")
            Button(onClick = { execute() }, enabled = !busy) { Text("读取 / 刷新我的联系方式") }
            if (version != null) {
                OutlinedTextField(phone, { phone = it }, label = { Text("本人号码，带国家区号，如 +86…") }, enabled = !busy)
                Row { Checkbox(share, { share = it }, enabled = !busy); Text("允许获授权的处理人查看我的号码") }
                Row { Checkbox(emergency, { emergency = it }, enabled = !busy); Text("愿意作为本家庭紧急联系人") }
                Text("紧急联系人仍需家庭处理权限和长辈授权；登记不代表已经获得授权。")
                Text("及时通知（ntfy）：" + if (pushStatus == "AVAILABLE") "服务已配置，需完成本机订阅" else "服务端尚未开启真实推送")
                OutlinedTextField(topic, { topic = it; subscription = null }, label = { Text("管理员分配给本人的私有主题（可留空）") }, enabled = !busy)
                Text("保存后打开 ntfy 订阅，使用本人的订阅账号登录并开启即时投递和系统通知；在对应长辈的关注事件页勾选“推送”。消息到达后可直接打开念念核实处理。")
                Button(onClick = { execute("PUT") }, enabled = !busy) { Text("保存本人联系方式") }
                subscription?.let { link ->
                    OutlinedButton(onClick = {
                        message = try {
                            context.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(link)).setPackage("io.heckel.ntfy"))
                            "已打开订阅设置，请检查登录和即时投递状态；打开设置不代表通知已送达。"
                        } catch (_: Exception) { "请先安装 ntfy 客户端，再打开订阅。" }
                    }, enabled = !busy) { Text("打开 ntfy 订阅") }
                }
                TextButton(onClick = {
                    runCatching { context.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse("https://docs.ntfy.sh/subscribe/phone/"))) }
                        .onFailure { message = "无法打开浏览器，请在设备上安装 ntfy 客户端。" }
                }) { Text("ntfy 安装与使用说明") }
                OutlinedButton(onClick = { execute("DELETE") }, enabled = !busy) { Text("删除本人联系方式") }
            }
            if (message.isNotBlank()) Text(message)
            recipients.forEach { recipient ->
                Text("${recipient.getString("display_name")} · 关注通知授权")
                listOf("NOTIFICATION_TO_FAMILY" to "关注通知", "HEALTH_MEDICATION" to "健康与用药信息").forEach { (code, label) ->
                    val grants = recipient.getJSONObject("grants")
                    val revokeId = if (grants.isNull(code)) null else grants.getString(code)
                    OutlinedButton(onClick = { consentChange = Triple(recipient.getString("user_id"), code, revokeId) }, enabled = !busy) {
                        Text(if (revokeId == null) "允许$label" else "撤回$label")
                    }
                }
            }
        }
    }
    consentChange?.let { change ->
        AlertDialog(onDismissRequest = { consentChange = null }, title = { Text("确认更改这位家人的授权") },
            text = { Text(if (change.third == null) "允许这位家人在具备家庭权限时查看对应关注信息并接收通知。您可以随时撤回。" else "撤回后将停止这位家人的相应访问和待发通知。") },
            confirmButton = { TextButton(onClick = {
                consentChange = null; busy = true
                scope.launch {
                    try { model.contactConsent(family, change.first, change.second, change.third); apply(model.contact(family)); message = "授权已更新。" }
                    catch (cancelled: CancellationException) { throw cancelled }
                    catch (_: Exception) { recipients = emptyList(); message = "授权更新结果未确认，请刷新核对。" }
                    finally { busy = false }
                }
            }) { Text("确认") } }, dismissButton = { TextButton(onClick = { consentChange = null }) { Text("取消") } })
    }
}
