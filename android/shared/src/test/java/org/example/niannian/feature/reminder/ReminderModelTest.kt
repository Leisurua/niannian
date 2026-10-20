package org.example.niannian.feature.reminder

import org.example.niannian.data.ApiFailure

import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.yield
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import java.io.IOException
import java.time.Instant

class ReminderModelTest {
    private var now = Instant.parse("2026-10-15T00:00:00Z")
    private fun rule() = JSONObject().put("id", "rule").put("family_id", "family").put("owner_user_id", "elder")
        .put("title", "虚构提醒").put("content", "虚构内容").put("type", "WATER").put("version", 1).put("active", true)
        .put("schedule_time_local", "00:01").put("timezone", "UTC").put("start_date", "2026-10-15")
        .put("recurrence_kind", "DAILY").put("recurrence_interval", 1)
    private inner class Gateway : ReminderGateway {
        var failure: Exception? = null
        var gate: CompletableDeferred<Unit>? = null
        val keys = mutableListOf<String>()
        override suspend fun list(path: String): List<JSONObject> {
            gate?.await(); failure?.let { throw it }
            return if (path.contains("/executions")) emptyList() else listOf(rule())
        }
        override suspend fun call(path: String, method: String, body: JSONObject?, key: String?, version: Long?): JSONObject {
            failure?.let { throw it }; keys += key!!
            return JSONObject().put("id", "00000000-0000-7000-8000-000000000001").put("reminder_id", "rule")
                .put("scheduled_at", body!!.getString("scheduled_at")).put("feedback_status", body.getString("status")).put("source", "OFFLINE")
        }
    }
    @Test fun offlineFeedbackSurvivesModelRestartAndAcknowledgesOnce() = runBlocking {
        val gateway = Gateway(); val store = EphemeralReminderStore()
        val model = ReminderModel(gateway, store, true, this, { now })
        model.bind("family", "elder")!!.join(); now = now.plusSeconds(120)
        model.tick()!!.join(); val key = model.state.value.cards.single().key
        gateway.failure = IOException("offline")
        model.feedback(key, "DONE")!!.join()
        assertTrue(model.state.value.offline)
        assertTrue(model.state.value.cards.single { it.key == key }.pending)
        model.hide()
        val restarted = ReminderModel(gateway, store, true, this, { now })
        restarted.bind("family", "elder")!!.join()
        assertTrue(restarted.state.value.cards.single { it.key == key }.pending)
        gateway.failure = null
        restarted.refresh()!!.join()
        assertFalse(restarted.state.value.cards.single { it.key == key }.pending)
        restarted.refresh()!!.join()
        assertEquals(1, gateway.keys.size)
    }
    @Test fun permissionDenialClearsStoredDataAndCannotRestoreOffline() = runBlocking {
        val gateway = Gateway(); val store = EphemeralReminderStore()
        val model = ReminderModel(gateway, store, true, this, { now })
        model.bind("family", "elder")!!.join(); assertFalse(model.state.value.rules.isEmpty())
        gateway.failure = ApiFailure(403, "PERMISSION_DENIED", "授权已撤回"); model.refresh()!!.join()
        assertTrue(model.state.value.cards.isEmpty()); assertEquals(0, store.load().length())
        gateway.failure = IOException("offline"); model.refresh()!!.join()
        assertTrue(model.state.value.cards.isEmpty())
    }
    @Test fun familyOfflineNeverDisplaysCachedHealthContent() = runBlocking {
        val gateway = Gateway(); val model = ReminderModel(gateway, EphemeralReminderStore(), false, this, { now })
        model.bind("family", "child")!!.join(); assertFalse(model.state.value.rules.isEmpty())
        gateway.failure = IOException("offline"); model.refresh()!!.join()
        assertTrue(model.state.value.rules.isEmpty()); assertTrue(model.state.value.cards.isEmpty())
    }
    @Test fun oldResponseCannotRepopulateAfterBackgroundClear() = runBlocking {
        val gateway = Gateway(); val model = ReminderModel(gateway, EphemeralReminderStore(), true, this, { now })
        val gate = CompletableDeferred<Unit>(); gateway.gate = gate
        val work = model.bind("family", "elder")!!; yield(); model.hide(); gate.complete(Unit); work.join()
        assertTrue(model.state.value.family.isEmpty()); assertTrue(model.state.value.rules.isEmpty())
    }
}
