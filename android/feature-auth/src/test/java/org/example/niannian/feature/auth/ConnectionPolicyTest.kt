package org.example.niannian.feature.auth

import org.junit.Assert.assertEquals
import org.junit.Assert.assertThrows
import org.junit.Test

class ConnectionPolicyTest {
    @Test fun releaseRequiresHttpsAndRejectsEmbeddedCredentials() {
        assertEquals("https://example.com", ConnectionPolicy.origin("https://example.com/", false))
        listOf("http://example.com", "http://10.0.2.2:8000", "https://user@example.com", "https://example.com?token=x",
            "https://example.com/path", "file:///data", "https://example.com#fragment").forEach {
            assertThrows(IllegalArgumentException::class.java) { ConnectionPolicy.origin(it, false) }
        }
    }
    @Test fun debugHttpIsOnlyForLoopbackAndEmulator() {
        assertEquals("http://10.0.2.2:8000", ConnectionPolicy.origin("http://10.0.2.2:8000", true))
        assertThrows(IllegalArgumentException::class.java) { ConnectionPolicy.origin("http://example.com", true) }
        assertThrows(IllegalArgumentException::class.java) { ConnectionPolicy.origin("http://localhost.example.com", true) }
    }
    @Test fun invitationCannotEscapeTheApiPath() {
        assertEquals("fictional_invite_value", ConnectionPolicy.invitation(" fictional_invite_value "))
        listOf("short", "../../other/path", "https://example.com/invite", "fictional?key=value").forEach {
            assertThrows(IllegalArgumentException::class.java) { ConnectionPolicy.invitation(it) }
        }
    }
}
