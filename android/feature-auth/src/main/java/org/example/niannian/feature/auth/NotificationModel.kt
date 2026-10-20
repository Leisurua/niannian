package org.example.niannian.feature.auth

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
    suspend fun call(path: String, method: String = "GET", body: JSONObject? = null, version: Long? = null): JSONObject
    suspend fun read(id: String, key: String): JSONObject
}

data class InboxItem(val id: String, val eventId: String, val status: String, val channel: String,
    val summary: String, val explanation: String)
data class NotificationState(val family: String = "", val owner: String = "", val user: String = "",
    val busy: Boolean = false, val loaded: Boolean = false, val items: List<InboxItem> = emptyList(),
    val message: String = "", val detail: String = "", val version: Long = 0,
    val inApp: Boolean = true, val push: Boolean = false, val timezone: String = "Asia/Shanghai",
    val quietStart: String = "22:00", val quietEnd: String = "08:00")

class NotificationModel(private val gateway: NotificationGateway, private val scope: CoroutineScope? = null) : ViewModel() {
    private val current = MutableStateFlow(NotificationState())
    val state = current.asStateFlow()
    private val tasks get() = scope ?: viewModelScope
    private var generation = 0
    private var job: Job? = null
    private var polling: Job? = null
    private var expiry: Job? = null
    fun clear() {
        generation++; job?.cancel(); polling?.cancel(); expiry?.cancel()
        polling = null; current.value = NotificationState()
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
        current.value = current.value.copy(busy = true, items = emptyList(), detail = "", message = "正在同步…")
        job = tasks.launch {
            try { block(stamp) }
            catch (cancelled: CancellationException) { throw cancelled }
            catch (_: Exception) { if (stamp == generation) current.value = current.value.copy(items = emptyList(), detail = "",
                loaded = false, message = "同步未完成。请检查网络和当前授权；暂不显示旧内容。") }
            finally { if (stamp == generation) current.value = current.value.copy(busy = false) }
        }
    }
    private fun setting(value: JSONObject) {
        require(value.getString("family_id") == current.value.family && value.getString("owner_user_id") == current.value.owner
            && value.getString("recipient_user_id") == current.value.user)
        val channels = value.getJSONArray("channels")
        val values = (0 until channels.length()).map { channels.getString(it) }
        require(values.all { it in listOf("IN_APP", "PUSH") })
        current.value = current.value.copy(version = value.getLong("version"), inApp = "IN_APP" in values,
            push = "PUSH" in values, timezone = value.getString("timezone"),
            quietStart = if (value.isNull("quiet_hours_start")) "" else value.getString("quiet_hours_start").take(5),
            quietEnd = if (value.isNull("quiet_hours_end")) "" else value.getString("quiet_hours_end").take(5), loaded = true)
    }
    private fun expire(stamp: Int) {
        expiry?.cancel()
        expiry = tasks.launch { delay(30000); if (stamp == generation) current.value = current.value.copy(
            items = emptyList(), detail = "", message = "等待重新核对当前授权…") }
    }
    fun refresh() = action { stamp ->
        val family = current.value.family; val owner = current.value.owner
        val preference = gateway.call(path())
        val values = mutableListOf<InboxItem>()
        for (item in gateway.list()) {
            if (stamp != generation) return@action
            val eventId = item.getString("signal_event_id")
            require(UUID.fromString(eventId).toString() == eventId)
            val event = gateway.call("/v1/signal-events/$eventId")
            if (stamp != generation) return@action
            if (event.getString("family_id") != family || event.getString("owner_user_id") != owner) continue
            val summary = item.getString("summary"); val explanation = event.getString("summary")
            require(summary.length <= 240 && explanation.length <= 1000)
            require(item.getString("status") in listOf("SENT", "DELIVERED", "READ", "FAILED"))
            values.add(InboxItem(item.getString("id"), eventId, item.getString("status"), item.getString("channel"), summary, explanation))
        }
        if (stamp == generation) {
            setting(preference)
            current.value = current.value.copy(items = values, message = "已同步 · Mock 演示，未验证设备推送到达。")
            expire(stamp)
        }
    }
    fun save(inApp: Boolean, push: Boolean, zone: String, start: String, end: String) = action { stamp ->
        val channels = JSONArray(); if (inApp) channels.put("IN_APP"); if (push) channels.put("PUSH")
        val body = JSONObject().put("channels", channels).put("timezone", zone)
            .put("quiet_hours_start", start.ifBlank { null } ?: JSONObject.NULL)
            .put("quiet_hours_end", end.ifBlank { null } ?: JSONObject.NULL)
        val result = gateway.call(path(), "PUT", body, current.value.version)
        if (stamp == generation) { setting(result); current.value = current.value.copy(message = "通知偏好已保存。授权仍由长辈单独决定。") }
    }
    fun read(item: InboxItem) = action { stamp ->
        val result = gateway.read(item.id, UUID.randomUUID().toString())
        require(result.getString("id") == item.id && result.getString("status") == "READ")
        val detail = gateway.call("/v1/signal-events/${item.eventId}")
        if (stamp != generation) return@action
        require(detail.getString("family_id") == current.value.family && detail.getString("owner_user_id") == current.value.owner)
        val summary = detail.getString("summary")
        require(summary.length <= 1000)
        current.value = current.value.copy(detail = summary, message = "已读 · 仅表示您查看了这条通知。")
        expire(stamp)
    }
    override fun onCleared() { clear(); super.onCleared() }
}
