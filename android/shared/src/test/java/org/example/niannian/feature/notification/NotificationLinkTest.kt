package org.example.niannian.feature.notification

import org.junit.Assert.*
import org.junit.Test

class NotificationLinkTest {
    private val id = "0192f1e4-6ed8-7c21-a4c1-5d58db7c3001"
    private val user = "0192f1e4-6ed8-7c21-a4c1-5d58db7c3002"
    private val link = "niannian-family://notification/$id/$user"

    @Test fun pushAndLocalNotificationsUseTheSameRoutingIds() {
        assertEquals(NotificationLaunch(id, user), parseNotificationLink(link))
        assertEquals(validatedNotificationLaunch(id, user), parseNotificationLink(link))
    }

    @Test fun malformedOrCredentialBearingLinksAreRejected() {
        listOf(null, "", "$link?token=secret", "$link#action", "$link/", "$link/extra",
            link.replace("notification/", "notification:443/"),
            link.replace("notification/", "secret@notification/"),
            link.replace("niannian-family", "https"), link.replace(id, "1-1-1-1-1"),
            link.replace(id, id.uppercase()), link.replace(id, "%30" + id.drop(1)),
            link.replace("notification", "other"), "niannian-family://notification/$id")
            .forEach { assertNull(it, parseNotificationLink(it)) }
        assertNull(validatedNotificationLaunch(id, null))
    }

    @Test fun subscriptionRequiresTlsDefaultSchemeAndPlainTopicWithoutCredentials() {
        assertEquals("ntfy://push.example/fictional-topic", validPushSubscription("ntfy://push.example/fictional-topic"))
        listOf("https://push.example/topic", "ntfy://secret@push.example/topic", "ntfy://push.example/topic?secure=false",
            "ntfy://push.example/topic#secret", "ntfy://push.example/prefix/topic", "ntfy://push.example/" + "x".repeat(65))
            .forEach { assertNull(it, validPushSubscription(it)) }
    }
}
