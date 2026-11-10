package org.example.niannian.elder

import java.nio.ByteBuffer
import java.util.UUID
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class BleHelpButtonTest {
    private val event = UUID.fromString("00112233-4455-4677-8899-aabbccddeeff")
    private fun frame() = ByteBuffer.allocate(17).put(1).putLong(event.mostSignificantBits)
        .putLong(event.leastSignificantBits).array()

    @Test fun validPressUsesTheFirmwareUuidAsTheIdempotencyKey() {
        assertEquals(event.toString(), decodeHelpPress(frame()))
    }

    @Test fun invalidVersionLengthAndUuidFlagsDoNotTriggerHelp() {
        assertNull(decodeHelpPress(frame().copyOf(16)))
        assertNull(decodeHelpPress(frame().apply { this[0] = 2 }))
        assertNull(decodeHelpPress(frame().apply { this[7] = 0 }))
        assertNull(decodeHelpPress(frame().apply { this[9] = 0 }))
    }
}
