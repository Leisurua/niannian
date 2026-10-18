package org.example.niannian.elder

import android.os.Bundle
import org.example.niannian.feature.reminder.*
import org.example.niannian.feature.memory.MemoryFailure
import org.example.niannian.feature.auth.ApiFailure
import org.example.niannian.feature.memory.MemoryGateway
import org.example.niannian.feature.memory.MemoryModel
import org.example.niannian.feature.memory.MemoryPanel
import org.json.JSONObject
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import java.util.UUID
import org.example.niannian.core.common.RuntimeConfig
import org.example.niannian.core.telemetry.AppExecutionBoundary
import org.example.niannian.core.telemetry.TelemetryLogger
import org.example.niannian.feature.auth.CompanionModel
import org.example.niannian.feature.auth.CompanionScreen
import org.example.niannian.feature.auth.FamilyRepository
import org.example.niannian.feature.auth.SecureSession
import org.example.niannian.feature.auth.ConversationToolsGateway
import org.example.niannian.feature.auth.ConversationToolsModel
import org.example.niannian.feature.auth.ConversationToolsPanel
import org.example.niannian.feature.conversation.ConversationGateway
import org.example.niannian.feature.conversation.ConversationModel
import org.example.niannian.feature.conversation.ConversationPanel
import org.example.niannian.feature.conversation.ConversationTransport

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        AppExecutionBoundary().run {
            super.onCreate(savedInstanceState)
            TelemetryLogger().info("APP_STARTED", mapOf("provider" to BuildConfig.PROVIDER_MODE))
            val preferences = getSharedPreferences("device-config", MODE_PRIVATE)
            val deviceId = preferences.getString("device-id", null) ?: UUID.randomUUID().toString().also {
                preferences.edit().putString("device-id", it).apply()
            }
            val reminderStore = ReminderStorage.get(applicationContext)
            val repository = FamilyRepository(SecureSession(applicationContext) { reminderStore.revokeEncryptionKey(); ReminderScheduler.cancel(applicationContext) }, BuildConfig.DEBUG,
                onCacheInvalidated = { reminderStore.revokeEncryptionKey(); ReminderScheduler.cancel(applicationContext) })
            val transport = ConversationTransport()
            val toolsGateway = object : ConversationToolsGateway {
                override suspend fun call(path: String, method: String, body: JSONObject?, version: Long?, reason: String?) =
                    repository.call(path, method, body, method == "POST" && (path.endsWith("/confirm") || path.endsWith("/pause-today")), version, reason)
            }
            val conversationGateway = object : ConversationGateway {
                override suspend fun create(family: String) = repository.call("/v1/conversations", "POST",
                    JSONObject().put("family_id", family).put("input_mode", "TEXT")).getString("id")
                override suspend fun status(id: String) = repository.call("/v1/conversations/$id").getString("status")
                override suspend fun end(id: String) { repository.call("/v1/conversations/$id/end", "POST", JSONObject().put("reason", "USER")) }
                override suspend fun connect(id: String, message: (String) -> Unit, closed: (Int) -> Unit) =
                    repository.withConversationConnection(id) { url, token -> transport.connect(url, token, message, closed) }
            }
            val memoryGateway = object : MemoryGateway {
                override suspend fun call(path: String, method: String, body: JSONObject?, idempotent: Boolean, version: Long?) = try { repository.call(path, method, body, idempotent, version) } catch (failure: ApiFailure) { throw MemoryFailure(failure.message ?: "请求未完成，请重试。") }
                override suspend fun list(path: String) = try { repository.readAll(path) } catch (failure: ApiFailure) { throw MemoryFailure(failure.message ?: "请求未完成，请重试。") }
                override suspend fun upload(url: String, headers: JSONObject, bytes: ByteArray) = try { repository.uploadPhoto(url, headers, bytes) } catch (failure: ApiFailure) { throw MemoryFailure(failure.message ?: "请求未完成，请重试。") }
                override suspend fun download(url: String) = try { repository.downloadPhoto(url) } catch (failure: ApiFailure) { throw MemoryFailure(failure.message ?: "请求未完成，请重试。") }
                override suspend fun retry() { repository.retryMemoryPending() }
                override fun hasPending() = repository.hasPending()
            }
            val reminderGateway = object : ReminderGateway {
                override suspend fun list(path: String) = try { repository.readAll(path) } catch (failure: ApiFailure) { throw ReminderFailure(failure.status) }
                override suspend fun call(path: String, method: String, body: JSONObject?, key: String?, version: Long?) = try {
                    if (key != null) repository.submitOfflineFeedback(path, body!!, key)
                    else repository.call(path, method, body, method == "POST", version)
                } catch (failure: ApiFailure) { throw ReminderFailure(failure.status) }
            }
            val factory = object : ViewModelProvider.Factory {
                override fun <T : ViewModel> create(modelClass: Class<T>): T = modelClass.cast(
                    when (modelClass) {
                        ReminderModel::class.java -> ReminderModel(reminderGateway, reminderStore, true, onCacheChanged = { ReminderScheduler.arm(applicationContext) })
                        MemoryModel::class.java -> MemoryModel(memoryGateway)
                        ConversationModel::class.java -> ConversationModel(conversationGateway)
                        ConversationToolsModel::class.java -> ConversationToolsModel(toolsGateway)
                        else -> CompanionModel(repository, true, deviceId)
                    }
                )!!
            }
            val model = ViewModelProvider(this, factory)[CompanionModel::class.java]
            val reminderModel = ViewModelProvider(this, factory)[ReminderModel::class.java]
            val memoryModel = ViewModelProvider(this, factory)[MemoryModel::class.java]
            val conversationModel = ViewModelProvider(this, factory)[ConversationModel::class.java]
            val toolsModel = ViewModelProvider(this, factory)[ConversationToolsModel::class.java]
            val runtime = RuntimeConfig.fromBuildValues(BuildConfig.ENVIRONMENT, BuildConfig.PROVIDER_MODE)
            setContent { CompanionScreen(model, runtime.statusLabel, offlineContent = { CachedReminderEntry(reminderModel, reminderStore, repository.savedUserId()) { ReminderScheduler.arm(applicationContext) } }) { state, unavailable ->
                val subjects = if (model.elder) listOf(state.userId to state.userName)
                    else state.members.filter { it.role == "ELDER" && it.status == "ACTIVE" }.map { it.userId to it.name }
                if (!state.busy) ReminderPanel(reminderModel, state.selected!!.id, state.userId, subjects, unavailable) { ReminderScheduler.arm(applicationContext) }
                MemoryPanel(memoryModel, state.selected!!.id, state.userId, subjects, unavailable)
                ConversationPanel(conversationModel, state.selected!!.id, state.userId, unavailable)
                val conversationState by conversationModel.state.collectAsState()
                ConversationToolsPanel(toolsModel, state.selected!!.id, subjects, true, unavailable,
                    conversationState.recapId.ifEmpty { conversationState.id })
            } }
        }
    }
}
