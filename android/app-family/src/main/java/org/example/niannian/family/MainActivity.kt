package org.example.niannian.family

import android.os.Bundle
import android.content.Intent
import androidx.compose.runtime.*
import org.example.niannian.data.*
import org.example.niannian.feature.reminder.*
import org.example.niannian.feature.message.MessageModel
import org.example.niannian.feature.memory.MemoryModel
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
import org.example.niannian.feature.notification.NotificationModel
import org.example.niannian.feature.notification.BackgroundNotifications
import org.example.niannian.feature.notification.BackgroundNotificationSettings
import org.example.niannian.feature.notification.NotificationEntry
import org.example.niannian.feature.notification.NotificationLaunch
import org.example.niannian.feature.notification.validatedNotificationLaunch
import org.example.niannian.feature.notification.parseNotificationLink

class MainActivity : ComponentActivity() {
    private var notificationLaunch by mutableStateOf<NotificationLaunch?>(null)
    private fun acceptNotification(intent: Intent?) {
        if (intent?.action == Intent.ACTION_VIEW) {
            notificationLaunch = parseNotificationLink(intent.dataString)
        } else {
            validatedNotificationLaunch(intent?.getStringExtra(BackgroundNotifications.NOTICE_ID),
                intent?.getStringExtra(BackgroundNotifications.RECIPIENT))?.let { notificationLaunch = it }
        }
    }
    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent); setIntent(intent); acceptNotification(intent)
    }
    override fun onCreate(savedInstanceState: Bundle?) {
        AppExecutionBoundary().run {
            super.onCreate(savedInstanceState)
            acceptNotification(intent)
            TelemetryLogger().info("APP_STARTED", mapOf("provider" to BuildConfig.PROVIDER_MODE))
            val preferences = getSharedPreferences("device-config", MODE_PRIVATE)
            val deviceId = preferences.getString("device-id", null) ?: UUID.randomUUID().toString().also {
                preferences.edit().putString("device-id", it).apply()
            }
            val reminderStore = EphemeralReminderStore()
            val repository = (application as FamilyApplication).notificationRepository
            val toolsGateway = repository.toolsGateway()
            val notificationGateway = repository.notificationGateway()
            val messageGateway = repository.messageGateway(deviceId, false)
            val memoryGateway = repository.memoryGateway()
            val reminderGateway = repository.reminderGateway()
            val factory = object : ViewModelProvider.Factory {
                override fun <T : ViewModel> create(modelClass: Class<T>): T = modelClass.cast(
                    when (modelClass) {
                        ReminderModel::class.java -> ReminderModel(reminderGateway, reminderStore, false)
                        MemoryModel::class.java -> MemoryModel(memoryGateway)
                        MessageModel::class.java -> MessageModel(messageGateway, false)
                        ConversationToolsModel::class.java -> ConversationToolsModel(toolsGateway)
                        NotificationModel::class.java -> NotificationModel(notificationGateway)
                        else -> CompanionModel(repository, false, deviceId)
                    }
                )!!
            }
            val model = ViewModelProvider(this, factory)[CompanionModel::class.java]
            val reminderModel = ViewModelProvider(this, factory)[ReminderModel::class.java]
            val memoryModel = ViewModelProvider(this, factory)[MemoryModel::class.java]
            val messageModel = ViewModelProvider(this, factory)[MessageModel::class.java]
            val toolsModel = ViewModelProvider(this, factory)[ConversationToolsModel::class.java]
            val notificationModel = ViewModelProvider(this, factory)[NotificationModel::class.java]
            val runtime = RuntimeConfig.fromBuildValues(BuildConfig.ENVIRONMENT, BuildConfig.PROVIDER_MODE)
            setContent {
                val account by model.state.collectAsState()
                CompanionScreen(model, runtime.statusLabel, reminderModel, memoryModel, toolsModel,
                    messages = messageModel,
                    notificationSettings = { BackgroundNotificationSettings(repository, account.userId) },
                    notifications = notificationModel)
                NotificationEntry(repository, notificationLaunch, account.userId, account.loggedIn) {
                    notificationLaunch = null
                    intent.removeExtra(BackgroundNotifications.NOTICE_ID)
                    intent.removeExtra(BackgroundNotifications.RECIPIENT)
                    intent.data = null
                }
            }
        }
    }
}
