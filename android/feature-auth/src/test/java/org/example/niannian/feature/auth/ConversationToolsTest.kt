package org.example.niannian.feature.auth

import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.yield
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

class ConversationToolsTest {
    private val cid = "0192f1e4-6ed8-7c21-a4c1-5d58db7c3001"
    private class Gateway : ConversationToolsGateway {
        var reason: String? = null
        var fail = false
        var gate: CompletableDeferred<Unit>? = null
        var summaryStatus = "READY"
        override suspend fun call(path: String, method: String, body: JSONObject?, version: Long?, reason: String?): JSONObject {
            this.reason = reason
            gate?.await()
            if (fail) error("fictional network failure")
            return if (path.startsWith("/v1/conversations")) JSONObject().put("family_id", "family-a").put("owner_user_id", "elder")
                .put("summary_status", summaryStatus).put("summary", "Mock 虚构主题")
            else JSONObject().put("version", 2).put("timezone", "Asia/Shanghai").put("window_start", "08:00:00")
                .put("window_end", "20:00:00").put("quiet_start", JSONObject.NULL).put("quiet_end", JSONObject.NULL)
                .put("daily_cap", 2).put("confirmed", true).put("paused_on", JSONObject.NULL)
        }
    }
    @Test fun familyReasonSentAndBackgroundClearRemovesSensitiveText() = runBlocking {
        val gateway = Gateway(); val model = ConversationToolsModel(gateway, this)
        model.bind("family-a", "elder"); model.summary(cid, "FOLLOW_UP"); yield()
        assertEquals("FOLLOW_UP", gateway.reason)
        assertTrue(model.state.value.summary.isNotEmpty())
        model.clear(); assertEquals("", model.state.value.summary)
    }
    @Test fun failedPendingAndCrossFamilyReadsNeverDisplaySummary() = runBlocking {
        val gateway = Gateway(); val model = ConversationToolsModel(gateway, this)
        model.bind("family-a", "elder"); gateway.summaryStatus = "PENDING"
        model.summary(cid, null); yield(); assertEquals("", model.state.value.summary)
        gateway.summaryStatus = "READY"; gateway.fail = true
        model.summary(cid, null); yield(); assertEquals("", model.state.value.summary)
        gateway.fail = false; model.bind("family-b", "elder")
        model.summary(cid, "FAMILY_CHECK_IN"); yield(); assertEquals("", model.state.value.summary)
        model.clear()
    }
    @Test fun oldReadCannotRestoreSummaryAfterFamilyChange() = runBlocking {
        val gateway = Gateway(); gateway.gate = CompletableDeferred()
        val model = ConversationToolsModel(gateway, this)
        model.bind("family-a", "elder"); model.summary(cid, null); yield()
        model.bind("family-b", "elder"); gateway.gate!!.complete(Unit); yield()
        assertEquals("family-b", model.state.value.family); assertEquals("", model.state.value.summary)
        model.clear()
    }
    @Test fun preferenceOfflineFailureClearsLoadedState() = runBlocking {
        val gateway = Gateway(); val model = ConversationToolsModel(gateway, this)
        model.bind("family-a", "elder"); model.refresh(); yield(); assertTrue(model.state.value.loaded)
        gateway.fail = true; model.pause(); yield(); assertFalse(model.state.value.loaded)
        assertTrue(model.state.value.message.contains("未完成")); model.clear()
    }
}
