package org.example.niannian.core.telemetry

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class TelemetryLoggerTest {
    @Test
    fun keepsOnlyApprovedMetadata() {
        var emitted = ""
        val privateContent = "private" + "content"
        val logger = TelemetryLogger { emitted = it }
        logger.info(
            "REQUEST_FAILED",
            mapOf(
                "request_id" to "req-1",
                "correlation_id" to "corr-1",
                "user_id" to "user-1",
                "family_id" to "family-1",
                "conversation_id" to "conversation-1",
                "event_id" to "event-1",
                "provider" to "mock",
                "result" to "FAILED",
                "error_code" to "TIMEOUT",
                "latency_ms" to "12",
                "transcript" to privateContent,
                "token" to privateContent,
                "device_id" to privateContent + " space",
            ),
        )
        assertTrue(emitted.contains("\"request_id\":\"req-1\""))
        assertTrue(emitted.contains("\"correlation_id\":\"corr-1\""))
        assertTrue(emitted.contains("\"user_id\":\"user-1\""))
        assertTrue(emitted.contains("\"family_id\":\"family-1\""))
        assertTrue(emitted.contains("\"conversation_id\":\"conversation-1\""))
        assertTrue(emitted.contains("\"event_id\":\"event-1\""))
        assertTrue(emitted.contains("\"provider\":\"mock\""))
        assertTrue(emitted.contains("\"result\":\"FAILED\""))
        assertTrue(emitted.contains("\"error_code\":\"TIMEOUT\""))
        assertTrue(emitted.contains("\"latency_ms\":12"))
        assertFalse(emitted.contains(privateContent))
        assertFalse(emitted.contains("transcript"))
        assertFalse(emitted.contains("token"))
    }

    @Test
    fun keepsDeviceId() {
        var emitted = ""
        val logger = TelemetryLogger { emitted = it }
        logger.info("DEVICE_SEEN", mapOf("device_id" to "device-1"))
        assertTrue(emitted.contains("\"device_id\":\"device-1\""))
    }

    @Test
    fun rejectsCredentialShapedMetadata() {
        var emitted = ""
        val credential = "sk-" + "A".repeat(24)
        val logger = TelemetryLogger { emitted = it }
        logger.info("REQUEST_FAILED", mapOf("user_id" to credential, "error_code" to credential))
        assertEquals("{\"event\":\"REQUEST_FAILED\"}", emitted)
    }

    @Test
    fun rejectsContentAsEventAndPhoneLikeId() {
        var emitted = ""
        val logger = TelemetryLogger { emitted = it }
        logger.info("message with spaces", mapOf("user_id" to "1" + "3".repeat(10)))
        assertEquals("{\"event\":\"UNSTRUCTURED_LOG\"}", emitted)
    }
}
