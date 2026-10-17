package org.example.niannian.feature.reminder

import kotlinx.coroutines.runBlocking
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import java.time.Instant

class ReminderLedgerTest {
    private var now = Instant.parse("2026-10-15T00:00:00Z")
    private fun rule(version: Int = 1) = JSONObject().put("id", "rule").put("family_id", "family").put("owner_user_id", "elder")
        .put("title", "虚构喝水提醒").put("content", "演示内容").put("type", "WATER").put("active", true).put("version", version)
        .put("schedule_time_local", "00:01").put("timezone", "UTC").put("start_date", "2026-10-15")
        .put("recurrence_kind", "DAILY").put("recurrence_interval", 1)
    private suspend fun ready(store: ReminderStore = EphemeralReminderStore()): ReminderLedger {
        val ledger = ReminderLedger(store) { now }
        ledger.bind("family", "elder"); ledger.refresh("family", "elder", listOf(rule()))
        now = now.plusSeconds(120)
        return ledger
    }
    private fun first(snapshot: JSONObject) = snapshot.getJSONObject("occurrences").keys().next()
    private fun ack(status: String) = JSONObject().put("id", "00000000-0000-7000-8000-000000000001")
        .put("reminder_id", "rule").put("scheduled_at", "2026-10-15T00:01:00Z").put("feedback_status", status).put("source", "OFFLINE")

    @Test fun restartKeepsPendingPayloadAndIdempotencyKeyUntilDurableAck() = runBlocking {
        val store = EphemeralReminderStore(); val ledger = ready(store)
        val key = first(ledger.snapshot()); ledger.feedback(key, "DONE")
        val first = ledger.attempted(key)!!.getJSONObject("action")
        val restarted = ReminderLedger(store) { now }
        assertNull(restarted.attempted(key)) // persisted backoff
        now = now.plusSeconds(10)
        val retried = restarted.attempted(key)!!.getJSONObject("action")
        assertEquals(first.getString("key"), retried.getString("key"))
        assertEquals(first.getJSONObject("body").toString(), retried.getJSONObject("body").toString())
        restarted.acknowledge(key, "wrong-key", JSONObject())
        assertTrue(restarted.snapshot().getJSONObject("occurrences").getJSONObject(key).has("action"))
        restarted.acknowledge(key, first.getString("key"), ack("DONE"))
        assertFalse(restarted.snapshot().getJSONObject("occurrences").getJSONObject(key).has("action"))
    }
    @Test fun expiredFeedbackIsErasedWithNoticeAndCannotUpload() = runBlocking {
        val ledger = ready(); val key = first(ledger.snapshot()); ledger.feedback(key, "SKIPPED")
        now = now.plusSeconds(86400)
        val snapshot = ledger.snapshot()
        assertFalse(snapshot.getJSONObject("occurrences").has(key))
        assertTrue(snapshot.getString("notice").isNotBlank())
        assertEquals(0, snapshot.getJSONArray("rules").length())
        assertNull(ledger.attempted(key))
    }
    @Test fun versionChangeRemovesStaleFeedbackAndSwitchWipesFamilyData() = runBlocking {
        val ledger = ready(); val key = first(ledger.snapshot()); ledger.feedback(key, "DONE")
        ledger.refresh("family", "elder", listOf(rule(2)))
        assertNull(ledger.attempted(key))
        ledger.bind("different-family", "different-owner")
        assertEquals(0, ledger.snapshot().getJSONArray("rules").length())
        assertEquals(0, ledger.snapshot().getJSONObject("occurrences").length())
    }
    @Test fun timeRollbackHidesAndErasesOldCache() = runBlocking {
        val store = EphemeralReminderStore(); val ledger = ready(store)
        ledger.snapshot(); now = now.minusSeconds(60)
        try { ledger.snapshot(); fail("Clock rollback was accepted") } catch (_: IllegalStateException) { }
        assertEquals(0, store.load().length())
    }
    @Test fun retryIsBoundedAndTerminalConflictRequiresExplicitAction() = runBlocking {
        val ledger = ready(); val key = first(ledger.snapshot()); ledger.feedback(key, "DONE")
        repeat(5) { assertNotNull(ledger.attempted(key)); now = now.plusSeconds(300) }
        assertNull(ledger.attempted(key))
        ledger.manualRetry(key); assertNotNull(ledger.attempted(key))
        ledger.conflict(key); now = now.plusSeconds(300)
        assertNull(ledger.attempted(key))
        ledger.manualRetry(key)
        assertFalse(ledger.snapshot().getJSONObject("occurrences").getJSONObject(key).has("action"))
    }
    @Test fun futureFeedbackAndClientNoResponseAreRejected() = runBlocking {
        val ledger = ready(); val key = first(ledger.snapshot())
        try { ledger.feedback(key, "NO_RESPONSE"); fail("Client invented status") } catch (_: IllegalArgumentException) { }
        try { ledger.feedback(key, "LATER", now.minusSeconds(1)); fail("Past snooze accepted") } catch (_: IllegalArgumentException) { }
        assertEquals("尚未收到反馈", feedbackLabel("NO_RESPONSE"))
    }
    @Test fun failedStorageCommitNeverReportsFeedbackAsSaved() = runBlocking {
        val backing = EphemeralReminderStore()
        var reject = false
        val store = object : ReminderStore {
            override suspend fun load() = backing.load()
            override suspend fun clear() = backing.clear()
            override suspend fun save(value: JSONObject) { if (reject) throw IllegalStateException("disk failure"); backing.save(value) }
        }
        val ledger = ready(store); val key = first(ledger.snapshot()); reject = true
        try { ledger.feedback(key, "DONE"); fail("Failed transaction reported success") } catch (_: IllegalStateException) { }
        assertFalse(backing.load().getJSONObject("occurrences").getJSONObject(key).has("action"))
    }
    @Test fun notificationSubmissionSurvivesRestartWithoutDuplicatingOccurrence() = runBlocking {
        val store = EphemeralReminderStore(); val ledger = ready(store)
        val due = ledger.notificationCandidates(); assertEquals(1, due.size)
        ledger.presented(due)
        val restarted = ReminderLedger(store) { now }
        assertTrue(restarted.notificationCandidates().isEmpty())
        restarted.feedback(due.single(), "LATER", now.plusSeconds(600))
        assertTrue(restarted.notificationCandidates().isEmpty())
        now = now.plusSeconds(600)
        assertEquals(due, restarted.notificationCandidates())
    }
    @Test fun offlineSnoozeThenDoneKeepsBothKeysAndFinalLocalFeedback() = runBlocking {
        val store = EphemeralReminderStore(); val ledger = ready(store)
        val key = first(ledger.snapshot())
        ledger.feedback(key, "LATER", now.plusSeconds(600)); now = now.plusSeconds(600)
        ledger.feedback(key, "DONE")
        val before = ledger.snapshot().getJSONObject("occurrences").getJSONObject(key)
        val firstKey = before.getJSONObject("action").getString("key")
        val finalKey = before.getJSONObject("next_action").getString("key")
        assertNotEquals(firstKey, finalKey)
        val restarted = ReminderLedger(store) { now }
        restarted.acknowledge(key, firstKey, ack("LATER"))
        val next = restarted.attempted(key)!!
        assertEquals("DONE", next.getString("status"))
        assertEquals(finalKey, next.getJSONObject("action").getString("key"))
        restarted.acknowledge(key, finalKey, ack("DONE"))
        assertFalse(restarted.snapshot().getJSONObject("occurrences").getJSONObject(key).has("action"))
    }
    @Test fun wrongResourceAckCannotErasePendingFeedback() = runBlocking {
        val ledger = ready(); val key = first(ledger.snapshot()); ledger.feedback(key, "DONE")
        val pending = ledger.attempted(key)!!.getJSONObject("action").getString("key")
        try { ledger.acknowledge(key, pending, ack("DONE").put("reminder_id", "foreign")); fail("Wrong ACK accepted") }
        catch (_: IllegalArgumentException) { }
        assertTrue(ledger.snapshot().getJSONObject("occurrences").getJSONObject(key).has("action"))
    }
    @Test fun mutatedRequestCannotBeSentWithOriginalIdempotencyKey() = runBlocking {
        val store = EphemeralReminderStore(); val ledger = ready(store); val key = first(ledger.snapshot())
        ledger.feedback(key, "DONE")
        val saved = store.load()
        saved.getJSONObject("occurrences").getJSONObject(key).getJSONObject("action").getJSONObject("body").put("status", "SKIPPED")
        store.save(saved)
        try { ledger.attempted(key); fail("Changed request was accepted") } catch (_: IllegalArgumentException) { }
    }
}
