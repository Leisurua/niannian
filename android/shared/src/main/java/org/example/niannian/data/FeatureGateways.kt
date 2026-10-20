package org.example.niannian.data

import org.example.niannian.feature.memory.*
import org.example.niannian.feature.reminder.*
import org.example.niannian.feature.conversation.ConversationToolsGateway
import org.example.niannian.feature.notification.NotificationGateway
import org.json.JSONObject

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
        override suspend fun call(path: String, method: String, body: JSONObject?, version: Long?) =
                    repository.call(path, method, body, false, version)
        override suspend fun read(id: String, key: String) = repository.markNotificationRead(id, key)
    }
}
