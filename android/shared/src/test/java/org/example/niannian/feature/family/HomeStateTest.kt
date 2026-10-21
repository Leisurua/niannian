package org.example.niannian.feature.family

import org.example.niannian.feature.memory.MemoryItem
import org.example.niannian.feature.memory.MemoryState
import org.example.niannian.feature.reminder.ReminderCard
import org.example.niannian.feature.reminder.ReminderState
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import java.time.Instant

class HomeStateTest {
    private val connected = CompanionState(loggedIn = true, userId = "elder-a",
        selected = FamilyChoice("family-a", "虚构家庭", "ELDER", "ACTIVE"))

    @Test fun savedLoginCannotClaimConnectionWhileOfflineOrAwaitingMembership() {
        assertTrue(homeConnectionLabel(connected).startsWith("已连接"))
        for (state in listOf(connected.copy(offline = true), connected.copy(busy = true),
            connected.copy(error = "请重新确认"), connected.copy(selected = null),
            connected.copy(selected = connected.selected!!.copy(status = "PENDING")), connected.copy(loggedIn = false))) {
            assertFalse(homeConnectionLabel(state).startsWith("已连接"))
            assertFalse(homeConnectionStatus(state).contains("已联机"))
        }
    }

    @Test fun homeNeverRendersMemoriesForAnotherAccountFamilyOrOffline() {
        val item = MemoryItem("memory", "虚构往事", "仅用于测试", "CONFIRMED", 1, "elder-a", emptyList())
        val memories = MemoryState(familyId = "family-a", userId = "elder-a", items = listOf(item))
        assertEquals(listOf(item), homeMemoryItems(connected, memories))
        assertTrue(homeMemoryItems(connected, memories.copy(error = "连接不可用")).isEmpty())
        assertTrue(homeMemoryItems(connected, memories.copy(items = emptyList())).isEmpty())
        for (state in listOf(connected.copy(userId = "elder-b"), connected.copy(offline = true),
            connected.copy(error = "授权待确认"), connected.copy(loggedIn = false),
            connected.copy(selected = connected.selected!!.copy(id = "family-b")))) {
            assertTrue(homeMemoryItems(state, memories).isEmpty())
        }
    }

    @Test fun familyHomeUsesCurrentServerTimeFeedbackAndDeletionWithoutMergingSimilarTitles() {
        val now = Instant.parse("2026-10-21T09:30:00Z")
        fun rule(id: String, time: String) = JSONObject().put("id", id).put("owner_user_id", "elder-a")
            .put("title", "虚构提醒$id").put("content", "虚构内容").put("type", "CALENDAR")
            .put("schedule_time_local", time).put("timezone", "Asia/Shanghai").put("start_date", "2026-10-21")
            .put("recurrence_kind", "DAILY")
        val old = ReminderState(family = "family-a", user = "elder-a", rules = listOf(rule("1", "08:30:00")))
        assertEquals("08:30", homeFamilyReminderRows(connected, old, "elder-a", now).single().time)
        val updated = rule("1", "17:12:00").put("executions", JSONArray().put(JSONObject()
            .put("scheduled_at", "2026-10-21T09:12:00+00:00").put("feedback_status", "DONE")))
        val fresh = old.copy(rules = listOf(updated, rule("12", "18:30:00")))
        val rows = homeFamilyReminderRows(connected, fresh, "elder-a", now)
        assertEquals(2, rows.size)
        assertEquals("17:12", rows.first().time)
        assertTrue(rows.first().done)
        assertFalse(homeFamilyReminderRows(connected, fresh, "elder-a", now.plusSeconds(86400)).first().done)
        assertTrue(homeFamilyReminderRows(connected, old.copy(rules = emptyList()), "elder-a", now).isEmpty())
        assertTrue(homeFamilyReminderRows(connected.copy(offline = true), fresh, "elder-a", now).isEmpty())
        assertTrue(homeFamilyReminderRows(connected, fresh.copy(offline = true), "elder-a", now).isEmpty())
        assertTrue(homeFamilyReminderRows(connected.copy(userId = "elder-b"), fresh, "elder-a", now).isEmpty())
        assertTrue(homeFamilyReminderRows(connected, fresh, "elder-b", now).isEmpty())
    }

    @Test fun elderHomeCompletionResetsForTheNextOccurrenceAndClearsWithTheModel() {
        val today = ReminderCard("today", "rule", "虚构提醒", "测试", "2026-10-21T17:12+08:00[Asia/Shanghai]",
            "DONE", false, false, false, true)
        val tomorrow = today.copy(key = "tomorrow", time = "2026-10-22T17:12+08:00[Asia/Shanghai]", status = "PENDING", due = false)
        val reminders = ReminderState(family = "family-a", user = "elder-a", cards = listOf(today, tomorrow))
        assertEquals(listOf(today), homeCurrentReminderCards(connected, reminders, Instant.parse("2026-10-21T10:00:00Z")))
        assertEquals(listOf(tomorrow), homeCurrentReminderCards(connected, reminders, Instant.parse("2026-10-22T00:00:00Z")))
        assertTrue(homeCurrentReminderCards(connected, ReminderState()).isEmpty())
    }

    @Test fun onlyCurrentElderMaySeeTheirOwnOfflineReminderCards() {
        val card = ReminderCard("key", "rule", "虚构喝水提醒", "测试", "2026-10-21T08:00Z[UTC]",
            "DONE", true, false, false, true)
        val reminders = ReminderState(family = "family-a", user = "elder-a", cards = listOf(card), offline = true)
        assertEquals(listOf(card), homeReminderCards(connected.copy(offline = true), reminders))
        assertTrue(homeReminderCards(connected.copy(userId = "elder-b"), reminders).isEmpty())
        assertTrue(homeReminderCards(connected.copy(selected = null), reminders).isEmpty())
        assertTrue(homeReminderCards(connected.copy(loggedIn = false), reminders).isEmpty())
    }

    @Test fun expiredOrUnparseableConsentIsNeverPresentedAsGranted() {
        val now = Instant.parse("2026-10-21T00:00:00Z")
        val permission = Permission("consent", "FAMILY_MEMORY", "GRANTED", 1, "")
        assertTrue(homeConsentGranted(permission, now))
        assertTrue(homeConsentGranted(permission.copy(expiry = "2026-10-22T00:00:00+00:00"), now))
        for (p in listOf(permission.copy(status = "REVOKED"), permission.copy(status = "PENDING"),
            permission.copy(expiry = now.toString()), permission.copy(expiry = "invalid"))) {
            assertFalse(homeConsentGranted(p, now))
        }
    }
}
