package org.example.niannian.feature.reminder

import java.time.Instant
import java.time.LocalDate
import java.time.LocalTime
import java.util.TimeZone
import org.json.JSONArray
import org.junit.Assert.*
import org.junit.Test

class ReminderCalendarTest {
    private fun rule() = ReminderRule(LocalTime.of(8, 30), "Asia/Shanghai", LocalDate.parse("2026-10-09"), kind = "DAILY")
    private fun range(rule: ReminderRule = rule(), start: String = "2026-10-09T00:00:00Z", end: String = "2026-10-12T00:00:00Z") =
        ReminderCalendar.occurrences(rule, Instant.parse(start), Instant.parse(end))

    @Test fun frozenFixturesMatchBackendIncludingExactOccurrenceHash() {
        val data = javaClass.getResourceAsStream("/calendar-cases.json")!!.bufferedReader().use { JSONArray(it.readText()) }
        assertEquals(16, data.length())
        for (index in 0 until data.length()) {
            val case = data.getJSONObject(index)
            val r = case.getJSONObject("rule")
            val quiet = r.optJSONObject("quiet_hours")?.let {
                ReminderQuietHours(LocalTime.parse(it.getString("start")), LocalTime.parse(it.getString("end")), it.getString("timezone"))
            }
            val weekdays = r.optJSONArray("days_of_week")
            val value = ReminderRule(LocalTime.parse(r.getString("schedule_time_local")), r.getString("timezone"),
                LocalDate.parse(r.getString("start_date")), r.optString("end_date").takeIf { it.isNotEmpty() }?.let(LocalDate::parse),
                r.getString("recurrence_kind"), r.optInt("recurrence_interval", 1),
                (0 until (weekdays?.length() ?: 0)).map { weekdays!!.getInt(it) }, quiet)
            val actual = range(value, case.getString("start"), case.getString("end"))
            val expected = case.getJSONArray("expected")
            assertEquals(case.getString("name"), expected.length(), actual.size)
            actual.forEachIndexed { rowIndex, row ->
                val target = expected.getJSONObject(rowIndex)
                assertEquals(Instant.parse(target.getString("scheduled_at")), row.scheduledAt)
                assertEquals(LocalDate.parse(target.getString("local_date")), row.localDate)
                assertEquals(LocalTime.parse(target.getString("local_time")), row.localTime)
                assertEquals(case.getString("name"), target.getString("occurrence_key"), row.occurrenceKey)
                assertEquals(target.getBoolean("quiet"), row.quiet)
            }
        }
    }

    @Test fun dstGapIsSkippedAndFoldUsesEarlierInstant() {
        val ny = rule().copy(timezone = "America/New_York", startDate = LocalDate.parse("2026-03-08"),
            time = LocalTime.of(2, 30), kind = "ONCE")
        assertTrue(range(ny, "2026-03-08T00:00:00Z", "2026-03-09T00:00:00Z").isEmpty())
        val fold = ny.copy(startDate = LocalDate.parse("2026-11-01"), time = LocalTime.of(1, 30))
        assertEquals(Instant.parse("2026-11-01T05:30:00Z"), range(fold, "2026-11-01T00:00:00Z", "2026-11-02T00:00:00Z").single().scheduledAt)
    }

    @Test fun phoneTimezoneChangeDoesNotMoveReminderOrChangeKey() {
        val saved = TimeZone.getDefault()
        try {
            TimeZone.setDefault(TimeZone.getTimeZone("Pacific/Honolulu"))
            val before = range()
            TimeZone.setDefault(TimeZone.getTimeZone("Asia/Tokyo"))
            assertEquals(before, range())
            assertEquals(Instant.parse("2026-10-09T00:30:00Z"), before.first().scheduledAt)
            assertEquals(before.size, before.map { it.occurrenceKey }.distinct().size)
        } finally { TimeZone.setDefault(saved) }
    }

    @Test fun retryAndOverlappingWindowsPreserveOccurrenceIdentity() {
        assertEquals(range(), range())
        assertEquals(range().last(), range(start = "2026-10-11T00:00:00Z").single())
        val quiet = rule().copy(quiet = ReminderQuietHours(LocalTime.of(8, 0), LocalTime.of(9, 0), "Asia/Shanghai"))
        assertEquals(range().map { it.occurrenceKey }, range(quiet).map { it.occurrenceKey })
        assertTrue(range(quiet).all { it.quiet })
    }

    @Test fun quietHoursBoundariesAndEqualHoursAreExplicit() {
        val quiet = ReminderQuietHours(LocalTime.of(22, 0), LocalTime.of(7, 0), "Asia/Shanghai")
        for ((clock, expected) in listOf("21:59" to false, "22:00" to true, "00:00" to true, "06:59" to true, "07:00" to false)) {
            assertEquals(expected, ReminderCalendar.inQuietHours(java.time.OffsetDateTime.parse("2026-10-09T$clock:00+08:00").toInstant(), quiet))
        }
        assertFalse(ReminderCalendar.inQuietHours(Instant.now(), quiet.copy(end = quiet.start)))
    }

    @Test fun invalidRulesAndOffsetZonesAreRejected() {
        val changes = listOf<() -> Unit>(
            { rule().copy(timezone = "Not/A_Zone") }, { rule().copy(timezone = "+08:00") },
            { rule().copy(timezone = "GMT+08:00") }, { rule().copy(interval = 0) },
            { rule().copy(kind = "UNKNOWN") }, { rule().copy(kind = "WEEKLY") },
            { rule().copy(weekdays = listOf(0)) }, { rule().copy(kind = "WEEKLY", weekdays = listOf(7)) },
            { rule().copy(kind = "WEEKLY", weekdays = listOf(1, 1)) },
            { rule().copy(endDate = LocalDate.parse("2026-10-08")) },
            { rule().copy(time = LocalTime.of(8, 30, 0, 1)) },
            { rule().copy(startDate = LocalDate.of(10000, 1, 1)) },
        )
        changes.forEach { assertThrows(IllegalArgumentException::class.java, it) }
    }

    @Test fun oversizedReversedAndEmptyWindowsAreRejected() {
        assertThrows(IllegalArgumentException::class.java) { range(end = "2028-10-12T00:00:00Z") }
        assertThrows(IllegalArgumentException::class.java) { range(end = "2026-10-08T00:00:00Z") }
        assertThrows(IllegalArgumentException::class.java) { range(end = "2026-10-09T00:00:00Z") }
        assertThrows(IllegalArgumentException::class.java) {
            ReminderCalendar.occurrences(rule(), Instant.parse("2026-10-09T00:00:00Z"), Instant.parse("2026-10-10T00:00:00Z"), 0)
        }
    }
}
