package org.example.niannian.data

import org.example.niannian.feature.memory.*
import org.example.niannian.feature.reminder.*
import org.example.niannian.feature.conversation.ConversationToolsGateway
import org.example.niannian.feature.notification.NotificationGateway
import org.json.JSONObject
import org.example.niannian.feature.message.MessageGateway

fun FamilyRepository.messageGateway(deviceId: String, elder: Boolean): MessageGateway {
    val repository = this
    return object : MessageGateway {
        override suspend fun register(family: String) {
            repository.registerMessageDevice(JSONObject().put("device_id", deviceId).put("family_id", family)
                .put("device_type", if (elder) "ANDROID_TABLET" else "ANDROID_PHONE")
                .put("client_kind", if (elder) "ELDER_MOBILE" else "FAMILY_MOBILE")
                .put("app_version", "0.1.0").put("os_version", "Android ${android.os.Build.VERSION.RELEASE}".take(64))
                .put("capabilities", JSONObject().put("rest_polling", true)))
        }
        override suspend fun list(family: String, box: String) = repository.readAll("/v1/messages?family_id=$family&box=$box&limit=100")
        override suspend fun acknowledge(id: String, read: Boolean) = repository.acknowledgeMessage(id, read)
        override suspend fun send(family: String, role: String, text: String) = repository.call("/v1/messages", "POST",
            JSONObject().put("family_id", family).put("destination", JSONObject().put("type", "FAMILY_ROLE").put("role", role))
                .put("message_type", "TEXT").put("priority", "NORMAL").put("payload", JSONObject().put("text", text)), true)
    }
}

fun FamilyRepository.memoryGateway(): MemoryGateway {
    val repository = this
    return object : MemoryGateway {
        override suspend fun call(path: String, method: String, body: JSONObject?, idempotent: Boolean, version: Long?) = repository.call(path, method, body, idempotent, version)
        override suspend fun list(path: String) = repository.readAll(path)
        override suspend fun upload(url: String, headers: JSONObject, bytes: ByteArray) = repository.uploadPhoto(url, headers, bytes)
        override suspend fun download(url: String) = repository.downloadPhoto(url)
        override suspend fun retry() { repository.retryMemoryPending() }
        override fun hasPending() = repository.hasPending()
    }
}

fun FamilyRepository.reminderGateway(): ReminderGateway {
    val repository = this
    return object : ReminderGateway {
        override suspend fun list(path: String) = repository.readAll(path)
        override suspend fun call(path: String, method: String, body: JSONObject?, key: String?, version: Long?) =
            if (key != null) repository.submitOfflineFeedback(path, body!!, key)
            else repository.call(path, method, body, method == "POST", version)
    }
}

fun FamilyRepository.toolsGateway(): ConversationToolsGateway {
    val repository = this
    return object : ConversationToolsGateway {
        override suspend fun call(path: String, method: String, body: JSONObject?, version: Long?, reason: String?) =
                    repository.call(path, method, body, method == "POST" && (path.endsWith("/confirm") || path.endsWith("/pause-today")), version, reason)
    }
}

fun FamilyRepository.notificationGateway(): NotificationGateway {
    val repository = this
    return object : NotificationGateway {
        override suspend fun list() = repository.readAll("/v1/notifications?limit=100")
        override suspend fun events(family: String) = repository.readAll("/v1/signal-events?family_id=$family&limit=100")
        override suspend fun call(path: String, method: String, body: JSONObject?, version: Long?) =
                    repository.call(path, method, body, false, version)
        override suspend fun read(id: String, key: String) = repository.markNotificationRead(id, key)
        override suspend fun act(id: String, body: JSONObject, key: String) = repository.handleSignal(id, body, key)
    }
}
