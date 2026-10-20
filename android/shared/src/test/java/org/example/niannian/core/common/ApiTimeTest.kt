package org.example.niannian.core.common

import org.junit.Assert.assertEquals
import org.junit.Test

class ApiTimeTest {
    @Test fun acceptsUtcAndOffsetTimestampsWithoutLosingPrecision() {
        val expected = parseApiInstant("2026-10-20T06:12:00.123456Z")
        assertEquals(expected, parseApiInstant("2026-10-20T06:12:00.123456+00:00"))
        assertEquals(expected, parseApiInstant("2026-10-20T14:12:00.123456+08:00"))
    }
}
