package org.example.niannian.family

import android.app.Application
import android.app.job.JobInfo
import android.app.job.JobScheduler
import android.content.ComponentName
import org.example.niannian.data.FamilyRepository
import org.example.niannian.data.SecureSession
import org.example.niannian.feature.notification.BackgroundNotifications
import org.example.niannian.feature.notification.NotificationRepositoryOwner
import org.example.niannian.feature.notification.NotificationSyncService

class FamilyApplication : Application(), NotificationRepositoryOwner {
    override fun scheduleNotificationSync(): Boolean {
        val scheduler = getSystemService(JobScheduler::class.java)
        if (scheduler.getPendingJob(BackgroundNotifications.JOB_ID) != null) return true
        return scheduler.schedule(JobInfo.Builder(BackgroundNotifications.JOB_ID, ComponentName(this, NotificationSyncService::class.java))
            .setRequiredNetworkType(JobInfo.NETWORK_TYPE_ANY)
            .setPeriodic(15 * 60 * 1000L).setPersisted(true).build()) == JobScheduler.RESULT_SUCCESS
    }

    override val notificationRepository by lazy {
        FamilyRepository(SecureSession(this) { BackgroundNotifications.stop(this) }, BuildConfig.DEBUG,
            onCacheInvalidated = { BackgroundNotifications.hide(this) })
    }
}
