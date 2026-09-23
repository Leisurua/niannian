package org.example.niannian.core.common

import org.junit.Assert.assertEquals
import org.junit.Test

class BuildInfoTest {
    @Test
    fun productNameIsStable() {
        assertEquals("NianNian", BuildInfo.PRODUCT_NAME)
    }
}
