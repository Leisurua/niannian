package org.example.niannian.feature.reminder

import org.example.niannian.core.common.parseApiInstant
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import org.json.JSONArray
import org.json.JSONObject
import java.time.Instant
import java.time.LocalDate
import java.time.LocalTime
import java.time.ZoneId
import java.util.UUID
import java.security.MessageDigest

private fun payloadHash(body: JSONObject): String {
    val canonical = body.keys().asSequence().sorted().joinToString("\n") { key -> key + ":" + JSONObject.quote(body.get(key).toString()) }
    return MessageDigest.getInstance("SHA-256").digest(canonical.toByteArray(Charsets.UTF_8))
        .joinToString("") { "%02x".format(java.util.Locale.ROOT, it) }
}

internal fun JSONArray.objects() = (0 until length()).map { getJSONObject(it) }
internal fun parseRule(r: JSONObject): ReminderRule {
    val q = r.optJSONObject("quiet_hours")?.let { ReminderQuietHours(LocalTime.parse(it.getString("start")), LocalTime.parse(it.getString("end")), it.getString("timezone")) }
    val days = r.optJSONArray("days_of_week") ?: JSONArray()
    return ReminderRule(LocalTime.parse(r.getString("schedule_time_local")), r.getString("timezone"), LocalDate.parse(r.getString("start_date")),
        r.optString("end_date").takeUnless { it.isBlank() || it == "null" }?.let(LocalDate::parse), r.getString("recurrence_kind"),
        r.optInt("recurrence_interval", 1), (0 until days.length()).map { days.getInt(it) }, q)
}

/** Every mutation persists one encrypted snapshot including both feedback and pending action. */
class ReminderLedger(private val store: ReminderStore, private val clock: () -> Instant = Instant::now) {
    companion object { private val mutex = Mutex() }
    private suspend fun <T> transaction(work: (JSONObject, Instant) -> T): T = mutex.withLock {
        val data = store.load()
        val now = clock()
        val last = data.optLong("last_seen", now.epochSecond)
        if (now.epochSecond < last) {
            store.clear(); throw IllegalStateException("设备时间发生倒退，请联网核对提醒。")
        }
        val result = work(data, now)
        data.put("last_seen", now.epochSecond)
        store.save(data)
        result
    }
    suspend fun clear() = mutex.withLock { store.clear() }
    suspend fun bind(family: String, owner: String) = transaction { data, _ ->
        if (data.optString("family") != family || data.optString("owner") != owner) {
            data.keys().asSequence().toList().filter { it != "_storage_epoch" }.forEach { data.remove(it) }
            data.put("family", family).put("owner", owner).put("rules", JSONArray()).put("occurrences", JSONObject())
        }
    }
    suspend fun refresh(family: String, owner: String, rules: List<JSONObject>) = transaction { data, now ->
        require(data.optString("family") == family && data.optString("owner") == owner)
        require(rules.size <= 100)
        rules.forEach { require(it.getString("family_id") == family && it.getString("owner_user_id") == owner) }
        val cached = JSONArray()
        rules.filter { it.getBoolean("active") }.forEach { original ->
            val r = JSONObject(original.toString())
            val parsed = parseRule(r)
            val end = parsed.endDate?.plusDays(1)?.atStartOfDay(ZoneId.of(parsed.timezone))?.toInstant()
            val expiry = minOf(now.plusSeconds(86400), end ?: now.plusSeconds(86400))
            r.put("cache_expiry", expiry.epochSecond)
            cached.put(r)
        }
        val occurrences = data.optJSONObject("occurrences") ?: JSONObject()
        val versions = cached.objects().associate { it.getString("id") to it.getLong("version") }
        occurrences.keys().asSequence().toList().forEach { key ->
            val item = occurrences.getJSONObject(key)
            if (versions[item.getString("reminder_id")] != item.getLong("version")) {
                if (item.has("action")) data.put("notice", "提醒已更新或无权访问，旧反馈未上传，请核对。")
                occurrences.remove(key)
            }
        }
        data.put("rules", cached).put("occurrences", occurrences).put("synced_at", now.epochSecond)
        cached.objects().forEach { r ->
            val parsed = parseRule(r)
            val server = r.optJSONArray("executions")?.objects().orEmpty().associateBy { parseApiInstant(it.getString("scheduled_at")) }
            ReminderCalendar.occurrences(parsed, now.minusSeconds(86400), now.plusSeconds(86400)).forEach { occurrence ->
                val known = server[occurrence.scheduledAt]
                if (occurrence.scheduledAt < now && known == null) return@forEach
                val key = r.getString("id") + ":" + occurrence.occurrenceKey
                val item = occurrences.optJSONObject(key) ?: JSONObject().put("reminder_id", r.getString("id"))
                    .put("version", r.getLong("version")).put("scheduled_at", occurrence.scheduledAt.toString())
                    .put("status", "PENDING").put("source", "OFFLINE").put("presented", false)
                if (known != null && !item.has("action")) {
                    item.put("status", known.getString("feedback_status")).put("source", known.getString("source"))
                    if (known.has("next_due_at")) item.put("next_due_at", known.getString("next_due_at"))
                }
                occurrences.put(key, item)
            }
            r.remove("executions")
        }
    }
    suspend fun snapshot(): JSONObject = transaction { data, now ->
        val rules = data.optJSONArray("rules") ?: JSONArray()
        val entries = data.optJSONObject("occurrences") ?: JSONObject()
        entries.keys().asSequence().toList().forEach { key ->
            val item = entries.getJSONObject(key)
            val action = item.optJSONObject("action")
            if (action != null && now.epochSecond >= action.getLong("expires_at")) {
                val next = item.optJSONObject("next_action")
                if (next != null && now.epochSecond < next.getLong("expires_at")) {
                    item.put("action", next); item.remove("next_action")
                } else entries.remove(key)
                data.put("notice", "部分反馈未同步且已过期，请联网核对。")
            } else if (action == null && parseApiInstant(item.getString("scheduled_at")) < now.minusSeconds(86400)) entries.remove(key)
        }
        val fresh = rules.objects().filter { now.epochSecond < it.getLong("cache_expiry") }
        if (fresh.size < rules.length()) data.put("notice", "部分提醒缓存已过期，请联网更新。")
        val validIds = fresh.map { it.getString("id") }.toSet()
        entries.keys().asSequence().toList().forEach { key ->
            val item = entries.getJSONObject(key)
            if (!item.has("action") && item.getString("reminder_id") !in validIds) entries.remove(key)
        }
        if (fresh.isEmpty() && entries.length() == 0) {
            data.remove("family"); data.remove("owner"); data.remove("synced_at")
        }
        data.put("rules", JSONArray(fresh)).put("occurrences", entries)
        JSONObject(data.toString())
    }
    suspend fun notificationCandidates(): List<String> {
        val data = snapshot()
        val now = clock()
        val rules = data.optJSONArray("rules")?.objects().orEmpty().associateBy { it.getString("id") }
        val entries = data.optJSONObject("occurrences") ?: return emptyList()
        return entries.keys().asSequence().filter { key ->
            val item = entries.getJSONObject(key)
            val rule = rules[item.getString("reminder_id")]
            val due = parseApiInstant(if (item.getString("status") == "LATER") item.getString("next_due_at") else item.getString("scheduled_at"))
            rule != null && item.getString("status") !in setOf("DONE", "SKIPPED") && !item.optBoolean("presented") &&
                due <= now && !ReminderCalendar.inQuietHours(now, parseRule(rule).quiet)
        }.toList()
    }
    suspend fun recordNotificationSubmission(keys: List<String>) = transaction { data, _ ->
        keys.forEach { data.optJSONObject("occurrences")?.optJSONObject(it)?.put("presented", true) }
    }
    /** Wake for actual reminders or cache expiry instead of consuming idle-alarm quota by polling. */
    suspend fun nextCheckAt(): Instant? {
        val data = snapshot()
        val now = clock()
        val rules = data.optJSONArray("rules")?.objects().orEmpty().associateBy { it.getString("id") }
        val times = rules.values.map { Instant.ofEpochSecond(it.getLong("cache_expiry")) }.toMutableList()
        val entries = data.optJSONObject("occurrences") ?: return times.minOrNull()
        for (key in entries.keys()) {
            val item = entries.getJSONObject(key)
            listOf("action", "next_action").forEach { slot ->
                item.optJSONObject(slot)?.let { times.add(Instant.ofEpochSecond(it.getLong("expires_at"))) }
            }
            val rule = rules[item.getString("reminder_id")] ?: continue
            if (item.getString("status") in setOf("DONE", "SKIPPED") || item.optBoolean("presented")) continue
            var due = maxOf(now, parseApiInstant(if (item.getString("status") == "LATER") item.getString("next_due_at") else item.getString("scheduled_at")))
            val quiet = parseRule(rule).quiet
            if (ReminderCalendar.inQuietHours(due, quiet)) {
                val local = due.atZone(ZoneId.of(quiet!!.timezone))
                val day = if (quiet.start > quiet.end && local.toLocalTime() >= quiet.start) local.toLocalDate().plusDays(1) else local.toLocalDate()
                due = day.atTime(quiet.end).atZone(local.zone).toInstant()
            }
            if (due < Instant.ofEpochSecond(rule.getLong("cache_expiry"))) times.add(due)
        }
        return times.minOrNull()
    }
    suspend fun feedback(key: String, status: String, next: Instant? = null) = transaction { data, now ->
        require(status in setOf("DONE", "LATER", "SKIPPED"))
        require(if (status == "LATER") next != null && next > now && next <= now.plusSeconds(86400) else next == null)
        val item = data.getJSONObject("occurrences").getJSONObject(key)
        val rule = data.getJSONArray("rules").objects().single { it.getString("id") == item.getString("reminder_id") }
        require(now.epochSecond < rule.getLong("cache_expiry") && parseApiInstant(item.getString("scheduled_at")) <= now)
        require(item.getString("status") !in setOf("DONE", "SKIPPED"))
        require(!item.has("action") || item.getString("status") == "LATER" && status in setOf("DONE", "SKIPPED") && !item.has("next_action"))
        val body = JSONObject().put("reminder_version", item.getLong("version")).put("scheduled_at", item.getString("scheduled_at"))
            .put("feedback_at", now.toString()).put("status", status)
        next?.let { body.put("next_due_at", it.toString()); item.put("next_due_at", it.toString()) }
        if (status == "LATER") item.put("presented", false)
        val slot = if (item.has("action")) "next_action" else "action"
        item.put("status", status).put(slot, JSONObject().put("key", UUID.randomUUID().toString()).put("body", body).put("payload_hash", payloadHash(body))
            .put("expires_at", now.plusSeconds(86400).epochSecond).put("attempts", 0).put("retry_at", now.epochSecond).put("failed", false))
    }
    suspend fun attempted(key: String): JSONObject? = transaction { data, now ->
        val item = data.optJSONObject("occurrences")?.optJSONObject(key) ?: return@transaction null
        val action = item.optJSONObject("action") ?: return@transaction null
        if (now.epochSecond >= action.getLong("expires_at") || action.getBoolean("failed") || action.getInt("attempts") >= 5 || now.epochSecond < action.getLong("retry_at")) return@transaction null
        require(action.getString("payload_hash") == payloadHash(action.getJSONObject("body"))) { "Pending payload changed" }
        val attempts = action.getInt("attempts") + 1
        action.put("attempts", attempts).put("retry_at", now.epochSecond + minOf(300L, 1L shl attempts))
        JSONObject(item.toString())
    }
    suspend fun acknowledge(key: String, actionKey: String, result: JSONObject) = transaction { data, _ ->
        val item = data.optJSONObject("occurrences")?.optJSONObject(key) ?: return@transaction
        if (item.optJSONObject("action")?.optString("key") != actionKey) return@transaction
        UUID.fromString(result.getString("id"))
        require(result.getString("reminder_id") == item.getString("reminder_id"))
        require(parseApiInstant(result.getString("scheduled_at")) == parseApiInstant(item.getString("scheduled_at")))
        require(result.getString("feedback_status") in setOf("PENDING", "LATER", "DONE", "SKIPPED", "NO_RESPONSE"))
        require(result.getString("source") in setOf("ONLINE", "OFFLINE"))
        item.put("source", result.getString("source"))
        val next = item.optJSONObject("next_action")
        if (next != null) { item.put("action", next); item.remove("next_action") }
        else { item.put("status", result.getString("feedback_status")); item.remove("action") }
    }
    suspend fun conflict(key: String) = transaction { data, _ ->
        val item = data.optJSONObject("occurrences")?.optJSONObject(key)
        val next = item?.optJSONObject("next_action")
        if (next != null) { item.put("action", next); item.remove("next_action") }
        else item?.optJSONObject("action")?.put("failed", true)
        data.put("notice", "反馈未被服务端确认，请联网核对；不会自动覆盖原记录。")
    }
    suspend fun manualRetry(key: String) = transaction { data, now ->
        val item = data.getJSONObject("occurrences").getJSONObject(key)
        val action = item.optJSONObject("action") ?: return@transaction
        require(now.epochSecond < action.getLong("expires_at"))
        if (action.getBoolean("failed")) {
            item.remove("action"); item.remove("next_due_at"); item.put("status", "PENDING")
        } else action.put("attempts", 0).put("retry_at", now.epochSecond)
    }
}
