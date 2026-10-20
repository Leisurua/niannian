package org.example.niannian.feature.reminder

import java.security.MessageDigest
import java.time.Duration
import java.time.Instant
import java.time.LocalDate
import java.time.LocalTime
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.time.temporal.ChronoUnit

internal data class ReminderRule(
    val time: LocalTime,
    val timezone: String,
    val startDate: LocalDate,
    val endDate: LocalDate? = null,
    val kind: String,
    val interval: Int = 1,
    val weekdays: List<Int> = emptyList(),
    val quiet: ReminderQuietHours? = null,
) {
    init {
        reminderZone(timezone)
        require(time.nano == 0)
        require(startDate.year in 1..9999 && (endDate == null || endDate.year in 1..9999))
        require(endDate == null || endDate >= startDate)
        require(kind in setOf("ONCE", "DAILY", "WEEKLY", "INTERVAL"))
        require(interval > 0)
        require(weekdays.all { it in 0..6 } && weekdays.distinct().size == weekdays.size)
        require(if (kind == "WEEKLY") weekdays.isNotEmpty() else weekdays.isEmpty())
    }
}

internal data class ReminderQuietHours(val start: LocalTime, val end: LocalTime, val timezone: String) {
    init { reminderZone(timezone); require(start.nano == 0 && end.nano == 0) }
}

internal data class ReminderOccurrence(
    val scheduledAt: Instant,
    val localDate: LocalDate,
    val localTime: LocalTime,
    val occurrenceKey: String,
    val quiet: Boolean,
)

private fun reminderZone(value: String): ZoneId {
    // Java accepts fixed offsets and GMT+... aliases which are not IANA rule IDs.
    require(value in ZoneId.getAvailableZoneIds()) { "Unknown IANA timezone" }
    return ZoneId.of(value)
}

internal object ReminderCalendar {
    private val timeFormat = DateTimeFormatter.ofPattern("HH:mm:ss", java.util.Locale.ROOT)
    private val utcFormat = DateTimeFormatter.ofPattern("uuuu-MM-dd'T'HH:mm:ss'+00:00'", java.util.Locale.ROOT)
        .withZone(ZoneId.of("UTC"))

    fun inQuietHours(instant: Instant, quiet: ReminderQuietHours?): Boolean {
        if (quiet == null || quiet.start == quiet.end) return false
        val local = instant.atZone(reminderZone(quiet.timezone)).toLocalTime()
        return if (quiet.start < quiet.end) local >= quiet.start && local < quiet.end
        else local >= quiet.start || local < quiet.end
    }

    fun occurrences(rule: ReminderRule, start: Instant, end: Instant, maxDays: Int = 366): List<ReminderOccurrence> {
        require(end > start && maxDays in 1..366) { "Invalid bounded time window" }
        require(Duration.between(start, end) <= Duration.ofDays(maxDays.toLong())) { "Time window too large" }
        val zone = reminderZone(rule.timezone)
        val startDay = start.atZone(zone).toLocalDate()
        val endDay = end.atZone(zone).toLocalDate()
        require(startDay.year in 1..9999 && endDay.year in 1..9999)
        var day = maxOf(startDay, rule.startDate)
        val last = minOf(endDay, rule.endDate ?: endDay)
        val result = mutableListOf<ReminderOccurrence>()
        while (day <= last) {
            val elapsed = ChronoUnit.DAYS.between(rule.startDate, day)
            val matches = when (rule.kind) {
                "ONCE" -> elapsed == 0L
                "DAILY", "INTERVAL" -> elapsed % rule.interval == 0L
                else -> (elapsed + rule.startDate.dayOfWeek.value - 1) / 7 % rule.interval == 0L &&
                    day.dayOfWeek.value - 1 in rule.weekdays
            }
            if (matches) {
                val wallTime = day.atTime(rule.time)
                // atZone() shifts nonexistent times forward; use explicit valid offsets instead.
                val instant = zone.rules.getValidOffsets(wallTime).map { wallTime.toInstant(it) }.minOrNull()
                if (instant != null && instant >= start && instant < end) {
                    val identity = "${rule.timezone}|$day|${rule.time.format(timeFormat)}|${utcFormat.format(instant)}"
                    val key = MessageDigest.getInstance("SHA-256").digest(identity.toByteArray(Charsets.UTF_8))
                        .joinToString("") { "%02x".format(java.util.Locale.ROOT, it) }
                    result += ReminderOccurrence(instant, day, rule.time, key, inQuietHours(instant, rule.quiet))
                }
            }
            if (day == last) break
            day = day.plusDays(1)
        }
        return result
    }
}
