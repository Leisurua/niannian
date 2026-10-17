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

/** Elder-only registration. Inexact alarms are an observed fallback, never exact delivery. */
object ReminderScheduler {
    private const val NOTIFICATION = 501
    private const val CHANNEL = "local-reminders"
    private fun intent(context: Context) = PendingIntent.getBroadcast(context, 501,
        Intent(context, ReminderReceiver::class.java), PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
    fun arm(context: Context) {
        context.getSystemService(AlarmManager::class.java).setAndAllowWhileIdle(AlarmManager.RTC_WAKEUP,
            System.currentTimeMillis() + 60000, intent(context))
    }
    fun cancel(context: Context) {
        context.getSystemService(AlarmManager::class.java).cancel(intent(context))
        context.getSystemService(NotificationManager::class.java).cancel(NOTIFICATION)
    }
    suspend fun check(context: Context) {
        val storage = ReminderStorage.get(context)
        val ledger = ReminderLedger(storage)
        val snapshot = ledger.snapshot()
        if ((snapshot.optJSONArray("rules")?.length() ?: 0) == 0) {
            cancel(context)
            if ((snapshot.optJSONObject("occurrences")?.length() ?: 0) > 0) arm(context)
            return
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
                // Records notification submission, not delivery or medication completion.
                if (submitted) ledger.presented(due)
            }
        }
        arm(context)
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
