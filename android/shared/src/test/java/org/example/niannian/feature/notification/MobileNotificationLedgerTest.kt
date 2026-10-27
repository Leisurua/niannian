package org.example.niannian.feature.notification

import org.junit.Assert.*
import org.junit.Test

class MobileNotificationLedgerTest {
    @Test fun repeatedPollAndUserDismissalDoNotNotifyAgain() {
        val empty = MobileNotificationLedger.parse(null, "account-a")
        assertEquals(setOf("new"), empty.toPost(setOf("new")))
        val saved = MobileNotificationLedger.parse(empty.update(setOf("new")).toString(), "account-a")
        assertTrue(saved.toPost(setOf("new")).isEmpty())
        assertEquals(setOf("next"), saved.toPost(setOf("new", "next")))
        assertEquals(setOf("new"), saved.toPost(setOf("new"), setOf("new")))
        assertTrue(saved.toPost(emptySet(), setOf("new")).isEmpty())
    }
    @Test fun accountOrServerChangeAndRetentionCannotReuseOldDedupeState() {
        val saved = MobileNotificationLedger("account-a", mapOf("old" to 1L)).update(emptySet(), 8 * 86400000L)
        assertTrue(MobileNotificationLedger.parse(saved.toString(), "account-a").seen.isEmpty())
        val current = MobileNotificationLedger.parse(null, "account-a").update(setOf("id"))
        assertEquals(setOf("id"), MobileNotificationLedger.parse(current.toString(), "account-b").toPost(setOf("id")))
        assertTrue(MobileNotificationLedger.parse("broken", "account-a").seen.isEmpty())
    }
}
