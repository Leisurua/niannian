package org.example.niannian.core.common

import org.junit.Assert.assertEquals
import org.junit.Assert.assertThrows
import org.junit.Test

class RuntimeConfigTest {
    @Test
    fun profilesHaveExplicitSourceLabels() {
        assertEquals("开发环境 · 演示能力（Mock）", RuntimeConfig.fromBuildValues("dev", "mock").statusLabel)
        assertEquals("测试环境 · 演示能力（Mock）", RuntimeConfig.fromBuildValues("test", "mock").statusLabel)
        assertEquals("DEMO · 演示数据 · 演示能力（Mock）", RuntimeConfig.fromBuildValues("demo", "mock").statusLabel)
        assertEquals("开发环境 · 真实能力（Real）", RuntimeConfig.fromBuildValues("dev", "real").statusLabel)
    }

    @Test
    fun demoRejectsRealProvider() {
        assertThrows(IllegalArgumentException::class.java) {
            RuntimeConfig.fromBuildValues("demo", "real")
        }
    }
}
