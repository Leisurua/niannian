package org.example.niannian.feature.notification

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import org.json.JSONArray
import org.json.JSONObject
import java.util.UUID

interface NotificationGateway {
    suspend fun list(): List<JSONObject>
    suspend fun events(family: String): List<JSONObject>
    suspend fun call(path: String, method: String = "GET", body: JSONObject? = null, version: Long? = null): JSONObject
    suspend fun read(id: String, key: String): JSONObject
    suspend fun act(id: String, body: JSONObject, key: String): JSONObject
}

data class InboxItem(val id: String, val eventId: String, val status: String, val channel: String,
    val summary: String, val explanation: String, val eventStatus: String = "", val deliveries: List<String> = emptyList())
data class EventContact(val name: String, val phone: String, val emergency: Boolean)
data class SignalDetail(val id: String, val status: String, val canHandle: Boolean, val actionedAt: String,
    val resolvedAt: String, val contacts: List<EventContact> = emptyList(), val history: List<String> = emptyList()) {
    val actions: List<String> get() = if (!canHandle) emptyList() else when (status) {
        "VALIDATED", "NOTIFIED", "NOTIFICATION_FAILED" -> listOf("ACKNOWLEDGE", "FALSE_POSITIVE")
        "ACKNOWLEDGED" -> listOf("CONTACT", "FALSE_POSITIVE", "RESOLVE")
        "CONTACTED" -> listOf("FALSE_POSITIVE", "RESOLVE")
        else -> emptyList()
    }
}
data class NotificationState(val family: String = "", val owner: String = "", val user: String = "",
    val busy: Boolean = false, val loaded: Boolean = false, val items: List<InboxItem> = emptyList(),
    val message: String = "", val detail: String = "", val version: Long = 0,
    val inApp: Boolean = true, val push: Boolean = false, val timezone: String = "Asia/Shanghai",
    val quietStart: String = "22:00", val quietEnd: String = "08:00", val event: SignalDetail? = null,
    val sms: Boolean = false, val phone: Boolean = false, val pushMode: String = "MOCK",
    val smsAvailable: Boolean = false, val phoneAvailable: Boolean = false)

class NotificationModel(private val gateway: NotificationGateway, private val scope: CoroutineScope? = null) : ViewModel() {
    private val current = MutableStateFlow(NotificationState())
    val state = current.asStateFlow()
    private val tasks get() = scope ?: viewModelScope
    private var generation = 0
    private var job: Job? = null
    private var polling: Job? = null
    private var expiry: Job? = null
    private var openedEvent: String? = null
    fun clear() {
        generation++; job?.cancel(); polling?.cancel(); expiry?.cancel()
        polling = null; openedEvent = null; current.value = NotificationState()
    }
    fun bind(family: String, owner: String, user: String) {
        if (current.value.family == family && current.value.owner == owner && current.value.user == user) return
        clear(); current.value = NotificationState(family = family, owner = owner, user = user)
    }
    fun startPolling() {
        if (polling?.isActive == true || current.value.owner.isBlank()) return
        polling = tasks.launch { while (isActive) { refresh(); delay(30000) } }
    }
    private fun path() = "/v1/families/${current.value.family}/notification-preferences/${current.value.owner}"
    private fun action(block: suspend (Int) -> Unit) {
        if (current.value.busy || current.value.owner.isBlank()) return
        val stamp = generation
        expiry?.cancel()
        current.value = current.value.copy(busy = true, items = emptyList(), detail = "", event = null, message = "正在同步…")
        job = tasks.launch {
            try { block(stamp) }
            catch (cancelled: CancellationException) { throw cancelled }
            catch (_: Exception) { if (stamp == generation) current.value = current.value.copy(items = emptyList(), detail = "", event = null,
                loaded = false, message = "同步未完成，操作结果未确认。请刷新核对网络、当前授权和事件处理状态；暂不显示旧内容。") }
            finally { if (stamp == generation) current.value = current.value.copy(busy = false) }
        }
    }
    private fun setting(value: JSONObject) {
        require(value.getString("family_id") == current.value.family && value.getString("owner_user_id") == current.value.owner
            && value.getString("recipient_user_id") == current.value.user)
        val channels = value.getJSONArray("channels")
        val values = (0 until channels.length()).map { channels.getString(it) }
        require(values.all { it in listOf("IN_APP", "PUSH", "SMS", "PHONE") })
        current.value = current.value.copy(version = value.getLong("version"), inApp = "IN_APP" in values,
            push = "PUSH" in values, sms = "SMS" in values, phone = "PHONE" in values, timezone = value.getString("timezone"),
            quietStart = if (value.isNull("quiet_hours_start")) "" else value.getString("quiet_hours_start").take(5),
            quietEnd = if (value.isNull("quiet_hours_end")) "" else value.getString("quiet_hours_end").take(5), loaded = true)
    }
    private fun expire(stamp: Int) {
        expiry?.cancel()
        expiry = tasks.launch { delay(30000); if (stamp == generation) current.value = current.value.copy(
            items = emptyList(), detail = "", event = null, message = "等待重新核对当前授权…") }
    }
    fun refresh() = action { stamp ->
        val family = current.value.family; val owner = current.value.owner
        val elder = owner == current.value.user
        val preference = if (elder) null else gateway.call(path())
        val capabilities = if (elder) null else gateway.call("/v1/notification-capabilities").optJSONObject("channels")
        val values = mutableListOf<InboxItem>()
        val notices = if (elder) emptyList() else gateway.list()
        for (event in gateway.events(family)) {
            if (stamp != generation) return@action
            val eventId = event.getString("id")
            require(UUID.fromString(eventId).toString() == eventId)
            if (event.getString("family_id") != family || event.getString("owner_user_id") != owner) continue
            val item = notices.firstOrNull { it.getString("signal_event_id") == eventId }
            val summary = item?.getString("summary").orEmpty(); val explanation = event.getString("summary")
            require(summary.length <= 240 && explanation.length <= 1000)
            val status = item?.getString("status") ?: "NONE"
            require(status in listOf("SENT", "DELIVERED", "READ", "FAILED", "NONE"))
            val deliveries = notices.filter { it.getString("signal_event_id") == eventId }.map { notice ->
                val channel = when (notice.getString("channel")) { "SMS" -> "短信"; "PHONE" -> "语音电话"; "PUSH" -> "推送"; else -> "应用内" }
                val result = when {
                    notice.optString("error_code") == "DELIVERY_UNKNOWN" -> "结果未知，请人工核实（不会自动重发）"
                    notice.optString("error_code") == "CHANNEL_NOT_CONFIGURED" -> "服务未配置或外发关闭"
                    notice.optString("error_code") == "CONTACT_REQUIRED" -> "请登记接收号码或推送主题"
                    notice.optString("error_code") == "PROVIDER_DELIVERY_FAILED" -> "服务商报告发送/呼叫失败"
                    notice.optString("delivery_status") in listOf("busy", "no-answer") -> "忙线或无人接听"
                    notice.optString("delivery_status") == "completed" -> "呼叫结束，仍需人工确认是否联系到本人"
                    notice.optString("status") == "FAILED" -> "发送失败"
                    notice.optString("status") == "DELIVERED" || notice.optString("delivery_status") == "delivered" -> "服务商确认送达"
                    notice.optString("status") == "READ" -> "应用内已读"
                    notice.getString("channel") == "IN_APP" -> "应用内可查看"
                    notice.optBoolean("simulated", true) -> "Mock 模拟发送"
                    else -> "服务商已受理，送达待确认"
                }
                "$channel：$result"
            }
            values.add(InboxItem(item?.getString("id").orEmpty(), eventId, status,
                item?.getString("channel").orEmpty(), summary, explanation, event.getString("status"), deliveries))
        }
        if (stamp == generation) {
            if (preference != null) setting(preference)
            current.value = current.value.copy(items = values, loaded = true, message = if (elder) "已同步家人处理进度。提示识别为 Mock；处理记录由家人提交。" else "已同步 · 事件识别为 Mock；各渠道结果以发送记录为准。",
                pushMode = capabilities?.optString("PUSH", "DISABLED") ?: "MOCK",
                smsAvailable = capabilities?.optString("SMS") == "AVAILABLE", phoneAvailable = capabilities?.optString("PHONE") == "AVAILABLE")
            openedEvent?.let { id ->
                val detail = gateway.call("/v1/signal-events/$id")
                if (stamp == generation) showEvent(detail, id)
            }
            expire(stamp)
        }
    }
    fun save(inApp: Boolean, push: Boolean, zone: String, start: String, end: String, sms: Boolean = false, phone: Boolean = false) = action { stamp ->
        val channels = JSONArray(); if (inApp) channels.put("IN_APP"); if (push) channels.put("PUSH")
        if (sms) channels.put("SMS"); if (phone) channels.put("PHONE")
        val body = JSONObject().put("channels", channels).put("timezone", zone)
            .put("quiet_hours_start", start.ifBlank { null } ?: JSONObject.NULL)
            .put("quiet_hours_end", end.ifBlank { null } ?: JSONObject.NULL)
        val result = gateway.call(path(), "PUT", body, current.value.version)
        if (stamp == generation) { setting(result); current.value = current.value.copy(message = "通知偏好已保存。授权仍由长辈单独决定。") }
    }
    fun read(item: InboxItem) = action { stamp ->
        if (item.id.isNotEmpty() && item.status != "FAILED") {
            val result = gateway.read(item.id, UUID.randomUUID().toString())
            require(result.getString("id") == item.id && result.getString("status") == "READ")
        }
        val detail = gateway.call("/v1/signal-events/${item.eventId}")
        if (stamp != generation) return@action
        openedEvent = item.eventId
        showEvent(detail, item.eventId)
        current.value = current.value.copy(message = "已查看 · 查看通知不等于确认关注或解决。")
        expire(stamp)
    }
    fun openNotification(id: String) = action { stamp ->
        require(UUID.fromString(id).toString() == id)
        val notice = gateway.call("/v1/notifications/$id")
        require(notice.getString("id") == id)
        require(notice.getString("family_id") == current.value.family && notice.getString("owner_user_id") == current.value.owner)
        val eventId = notice.getString("signal_event_id")
        val detail = gateway.call("/v1/signal-events/$eventId")
        if (stamp != generation) return@action
        if (notice.getString("status") != "FAILED") gateway.read(id, UUID.randomUUID().toString())
        if (stamp != generation) return@action
        openedEvent = eventId
        showEvent(detail, eventId)
        current.value = current.value.copy(message = "已打开通知，请核实后处理。查看不等于确认关注。")
        expire(stamp)
    }
    private fun showEvent(detail: JSONObject, id: String) {
        require(detail.getString("id") == id)
        require(detail.getString("family_id") == current.value.family && detail.getString("owner_user_id") == current.value.owner)
        val summary = detail.getString("summary")
        require(summary.length <= 1000)
        val contacts = detail.optJSONArray("contacts") ?: JSONArray()
        val history = detail.optJSONArray("history") ?: JSONArray()
        current.value = current.value.copy(detail = summary, event = SignalDetail(id, detail.getString("status"),
            detail.optBoolean("can_handle", false), detail.optString("actioned_at"), detail.optString("resolved_at"),
            (0 until contacts.length()).map { index -> contacts.getJSONObject(index).let {
                val phone = it.getString("phone"); require(phone.matches(Regex("\\+[1-9][0-9]{6,14}")))
                EventContact(it.getString("display_name"), phone, it.getBoolean("emergency")) } },
            (0 until history.length()).map { index -> history.getJSONObject(index).let {
                "${it.optString("actor_display_name", "家庭成员")} · ${signalActionLabel(it.getString("action"))} · ${it.getString("occurred_at")}" } }))
    }
    fun handle(actionName: String) {
        val event = current.value.event ?: return
        if (actionName !in event.actions) return
        action { stamp ->
            val result = gateway.act(event.id, JSONObject().put("action", actionName).put("expected_status", event.status), UUID.randomUUID().toString())
            if (stamp != generation) return@action
            showEvent(result, event.id)
            current.value = current.value.copy(message = when (actionName) {
                "ACKNOWLEDGE" -> "已确认关注。"
                "CONTACT" -> "已保存您人工确认的联系记录；应用不验证电话是否接通。"
                "FALSE_POSITIVE" -> "已标记误报，尚未发送的通知已取消。"
                else -> "已保存您确认的解决状态。"
            })
            expire(stamp)
        }
    }
    override fun onCleared() { clear(); super.onCleared() }
}

internal fun signalActionLabel(action: String) = when (action) {
    "ACKNOWLEDGE" -> "确认关注"; "CONTACT" -> "人工记录已联系"; "FALSE_POSITIVE" -> "标记误报"; "RESOLVE" -> "标记解决"; else -> action
}
