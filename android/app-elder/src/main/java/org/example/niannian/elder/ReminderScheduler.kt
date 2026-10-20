package org.example.niannian.elder

import org.example.niannian.feature.reminder.ReminderLedger
import org.example.niannian.feature.reminder.ReminderStorage

import android.Manifest
import android.app.AlarmManager
import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withTimeout
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock

/** Elder-only registration. Inexact alarms are an observed fallback, never exact delivery. */
object ReminderScheduler {
    private const val NOTIFICATION = 501
    private const val CHANNEL = "local-reminders"
    private val mutex = Mutex()
    private fun intent(context: Context) = PendingIntent.getBroadcast(context, 501,
        Intent(context, ReminderReceiver::class.java), PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
    fun arm(context: Context) {
        val application = context.applicationContext
        CoroutineScope(Dispatchers.IO).launch {
            try { withTimeout(8000) { mutex.withLock { scheduleNext(application) } } }
            catch (_: Exception) { cancel(application) }
        }
    }
    private suspend fun scheduleNext(context: Context) {
        val storage = ReminderStorage.get(context)
        val ledger = ReminderLedger(storage)
        val snapshot = ledger.snapshot()
        val next = ledger.nextCheckAt()
        storage.whenCurrent(snapshot) {
            val alarms = context.getSystemService(AlarmManager::class.java)
            if (next == null) cancel(context)
            else alarms.setAndAllowWhileIdle(AlarmManager.RTC_WAKEUP,
                maxOf(System.currentTimeMillis() + 1000, next.toEpochMilli()), intent(context))
        }
    }
    fun cancel(context: Context) {
        context.getSystemService(AlarmManager::class.java).cancel(intent(context))
        context.getSystemService(NotificationManager::class.java).cancel(NOTIFICATION)
    }
    suspend fun check(context: Context) = mutex.withLock {
        val storage = ReminderStorage.get(context)
        val ledger = ReminderLedger(storage)
        val snapshot = ledger.snapshot()
        if ((snapshot.optJSONArray("rules")?.length() ?: 0) == 0) {
            cancel(context)
            scheduleNext(context)
            return@withLock
        }
        val due = ledger.notificationCandidates()
        val manager = context.getSystemService(NotificationManager::class.java)
        manager.createNotificationChannel(NotificationChannel(CHANNEL, "本人提醒", NotificationManager.IMPORTANCE_DEFAULT))
        val permitted = Build.VERSION.SDK_INT < 33 || context.checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) == PackageManager.PERMISSION_GRANTED
        if (due.isNotEmpty() && permitted && manager.areNotificationsEnabled() && manager.getNotificationChannel(CHANNEL).importance != NotificationManager.IMPORTANCE_NONE) {
            val launch = context.packageManager.getLaunchIntentForPackage(context.packageName)
            if (launch != null) {
                val pending = PendingIntent.getActivity(context, 501, launch, PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
                val submitted = storage.whenCurrent(snapshot) { manager.notify(NOTIFICATION, Notification.Builder(context, CHANNEL)
                    .setSmallIcon(android.R.drawable.ic_popup_reminder).setContentTitle("念念提醒")
                    .setContentText("有一条本人提醒，请打开念念查看。")
                    .setVisibility(Notification.VISIBILITY_PRIVATE).setOnlyAlertOnce(true).setAutoCancel(true)
                    .setContentIntent(pending).build()) }
                if (submitted) ledger.recordNotificationSubmission(due)
            }
        }
        scheduleNext(context)
    }
}

class ReminderReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        val pending = goAsync()
        CoroutineScope(Dispatchers.IO).launch {
            try { withTimeout(8000) { ReminderScheduler.check(context.applicationContext) } }
            catch (_: Exception) { ReminderScheduler.cancel(context) }
            finally { pending.finish() }
        }
    }
}
