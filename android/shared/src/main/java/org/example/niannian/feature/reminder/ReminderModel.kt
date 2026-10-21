package org.example.niannian.feature.reminder

import org.example.niannian.data.ApiFailure
import org.example.niannian.core.common.parseApiInstant

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import org.json.JSONArray
import org.json.JSONObject
import java.time.Instant
import java.time.LocalDate
import java.time.LocalTime
import java.time.ZoneId

interface ReminderGateway {
    suspend fun list(path: String): List<JSONObject>
    suspend fun call(path: String, method: String = "GET", body: JSONObject? = null, key: String? = null, version: Long? = null): JSONObject
}
class EphemeralReminderStore : ReminderStore {
    private var data = "{}"
    override suspend fun load() = JSONObject(data)
    override suspend fun save(value: JSONObject) { data = value.toString() }
    override suspend fun clear() { data = "{}" }
}
data class ReminderCard(val key: String, val reminderId: String, val title: String, val content: String, val time: String,
    val status: String, val pending: Boolean, val failed: Boolean, val medication: Boolean, val due: Boolean)
data class ReminderState(val family: String = "", val user: String = "", val busy: Boolean = false, val offline: Boolean = false,
    val cards: List<ReminderCard> = emptyList(), val rules: List<JSONObject> = emptyList(), val message: String = "", val error: String = "")

class ReminderModel(private val gateway: ReminderGateway, store: ReminderStore, val elder: Boolean,
    private val taskScope: CoroutineScope? = null, private val clock: () -> Instant = Instant::now,
    private val onCacheChanged: () -> Unit = {}) : ViewModel() {
    private val ledger = ReminderLedger(store, clock)
    private val current = MutableStateFlow(ReminderState())
    val state = current.asStateFlow()
    private var generation = 0
    private var job: Job? = null
    fun hide() { generation++; job?.cancel(); current.value = ReminderState() }
    fun bind(family: String, user: String): Job? {
        if (current.value.family == family && current.value.user == user) return null
        hide(); current.value = ReminderState(family = family, user = user)
        return action { stamp -> ledger.bind(family, user); sync(stamp) }
    }
    private fun action(work: suspend (Int) -> Unit): Job? {
        if (current.value.busy || current.value.family.isBlank()) return null
        val stamp = generation
        current.value = current.value.copy(busy = true, error = "", message = "")
        job = (taskScope ?: viewModelScope).launch {
            try { work(stamp) }
            catch (cancelled: CancellationException) { throw cancelled }
            catch (failure: Exception) {
                if (stamp == generation) {
                    if (failure is ApiFailure && failure.status in setOf(401, 403, 404)) {
                        ledger.clear(); current.value = current.value.copy(cards = emptyList(), rules = emptyList(), error = "登录或授权已失效，请重新确认。")
                    } else current.value = current.value.copy(cards = emptyList(), rules = emptyList(), error = "提醒未完成，请检查连接、时间或输入后重试。")
                }
            } finally { if (stamp == generation) current.value = current.value.copy(busy = false) }
        }
        return job
    }
    private suspend fun show(stamp: Int) {
        val data = ledger.snapshot()
        if (stamp != generation) return
        val now = clock()
        val rules = data.optJSONArray("rules")?.objects().orEmpty()
        val byId = rules.associateBy { it.getString("id") }
        val entries = data.optJSONObject("occurrences") ?: JSONObject()
        val cards = entries.keys().asSequence().mapNotNull { key ->
            val e = entries.getJSONObject(key)
            val r = byId[e.getString("reminder_id")] ?: return@mapNotNull null
            val instant = parseApiInstant(e.optString("next_due_at").takeIf { e.getString("status") == "LATER" && it.isNotBlank() } ?: e.getString("scheduled_at"))
            val action = e.optJSONObject("action")
            ReminderCard(key, r.getString("id"), r.getString("title"), r.getString("content"),
                instant.atZone(ZoneId.of(r.getString("timezone"))).toString(), e.getString("status"), action != null,
                action?.optBoolean("failed") == true || (action?.optInt("attempts") ?: 0) >= 5,
                r.getString("type") == "MEDICATION", instant <= now && !ReminderCalendar.inQuietHours(now, parseRule(r).quiet))
        }.sortedBy { it.time }.toList()
        current.value = current.value.copy(cards = cards, rules = rules, message = data.optString("notice"))
    }
    private suspend fun sync(stamp: Int) {
        val bound = current.value
        try {
            val rows = gateway.list("/v1/reminders?family_id=${bound.family}&limit=100" + if (elder) "&owner_user_id=${bound.user}" else "")
            if (stamp != generation) return
            rows.forEach { r -> r.put("executions", JSONArray(gateway.list("/v1/reminders/${r.getString("id")}/executions?limit=100"))) }
            if (stamp != generation) return
            if (!elder) {
                current.value = current.value.copy(rules = rows, cards = emptyList(), offline = false)
                return
            }
            ledger.bind(bound.family, bound.user)
            ledger.refresh(bound.family, bound.user, rows)
            onCacheChanged()
            current.value = current.value.copy(offline = false)
            val entries = ledger.snapshot().optJSONObject("occurrences") ?: JSONObject()
            for (key in entries.keys().asSequence().toList()) {
                if (stamp != generation) return
                val pending = ledger.attempted(key) ?: continue
                val action = pending.getJSONObject("action")
                try {
                    val result = gateway.call("/v1/reminders/${pending.getString("reminder_id")}/offline-feedback", "POST", action.getJSONObject("body"), action.getString("key"))
                    if (stamp != generation) return
                    ledger.acknowledge(key, action.getString("key"), result)
                } catch (cancelled: CancellationException) { throw cancelled }
                catch (failure: ApiFailure) {
                    if (failure.status == 401 || failure.status == 403 || failure.status == 404) throw failure
                    if (failure.status in 400..499 && failure.status !in setOf(408, 429)) ledger.conflict(key)
                    else current.value = current.value.copy(offline = true)
                } catch (_: Exception) { current.value = current.value.copy(offline = true) }
            }
            show(stamp)
        } catch (cancelled: CancellationException) { throw cancelled }
        catch (failure: Exception) {
            if (failure is ApiFailure && failure.status in setOf(401, 403, 404)) throw failure
            if (stamp == generation) {
                current.value = current.value.copy(offline = true, error = "当前无法更新提醒；仅可使用有效期内的本人缓存。")
                if (elder) show(stamp) else current.value = current.value.copy(rules = emptyList(), cards = emptyList())
            }
        }
    }
    fun refresh() = action { sync(it) }
    fun retry(key: String) = action { stamp -> ledger.manualRetry(key); sync(stamp) }
    fun tick() = action { if (elder) show(it) }
    fun feedback(key: String, status: String, confirmed: Boolean = false) = action { stamp ->
        val card = current.value.cards.single { it.key == key }
        require(elder && card.due && (!card.medication || status != "SKIPPED" || confirmed))
        ledger.feedback(key, status, if (status == "LATER") clock().plusSeconds(600) else null)
        onCacheChanged()
        show(stamp)
        current.value = current.value.copy(message = "反馈已安全保存在本机，等待服务端确认。")
        sync(stamp)
        if (stamp == generation && !current.value.offline && current.value.cards.any { it.key == key && !it.pending })
            current.value = current.value.copy(message = "反馈已同步至服务端。")
    }
    fun save(owner: String, title: String, content: String, date: String, time: String, zone: String,
        type: String, daily: Boolean, confirmed: Boolean, editing: JSONObject? = null,
        onSaved: (() -> Unit)? = null) = action { stamp ->
        require(title.isNotBlank() && title.length <= 240 && content.length <= 2000)
        require(type != "MEDICATION" || !elder && confirmed)
        LocalDate.parse(date); LocalTime.parse(time); ZoneId.of(zone)
        val body = JSONObject().put("family_id", current.value.family).put("owner_user_id", owner).put("type", type)
            .put("title", title).put("content", content).put("start_date", date).put("schedule_time_local", time)
            .put("timezone", zone).put("recurrence_kind", if (daily) "DAILY" else "ONCE").put("recurrence_interval", 1)
        if (editing == null) gateway.call("/v1/reminders", "POST", body)
        else gateway.call("/v1/reminders/${editing.getString("id")}", "PATCH", body, version = editing.getLong("version"))
        if (stamp == generation) {
            onSaved?.invoke()
            sync(stamp)
            if (stamp == generation) {
                current.value = current.value.copy(message = if (current.value.offline) "提醒已保存，列表待重新读取。" else "提醒已保存并同步。")
            }
        }
    }
    fun delete(id: String) = action { stamp ->
        gateway.call("/v1/reminders/$id", "DELETE")
        if (stamp == generation) sync(stamp)
    }
    fun executions(id: String) = action { stamp ->
        val rows = gateway.list("/v1/reminders/$id/executions?limit=100")
        if (stamp == generation) current.value = current.value.copy(message = if (rows.isEmpty()) "尚无执行记录。" else rows.take(10).joinToString("\n") {
            it.getString("scheduled_at") + " · " + feedbackLabel(it.getString("feedback_status"))
        })
    }
}

fun feedbackLabel(status: String) = when (status) {
    "DONE" -> "已反馈完成"; "LATER" -> "稍后提醒"; "SKIPPED" -> "已反馈跳过（不代表未服药）"
    "NO_RESPONSE" -> "尚未收到反馈"; else -> "等待反馈"
}
