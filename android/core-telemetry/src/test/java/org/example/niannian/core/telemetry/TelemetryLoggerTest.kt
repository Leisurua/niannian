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
                "error_code" to "TIMEOUT",
                "latency_ms" to "12",
                "transcript" to privateContent,
                "token" to privateContent,
                "device_id" to privateContent + " space",
            ),
        )
        assertTrue(emitted.contains("\"request_id\":\"req-1\""))
        assertTrue(emitted.contains("\"correlation_id\":\"corr-1\""))
        assertTrue(emitted.contains("\"error_code\":\"TIMEOUT\""))
        assertTrue(emitted.contains("\"latency_ms\":12"))
        assertFalse(emitted.contains(privateContent))
        assertFalse(emitted.contains("transcript"))
        assertFalse(emitted.contains("token"))
    }

    @Test
    fun rejectsContentAsEventAndPhoneLikeId() {
        var emitted = ""
        val logger = TelemetryLogger { emitted = it }
        logger.info("message with spaces", mapOf("user_id" to "1" + "3".repeat(10)))
        assertEquals("{\"event\":\"UNSTRUCTURED_LOG\"}", emitted)
    }
}
