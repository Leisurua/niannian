package org.example.niannian.core.telemetry

import android.util.Log

/** Only stable event codes and allowlisted metadata reach Logcat. */
class TelemetryLogger(private val sink: (String) -> Unit = { Log.i("NianNian", it) }) {
    private val symbol = Regex("[A-Za-z][A-Za-z0-9_.-]{0,63}")
    private val eventCode = Regex("[A-Z][A-Z0-9_]{2,63}")
    private val identifier = Regex("[A-Za-z0-9][A-Za-z0-9._:-]{0,127}")
    private val phoneLike = Regex("[0-9]{10,}")
    private val secretLike = Regex("(?:sk-[A-Za-z0-9]{20,}|AKIA[A-Z0-9]{16}|eyJ[A-Za-z0-9_-]{8,}\\.eyJ[A-Za-z0-9_-]{8,}\\.[A-Za-z0-9_-]{8,})")
    private val idFields = setOf("request_id", "correlation_id", "user_id", "family_id", "conversation_id", "event_id", "device_id")
    private val symbolFields = setOf("provider", "result", "error_code")

    fun info(event: String, fields: Map<String, String> = emptyMap()) {
        val safeEvent = if (eventCode.matches(event) && !phoneLike.containsMatchIn(event)) event else "UNSTRUCTURED_LOG"
        val values = mutableListOf("\"event\":\"$safeEvent\"")
        for ((key, value) in fields) {
            if (key == "latency_ms") {
                val latency = value.toLongOrNull()
                if (latency != null && latency in 0..86_400_000) values.add("\"latency_ms\":$latency")
                continue
            }
            val pattern = when (key) {
                in idFields -> identifier
                in symbolFields -> symbol
                else -> continue
            }
            if (pattern.matches(value) && !phoneLike.containsMatchIn(value) && !secretLike.containsMatchIn(value)) {
                values.add("\"$key\":\"$value\"")
            }
        }
        sink("{${values.joinToString(",")}}")
    }
}
