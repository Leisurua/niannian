package org.example.niannian.feature.notification

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
        var eventStatus = "NOTIFIED"; var canHandle = true; var actionCount = 0
        var actionWait: CompletableDeferred<Unit>? = null
        fun event() = JSONObject().put("id", eventId).put("family_id", family).put("owner_user_id", "elder")
            .put("summary", "Mock · 请先联系家人核实").put("status", eventStatus).put("can_handle", canHandle)
        override suspend fun events(family: String) = listOf(event())
        override suspend fun list(): List<JSONObject> {
            wait?.await(); if (fail) error("offline")
            return listOf(JSONObject().put("id", id).put("signal_event_id", eventId).put("status", "SENT")
                .put("channel", "IN_APP").put("summary", "Mock · 有关注提示"))
        }
        override suspend fun call(path: String, method: String, body: JSONObject?, version: Long?): JSONObject {
            if (fail) error("offline")
            if (path.startsWith("/v1/signal-events")) return event()
            lastBody = body; lastVersion = version
            return JSONObject().put("family_id", "family").put("owner_user_id", "elder").put("recipient_user_id", "child")
                .put("channels", JSONArray(listOf("IN_APP"))).put("timezone", "Asia/Shanghai").put("version", if (method == "PUT") 1 else 0)
                .put("quiet_hours_start", JSONObject.NULL).put("quiet_hours_end", JSONObject.NULL)
        }
        override suspend fun read(id: String, key: String): JSONObject {
            java.util.UUID.fromString(key); readCount++
            return JSONObject().put("id", id).put("status", "READ")
        }
        override suspend fun act(id: String, body: JSONObject, key: String): JSONObject {
            java.util.UUID.fromString(key)
            actionWait?.await()
            if (fail) error("offline")
            assertEquals(eventStatus, body.getString("expected_status"))
            actionCount++; lastBody = body
            eventStatus = when (body.getString("action")) {
                "ACKNOWLEDGE" -> "ACKNOWLEDGED"; "CONTACT" -> "CONTACTED"; "FALSE_POSITIVE" -> "FALSE_POSITIVE"; else -> "RESOLVED"
            }
            return event().put("actioned_at", "2026-10-23T04:00:00Z")
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

    @Test fun eventActionsRequirePermissionAndOnlyAdvanceAfterServerConfirmation() = runBlocking {
        val gateway = Gateway(); val model = NotificationModel(gateway, this)
        model.bind("family", "elder", "child"); model.refresh(); yield()
        model.read(model.state.value.items.single()); yield()
        assertEquals("NOTIFIED", model.state.value.event!!.status)
        model.handle("CONTACT"); yield()
        assertEquals(0, gateway.actionCount)
        for ((action, expected) in listOf("ACKNOWLEDGE" to "ACKNOWLEDGED", "CONTACT" to "CONTACTED", "RESOLVE" to "RESOLVED")) {
            model.handle(action); yield()
            assertEquals(expected, model.state.value.event!!.status)
            assertTrue(model.state.value.event!!.actionedAt.isNotBlank())
        }
        model.handle("ACKNOWLEDGE"); yield(); assertEquals(3, gateway.actionCount)
        model.refresh(); yield()
        gateway.canHandle = false
        model.read(model.state.value.items.single()); yield()
        assertTrue(model.state.value.event!!.actions.isEmpty())
        model.clear()
    }

    @Test fun failedOrLateActionCannotRestoreDetailAfterRevocationOrFamilyChange() = runBlocking {
        for (leave in listOf(false, true)) {
            val gateway = Gateway(); val model = NotificationModel(gateway, this)
            model.bind("family", "elder", "child"); model.refresh(); yield()
            model.read(model.state.value.items.single()); yield()
            gateway.actionWait = CompletableDeferred()
            model.handle("ACKNOWLEDGE"); yield()
            assertNull(model.state.value.event)
            if (leave) model.bind("other", "elder", "child") else gateway.fail = true
            gateway.actionWait!!.complete(Unit); yield()
            assertNull(model.state.value.event); assertTrue(model.state.value.detail.isEmpty())
            assertEquals(0, gateway.actionCount)
            model.clear()
        }
    }

    @Test fun falsePositiveClosesEventAndBlocksFurtherActions() = runBlocking {
        val gateway = Gateway(); val model = NotificationModel(gateway, this)
        model.bind("family", "elder", "child"); model.refresh(); yield()
        model.read(model.state.value.items.single()); yield()
        assertTrue("FALSE_POSITIVE" in model.state.value.event!!.actions)
        model.handle("FALSE_POSITIVE"); yield()
        assertEquals("FALSE_POSITIVE", model.state.value.event!!.status)
        assertTrue(model.state.value.event!!.actions.isEmpty())
        assertTrue(model.state.value.message.contains("误报"))
        model.handle("CONTACT"); yield(); assertEquals(1, gateway.actionCount)
        model.clear()
    }
}
