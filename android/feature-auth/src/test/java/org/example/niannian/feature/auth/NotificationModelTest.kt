package org.example.niannian.feature.auth

import kotlinx.coroutines.*
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

class NotificationModelTest {
    private val eventId = "0192f1e4-6ed8-7c21-a4c1-5d58db7c3001"
    private val id = "0192f1e4-6ed8-7c21-a4c1-5d58db7c3002"
    private inner class Gateway : NotificationGateway {
        var family = "family"; var fail = false; var wait: CompletableDeferred<Unit>? = null
        var readCount = 0; var lastBody: JSONObject? = null; var lastVersion: Long? = null
        override suspend fun list(): List<JSONObject> {
            wait?.await(); if (fail) error("offline")
            return listOf(JSONObject().put("id", id).put("signal_event_id", eventId).put("status", "SENT")
                .put("channel", "IN_APP").put("summary", "Mock · 有关注提示"))
        }
        override suspend fun call(path: String, method: String, body: JSONObject?, version: Long?): JSONObject {
            if (fail) error("offline")
            if (path.startsWith("/v1/signal-events")) return JSONObject().put("family_id", family).put("owner_user_id", "elder")
                .put("summary", "Mock · 请先联系家人核实")
            lastBody = body; lastVersion = version
            return JSONObject().put("family_id", "family").put("owner_user_id", "elder").put("recipient_user_id", "child")
                .put("channels", JSONArray(listOf("IN_APP"))).put("timezone", "Asia/Shanghai").put("version", if (method == "PUT") 1 else 0)
                .put("quiet_hours_start", JSONObject.NULL).put("quiet_hours_end", JSONObject.NULL)
        }
        override suspend fun read(id: String, key: String): JSONObject {
            java.util.UUID.fromString(key); readCount++
            return JSONObject().put("id", id).put("status", "READ")
        }
    }
    @Test fun refreshAndReadShowOnlyCurrentAuthorizedFamily() = runBlocking {
        val gateway = Gateway(); val model = NotificationModel(gateway, this)
        model.bind("family", "elder", "child"); model.refresh(); yield()
        assertEquals(1, model.state.value.items.size)
        assertTrue(model.state.value.message.contains("Mock"))
        model.read(model.state.value.items.single()); yield()
        assertEquals(1, gateway.readCount)
        assertTrue(model.state.value.detail.contains("核实"))
        model.clear(); assertEquals("", model.state.value.detail)
    }
    @Test fun otherFamilyIsFilteredAndFailureClearsAllOldContent() = runBlocking {
        val gateway = Gateway(); val model = NotificationModel(gateway, this)
        model.bind("family", "elder", "child"); model.refresh(); yield()
        gateway.family = "other"; model.refresh(); yield()
        assertTrue(model.state.value.items.isEmpty())
        gateway.family = "family"; model.refresh(); yield()
        assertFalse(model.state.value.items.isEmpty())
        gateway.fail = true; model.refresh(); yield()
        assertTrue(model.state.value.items.isEmpty()); assertFalse(model.state.value.loaded)
        assertTrue(model.state.value.message.contains("同步未完成"))
        model.clear()
    }
    @Test fun familySwitchAndBackgroundClearCannotRestoreLateResults() = runBlocking {
        val gateway = Gateway(); gateway.wait = CompletableDeferred()
        val model = NotificationModel(gateway, this)
        model.bind("family", "elder", "child"); model.refresh(); yield()
        model.bind("other", "elder", "child"); gateway.wait!!.complete(Unit); yield()
        assertEquals("other", model.state.value.family); assertTrue(model.state.value.items.isEmpty())
        model.clear(); assertEquals("", model.state.value.family)
    }
    @Test fun preferencesCarryVersionAndNoRecipientOverrideOrConsent() = runBlocking {
        val gateway = Gateway(); val model = NotificationModel(gateway, this)
        model.bind("family", "elder", "child"); model.refresh(); yield()
        model.save(true, true, "Asia/Shanghai", "22:00", "08:00"); yield()
        assertEquals(0L, gateway.lastVersion)
        assertEquals(listOf("IN_APP", "PUSH"), (0..1).map { gateway.lastBody!!.getJSONArray("channels").getString(it) })
        assertFalse(gateway.lastBody!!.has("recipient_user_id")); assertFalse(gateway.lastBody!!.has("consent"))
        model.clear()
    }
    @Test fun pollingStartsOnceAndClearStopsIt() = runBlocking {
        val gateway = Gateway(); val model = NotificationModel(gateway, this)
        model.bind("family", "elder", "child"); model.startPolling(); model.startPolling(); yield(); yield()
        assertEquals(1, model.state.value.items.size)
        model.clear(); yield()
        assertTrue(model.state.value.items.isEmpty()); assertEquals("", model.state.value.family)
    }
}
