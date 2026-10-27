package org.example.niannian.family

import android.app.Application
import org.example.niannian.data.FamilyRepository
import org.example.niannian.data.SecureSession
import org.example.niannian.feature.notification.BackgroundNotifications
import org.example.niannian.feature.notification.NotificationRepositoryOwner

class FamilyApplication : Application(), NotificationRepositoryOwner {
    override val notificationRepository by lazy {
        FamilyRepository(SecureSession(this) { BackgroundNotifications.stop(this) }, BuildConfig.DEBUG,
            onCacheInvalidated = { BackgroundNotifications.hide(this) })
    }
}
