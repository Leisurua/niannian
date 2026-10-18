package org.example.niannian.feature.conversation

import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.yield
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

class ConversationModelTest {
    private val id = "0192f1e4-6ed8-7c21-a4c1-5d58db7c3001"
    private fun frame(sequence: Long, type: String = "session.ready", payload: JSONObject = JSONObject()) =
        JSONObject().put("conversation_id", id).put("sequence", sequence).put("type", type).put("payload", payload).toString()

    private inner class Gateway : ConversationGateway {
        val sent = mutableListOf<JSONObject>()
        var listener: (String) -> Unit = {}
        var onClose: (Int) -> Unit = {}
        var closed = 0
        var failEnd = false
        var waitStatus: CompletableDeferred<Unit>? = null
        var immediateReady = false
        override suspend fun create(family: String) = id
        override suspend fun status(id: String): String { waitStatus?.await(); return "ACTIVE" }
        override suspend fun end(id: String) { if (failEnd) error("offline") }
        override suspend fun connect(id: String, message: (String) -> Unit, closed: (Int) -> Unit): ConversationSocket {
            listener = message; onClose = closed
            if (immediateReady) message(frame(1))
            return object : ConversationSocket {
                override fun send(text: String): Boolean { sent.add(JSONObject(text)); return true }
                override fun close() { this@Gateway.closed++ }
            }
        }
    }

    @Test fun handshakeSendsOneStartAndNeverRepeatsItForSecondReady() = runBlocking {
        val gateway = Gateway(); val model = ConversationModel(gateway, this)
        model.bind("family", "elder"); model.start(); yield()
        gateway.listener(frame(1)); yield()
        gateway.listener(frame(2)); yield()
        assertEquals(listOf("session.start"), gateway.sent.map { it.getString("type") })
        model.clear()
    }

    @Test fun reconnectKeepsIncreasingClientSequenceAndIgnoresOldCallback() = runBlocking {
        val gateway = Gateway(); val model = ConversationModel(gateway, this)
        model.bind("family", "elder"); model.start(); yield()
        gateway.listener(frame(1)); yield()
        val oldClose = gateway.onClose
        gateway.onClose(0); yield()
        model.start(); yield()
        gateway.listener(frame(5)); yield()
        oldClose(4403); yield()
        assertTrue(model.state.value.connected)
        assertEquals(listOf(1L, 2L), gateway.sent.map { it.getLong("sequence") })
        model.clear()
    }

    @Test fun familyChangeAndClearRejectLateFrames() = runBlocking {
        val gateway = Gateway(); val model = ConversationModel(gateway, this)
        model.bind("family-a", "elder"); model.start(); yield()
        gateway.listener(frame(1)); yield()
        val old = gateway.listener
        model.bind("family-b", "elder")
        old(frame(2, "assistant.text", JSONObject().put("text", "old private text"))); yield()
        assertEquals("family-b", model.state.value.family)
        assertEquals("", model.state.value.reply)
        assertFalse(model.state.value.connected)
        model.clear()
    }

    @Test fun malformedGapAndAuthorizationFailureClearDisplayedReply() = runBlocking {
        for (failure in listOf("gap", "json", "permission")) {
            val gateway = Gateway(); val model = ConversationModel(gateway, this)
            model.bind("family", "elder"); model.start(); yield()
            gateway.listener(frame(1)); yield()
            gateway.listener(frame(2, "assistant.text", JSONObject().put("text", "fictional reply"))); yield()
            assertEquals("fictional reply", model.state.value.reply)
            when (failure) {
                "gap" -> gateway.listener(frame(4))
                "json" -> gateway.listener("invalid")
                else -> gateway.onClose(4403)
            }
            yield()
            assertEquals("", model.state.value.reply)
            assertFalse(model.state.value.connected)
            model.clear()
        }
    }

    @Test fun doubleInputAndControlsDoNotGenerateDuplicateTurn() = runBlocking {
        val gateway = Gateway(); val model = ConversationModel(gateway, this)
        model.bind("family", "elder"); model.start(); yield()
        gateway.listener(frame(1)); yield()
        model.input("你好"); model.input("不应重发"); model.repeat(); model.slowDown()
        assertEquals(1, gateway.sent.count { it.getString("type") == "text.input" })
        model.interrupt()
        assertEquals("interrupt", gateway.sent.last().getString("type"))
        assertEquals("", model.state.value.reply)
        model.clear()
    }

    @Test fun endingUnknownResultRetainsSequenceForSafeReconnect() = runBlocking {
        val gateway = Gateway(); val model = ConversationModel(gateway, this)
        model.bind("family", "elder"); model.start(); yield()
        gateway.listener(frame(1)); yield()
        gateway.failEnd = true; model.end(); yield()
        model.start(); yield()
        gateway.listener(frame(3)); yield()
        assertEquals(2L, gateway.sent.last().getLong("sequence"))
        model.clear()
    }

    @Test fun delayedStartAcknowledgementDoesNotUnlockAnActiveTurn() = runBlocking {
        val gateway = Gateway(); val model = ConversationModel(gateway, this)
        model.bind("family", "elder"); model.start(); yield()
        gateway.listener(frame(1)); yield()
        model.input("你好")
        gateway.listener(frame(2)); yield()
        assertTrue(model.state.value.busy)
        assertEquals("THINKING", model.state.value.state)
        model.input("不应重发")
        assertEquals(1, gateway.sent.count { it.getString("type") == "text.input" })
        model.clear()
    }

    @Test fun pendingStatusCannotRestoreOldFamilyAfterClear() = runBlocking {
        val gateway = Gateway(); val gate = CompletableDeferred<Unit>(); gateway.waitStatus = gate
        val model = ConversationModel(gateway, this)
        model.bind("family-a", "elder"); model.start(); yield()
        model.bind("family-b", "elder"); gate.complete(Unit); yield()
        assertEquals("family-b", model.state.value.family)
        assertEquals("", model.state.value.id)
        assertFalse(model.state.value.connected)
        model.clear()
    }

    @Test fun successfulEndKeepsOnlyCurrentRecapIdUntilClear() = runBlocking {
        val gateway = Gateway(); val model = ConversationModel(gateway, this)
        model.bind("family", "elder"); model.start(); yield()
        val id = model.state.value.id
        model.end(); yield()
        assertEquals(id, model.state.value.recapId)
        assertEquals("", model.state.value.reply)
        model.clear(); assertEquals("", model.state.value.recapId)
    }
}
