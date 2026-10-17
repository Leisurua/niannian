package org.example.niannian.family

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

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        AppExecutionBoundary().run {
            super.onCreate(savedInstanceState)
            TelemetryLogger().info("APP_STARTED", mapOf("provider" to BuildConfig.PROVIDER_MODE))
            val preferences = getSharedPreferences("device-config", MODE_PRIVATE)
            val deviceId = preferences.getString("device-id", null) ?: UUID.randomUUID().toString().also {
                preferences.edit().putString("device-id", it).apply()
            }
            val reminderStore = EphemeralReminderStore()
            val repository = FamilyRepository(SecureSession(applicationContext), BuildConfig.DEBUG)
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
                        ReminderModel::class.java -> ReminderModel(reminderGateway, reminderStore, false)
                        MemoryModel::class.java -> MemoryModel(memoryGateway)
                        else -> CompanionModel(repository, false, deviceId)
                    }
                )!!
            }
            val model = ViewModelProvider(this, factory)[CompanionModel::class.java]
            val reminderModel = ViewModelProvider(this, factory)[ReminderModel::class.java]
            val memoryModel = ViewModelProvider(this, factory)[MemoryModel::class.java]
            val runtime = RuntimeConfig.fromBuildValues(BuildConfig.ENVIRONMENT, BuildConfig.PROVIDER_MODE)
            setContent { CompanionScreen(model, runtime.statusLabel) { state, unavailable ->
                val subjects = if (model.elder) listOf(state.userId to state.userName)
                    else state.members.filter { it.role == "ELDER" && it.status == "ACTIVE" }.map { it.userId to it.name }
                if (!state.busy) ReminderPanel(reminderModel, state.selected!!.id, state.userId, subjects, unavailable)
                MemoryPanel(memoryModel, state.selected!!.id, state.userId, subjects, unavailable)
            } }
        }
    }
}
