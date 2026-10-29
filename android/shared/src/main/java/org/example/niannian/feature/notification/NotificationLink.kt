package org.example.niannian.feature.notification

import java.net.URI
import java.util.UUID

data class NotificationLaunch(val id: String, val recipient: String)

fun validatedNotificationLaunch(id: String?, recipient: String?): NotificationLaunch? = runCatching {
    require(id != null && recipient != null)
    require(UUID.fromString(id).toString() == id && UUID.fromString(recipient).toString() == recipient)
    NotificationLaunch(id, recipient)
}.getOrNull()

/** Links carry routing IDs only. Opening still requires server authorization. */
fun parseNotificationLink(raw: String?): NotificationLaunch? = runCatching {
    require(raw != null && raw.length <= 160)
    val uri = URI(raw)
    require(uri.scheme == "niannian-family" && uri.rawAuthority == "notification")
    require(uri.rawQuery == null && uri.rawFragment == null && uri.rawPath == uri.path)
    val parts = uri.path.split('/')
    require(parts.size == 3 && parts[0].isEmpty())
    validatedNotificationLaunch(parts[1], parts[2])
}.getOrNull()

fun validPushSubscription(raw: String?): String? = runCatching {
    require(raw != null && raw.length <= 512)
    val uri = URI(raw)
    require(uri.scheme == "ntfy" && !uri.host.isNullOrBlank() && uri.rawUserInfo == null)
    require(uri.rawQuery == null && uri.rawFragment == null && uri.rawPath == uri.path)
    require(uri.path.matches(Regex("/[A-Za-z0-9_-]{1,64}")))
    raw
}.getOrNull()
