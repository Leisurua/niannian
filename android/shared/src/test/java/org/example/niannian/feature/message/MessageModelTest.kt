package org.example.niannian.feature.message

import kotlinx.coroutines.*
import kotlinx.coroutines.flow.first
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

class MessageModelTest {
    private class Gateway : MessageGateway {
        var status = "QUEUED"; var fail = false; var registered = ""
        var sent = ""; val receipts = mutableListOf<Boolean>()
        var pending: String? = null
        var loseReply = false
        var wait: CompletableDeferred<Unit>? = null
        override suspend fun register(family: String, user: String) { registered = family }
        override suspend fun list(family: String, box: String): List<JSONObject> {
            wait?.await(); if (fail) error("offline")
            if (box == "OUTBOX") return emptyList()
            return listOf(JSONObject().put("id", "letter").put("family_id", family).put("created_at", "2026-10-21T00:00:00Z")
                .put("payload", JSONObject().put("text", "虚构留言"))
                .put("deliveries", JSONArray().put(JSONObject().put("id", "receipt").put("status", status))))
        }
        override suspend fun acknowledge(id: String, read: Boolean): JSONObject {
            receipts.add(read); status = if (read) "READ" else "RECEIVED"
            return JSONObject().put("id", id).put("status", status)
        }
        override suspend fun pendingDraft(family: String, user: String) = pending.takeIf { family == "family" }
        override suspend fun send(family: String, user: String, role: String, text: String): JSONObject {
            sent = "$family:$role:$text"
            if (loseReply) { pending = text; error("offline") }
            pending = null
            return JSONObject()
        }
    }

    @Test fun receptionAndExplicitReadAreSeparateAndReplyUsesCurrentFamily() = runBlocking {
        val gateway = Gateway(); val model = MessageModel(gateway, true, this)
        model.bind("family", "elder"); yield(); yield()
        assertEquals("family", gateway.registered)
        assertEquals(listOf(false), gateway.receipts)
        model.read(model.state.value.items.single()); yield()
        assertEquals(listOf(false, true), gateway.receipts)
        model.send("虚构回复"); yield()
        assertEquals("family:CHILD:虚构回复", gateway.sent)
        assertEquals(1, model.state.value.sentVersion)
        model.clear()
    }

    @Test fun disconnectClearsOldContentAndReconnectPullsAgain() = runBlocking {
        val gateway = Gateway(); val model = MessageModel(gateway, false, this)
        model.bind("family", "child"); yield(); yield()
        assertEquals(1, model.state.value.items.size)
        gateway.fail = true; model.refresh(); yield()
        assertTrue(model.state.value.items.isEmpty())
        assertFalse(model.state.value.loaded)
        assertTrue(model.state.value.error.isNotBlank())
        gateway.fail = false; model.refresh(); yield()
        assertEquals(1, model.state.value.items.size)
        assertTrue(model.state.value.loaded)
        assertEquals("", model.state.value.error)
        model.clear()
    }

    @Test fun retryDraftIsRestoredOnlyForItsFamilyAndClearedAfterSuccess() = runBlocking {
        val gateway = Gateway()
        val model = MessageModel(gateway, false, this)
        suspend fun loaded() = withTimeout(2000) { model.state.first { it.loaded && !it.busy } }
        model.bind("family", "child"); loaded()
        gateway.loseReply = true
        model.send("虚构留言"); yield()
        assertEquals("虚构留言", model.state.value.pendingDraft)
        assertEquals(0, model.state.value.sentVersion)
        model.bind("another-family", "child")
        assertNull(loaded().pendingDraft)
        model.bind("family", "child")
        assertEquals("虚构留言", loaded().pendingDraft)
        gateway.loseReply = false
        model.send(model.state.value.pendingDraft!!); yield()
        assertNull(model.state.value.pendingDraft)
        assertEquals(1, model.state.value.sentVersion)
        model.clear()
    }

    @Test fun homeAndComposerShareOneBindingWithoutResettingDeliveryOrSendState() = runBlocking {
        val gateway = Gateway(); val model = MessageModel(gateway, false, this)
        model.bind("family", "child"); yield(); yield()
        model.send("真实发送测试"); yield()
        val loaded = model.state.value
        model.bind("family", "child"); yield()
        assertEquals(loaded, model.state.value)
        assertEquals(listOf(false), gateway.receipts)
        model.clear()
    }

    @Test fun switchingFamilyOrLeavingForegroundDiscardsLateResponses() = runBlocking {
        val gateway = Gateway(); gateway.wait = CompletableDeferred()
        val model = MessageModel(gateway, false, this)
        model.bind("old-family", "child"); yield(); yield()
        model.bind("new-family", "child")
        gateway.wait!!.complete(Unit); yield(); yield()
        assertEquals("new-family", model.state.value.family)
        assertEquals("new-family", gateway.registered)
        model.clear(); yield()
        assertTrue(model.state.value.items.isEmpty()); assertEquals("", model.state.value.user)
    }
}
