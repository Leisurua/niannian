package org.example.niannian.core.common

import java.time.Instant
import java.time.OffsetDateTime

/** Older Android ISO_INSTANT parsers reject API timestamps ending in +00:00. */
fun parseApiInstant(value: String): Instant = OffsetDateTime.parse(value).toInstant()
