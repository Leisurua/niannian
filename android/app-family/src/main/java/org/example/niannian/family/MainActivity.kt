package org.example.niannian.family

import android.os.Bundle
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
            val factory = object : ViewModelProvider.Factory {
                override fun <T : ViewModel> create(modelClass: Class<T>): T = modelClass.cast(
                    CompanionModel(FamilyRepository(SecureSession(applicationContext), BuildConfig.DEBUG), false, deviceId)
                )!!
            }
            val model = ViewModelProvider(this, factory)[CompanionModel::class.java]
            val runtime = RuntimeConfig.fromBuildValues(BuildConfig.ENVIRONMENT, BuildConfig.PROVIDER_MODE)
            setContent { CompanionScreen(model, runtime.statusLabel) }
        }
    }
}
