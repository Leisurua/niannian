package org.example.niannian.family

import android.os.Bundle
import org.example.niannian.data.*
import org.example.niannian.feature.reminder.*
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
import org.example.niannian.feature.family.CompanionModel
import org.example.niannian.feature.family.CompanionScreen
import org.example.niannian.feature.conversation.ConversationToolsModel
import org.example.niannian.feature.conversation.ConversationToolsPanel
import org.example.niannian.feature.notification.NotificationModel
import org.example.niannian.feature.notification.NotificationPanel

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
            val toolsGateway = repository.toolsGateway()
            val notificationGateway = repository.notificationGateway()
            val memoryGateway = repository.memoryGateway()
            val reminderGateway = repository.reminderGateway()
            val factory = object : ViewModelProvider.Factory {
                override fun <T : ViewModel> create(modelClass: Class<T>): T = modelClass.cast(
                    when (modelClass) {
                        ReminderModel::class.java -> ReminderModel(reminderGateway, reminderStore, false)
                        MemoryModel::class.java -> MemoryModel(memoryGateway)
                        ConversationToolsModel::class.java -> ConversationToolsModel(toolsGateway)
                        NotificationModel::class.java -> NotificationModel(notificationGateway)
                        else -> CompanionModel(repository, false, deviceId)
                    }
                )!!
            }
            val model = ViewModelProvider(this, factory)[CompanionModel::class.java]
            val reminderModel = ViewModelProvider(this, factory)[ReminderModel::class.java]
            val memoryModel = ViewModelProvider(this, factory)[MemoryModel::class.java]
            val toolsModel = ViewModelProvider(this, factory)[ConversationToolsModel::class.java]
            val notificationModel = ViewModelProvider(this, factory)[NotificationModel::class.java]
            val runtime = RuntimeConfig.fromBuildValues(BuildConfig.ENVIRONMENT, BuildConfig.PROVIDER_MODE)
            setContent { CompanionScreen(model, runtime.statusLabel) { state, unavailable ->
                val subjects = if (model.elder) listOf(state.userId to state.userName)
                    else state.members.filter { it.role == "ELDER" && it.status == "ACTIVE" }.map { it.userId to it.name }
                if (!state.busy) ReminderPanel(reminderModel, state.selected!!.id, state.userId, subjects, unavailable)
                MemoryPanel(memoryModel, state.selected!!.id, state.userId, subjects, unavailable)
                ConversationToolsPanel(toolsModel, state.selected!!.id, subjects, false, unavailable)
                NotificationPanel(notificationModel, state.selected!!.id, state.userId, subjects, unavailable,
                    state.permissions.toString() + state.members.toString())
            } }
        }
    }
}
