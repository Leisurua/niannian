package org.example.niannian.feature.conversation

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import org.json.JSONObject
import java.util.UUID

interface ConversationToolsGateway {
    suspend fun call(path: String, method: String = "GET", body: JSONObject? = null, version: Long? = null, reason: String? = null): JSONObject
}

data class ConversationToolsState(val family: String = "", val owner: String = "", val busy: Boolean = false,
    val version: Long = 1, val timezone: String = "Asia/Shanghai", val start: String = "08:00", val end: String = "20:00",
    val quietStart: String = "", val quietEnd: String = "", val cap: Int = 0, val confirmed: Boolean = false,
    val paused: String = "", val loaded: Boolean = false, val message: String = "", val summary: String = "")

class ConversationToolsModel(private val gateway: ConversationToolsGateway, private val scope: CoroutineScope? = null) : ViewModel() {
    suspend fun weeklyReport(family: String, owner: String, week: String, reason: String?): String =
        gateway.call("/v1/reports/weekly?family_id=$family&owner_user_id=$owner&week_start=$week&timezone=Asia%2FShanghai",
            reason = reason).getString("text")
    suspend fun deleteStatistics(family: String) { gateway.call("/v1/reports/data?family_id=$family", "DELETE") }
    private val current = MutableStateFlow(ConversationToolsState())
    val state = current.asStateFlow()
    private var generation = 0
    private var job: Job? = null
    private var expiry: Job? = null
    private val tasks get() = scope ?: viewModelScope
    fun clear() { generation++; job?.cancel(); expiry?.cancel(); current.value = ConversationToolsState() }
    fun bind(family: String, owner: String) {
        if (current.value.family == family && current.value.owner == owner) return
        clear(); current.value = ConversationToolsState(family = family, owner = owner)
    }
    private fun path() = "/v1/families/${current.value.family}/proactive-preferences/${current.value.owner}"
    private fun action(block: suspend () -> Unit) {
        if (current.value.busy || current.value.owner.isEmpty()) return
        val stamp = generation
        current.value = current.value.copy(busy = true, summary = "", message = "")
        job = tasks.launch {
            try { block() }
            catch (cancelled: CancellationException) { throw cancelled }
            catch (_: Exception) { if (generation == stamp) current.value = current.value.copy(summary = "", loaded = false,
                message = "未完成。请检查网络、授权和设置版本后重新读取；离线不展示摘要或提交暂停。") }
            finally { if (generation == stamp) current.value = current.value.copy(busy = false) }
        }
    }
    private fun apply(value: JSONObject) {
        current.value = current.value.copy(version = value.getLong("version"), timezone = value.getString("timezone"),
            start = value.getString("window_start").take(5), end = value.getString("window_end").take(5),
            quietStart = if (value.isNull("quiet_start")) "" else value.getString("quiet_start").take(5),
            quietEnd = if (value.isNull("quiet_end")) "" else value.getString("quiet_end").take(5),
            cap = value.getInt("daily_cap"), confirmed = value.getBoolean("confirmed"),
            paused = if (value.isNull("paused_on")) "" else value.getString("paused_on"), loaded = true)
    }
    fun refresh() = action { val stamp = generation; val result = gateway.call(path()); if (stamp == generation) apply(result) }
    fun propose(zone: String, start: String, end: String, quietStart: String, quietEnd: String, cap: String) = action {
        val stamp = generation
        val body = JSONObject().put("timezone", zone).put("window_start", start).put("window_end", end)
            .put("quiet_start", quietStart.ifBlank { null } ?: JSONObject.NULL).put("quiet_end", quietEnd.ifBlank { null } ?: JSONObject.NULL)
            .put("daily_cap", cap.toInt())
        val result = gateway.call(path(), "PUT", body, current.value.version)
        if (stamp == generation) { apply(result); current.value = current.value.copy(message = "设置已提出，等待长辈本人确认。") }
    }
    fun confirm() = action {
        val stamp = generation
        val result = gateway.call(path() + "/confirm", "POST", JSONObject().put("version", current.value.version))
        if (stamp == generation) apply(result)
    }
    fun pause() = action {
        val stamp = generation
        val result = gateway.call(path() + "/pause-today", "POST", JSONObject())
        if (stamp == generation) { apply(result); current.value = current.value.copy(message = "今天已减少主动互动，必要提醒和紧急联系仍可用。") }
    }
    fun summary(id: String, reason: String?, request: Boolean = false) = action {
        require(UUID.fromString(id).toString() == id)
        require(reason == null || reason in listOf("FAMILY_CHECK_IN", "FOLLOW_UP"))
        val stamp = generation
        if (request) gateway.call("/v1/conversations/$id/summary", "POST", reason = reason)
        val result = gateway.call("/v1/conversations/$id", reason = reason)
        require(result.getString("family_id") == current.value.family && result.getString("owner_user_id") == current.value.owner)
        if (stamp != generation) return@action
        val content = if (result.optString("summary_status") == "READY" && !result.isNull("summary")) result.optString("summary") else ""
        require(content.length <= 1000)
        current.value = current.value.copy(summary = content, message = if (content.isEmpty()) "这次还没有可回顾的摘要；可能正在生成、已过期或尚未授权。" else "Mock · 这是本次会话摘要。访问已记录；不会展示逐字稿。")
        expiry?.cancel()
        expiry = tasks.launch { delay(5000); if (stamp == generation) current.value = current.value.copy(summary = "",
            message = "摘要已隐藏。再次查看会重新检查当前授权并记录访问。") }
    }
    override fun onCleared() { clear(); super.onCleared() }
}
