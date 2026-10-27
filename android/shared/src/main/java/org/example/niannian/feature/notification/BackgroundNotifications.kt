package org.example.niannian.feature.notification

import android.Manifest
import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.job.JobInfo
import android.app.job.JobParameters
import android.app.job.JobScheduler
import android.app.job.JobService
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import kotlinx.coroutines.*
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import org.example.niannian.data.FamilyRepository
import org.json.JSONObject
import java.security.MessageDigest
import java.util.UUID

interface NotificationRepositoryOwner {
    val notificationRepository: FamilyRepository
}

/** System-scheduled inbox delivery; never claims a provider or human receipt. */
object BackgroundNotifications {
    const val NOTICE_ID = "niannian.notification.id"
    const val RECIPIENT = "niannian.notification.recipient"
    private const val JOB_ID = 7301
    private const val CHANNEL = "family-attention"
    private const val RESTORED_CHANNEL = "family-attention-restored"
    private val mutex = Mutex()
    private var generation = 0
    private fun prefs(context: Context) = context.getSharedPreferences("background-notifications", Context.MODE_PRIVATE)
    fun enabled(context: Context) = prefs(context).getBoolean("enabled", false)
    fun permitted(context: Context) = context.getSystemService(NotificationManager::class.java).areNotificationsEnabled() &&
        context.getSystemService(NotificationManager::class.java).getNotificationChannel(CHANNEL)?.importance != NotificationManager.IMPORTANCE_NONE

    fun enable(context: Context): Boolean {
        prefs(context).edit().putBoolean("enabled", true).apply()
        val scheduled = schedule(context)
        if (!scheduled) stop(context)
        return scheduled
    }

    fun schedule(context: Context): Boolean {
        if (!enabled(context)) return false
        if (context.checkSelfPermission(Manifest.permission.RECEIVE_BOOT_COMPLETED) != PackageManager.PERMISSION_GRANTED) return false
        val scheduler = context.getSystemService(JobScheduler::class.java)
        if (scheduler.getPendingJob(JOB_ID) != null) return true
        return scheduler.schedule(JobInfo.Builder(JOB_ID, ComponentName(context, NotificationSyncService::class.java))
            .setRequiredNetworkType(JobInfo.NETWORK_TYPE_ANY)
            .setPeriodic(15 * 60 * 1000L).setPersisted(true).build()) == JobScheduler.RESULT_SUCCESS
    }

    @Synchronized fun hide(context: Context) {
        generation++
        val manager = context.getSystemService(NotificationManager::class.java)
        val settings = prefs(context)
        val restore = settings.getStringSet("restore", emptySet()).orEmpty() + manager.activeNotifications.mapNotNull { it.tag }
        settings.edit().putStringSet("restore", restore).apply()
        manager.cancelAll()
    }

    fun stop(context: Context) {
        prefs(context).edit().putBoolean("enabled", false).remove("ledger").apply()
        context.getSystemService(JobScheduler::class.java).cancel(JOB_ID)
        hide(context)
        prefs(context).edit().remove("restore").apply()
    }

    suspend fun sync(context: Context, repository: FamilyRepository): Boolean = mutex.withLock {
        if (!enabled(context)) return@withLock true
        val stamp = synchronized(this) { generation }
        try {
            val user = repository.savedUserId()
            if (!repository.hasSession() || user.isBlank()) { stop(context); return@withLock true }
            if (!permitted(context)) { hide(context); return@withLock true }
            val scope = MessageDigest.getInstance("SHA-256").digest((repository.savedOrigin() + ":" + user).toByteArray())
                .joinToString("") { "%02x".format(it) }
            val items = repository.readAll("/v1/notifications/mobile-inbox?limit=100")
            currentCoroutineContext().ensureActive()
            if (repository.savedUserId() != user) return@withLock true
            val ids = items.map { UUID.fromString(it.getString("id")).toString() }.toSet()
            synchronized(this) {
                if (stamp != generation || !enabled(context)) return@withLock true
                val settings = prefs(context)
                val ledger = MobileNotificationLedger.parse(settings.getString("ledger", null), scope)
                val manager = context.getSystemService(NotificationManager::class.java)
                manager.createNotificationChannel(NotificationChannel(CHANNEL, "家人关注提示", NotificationManager.IMPORTANCE_DEFAULT)
                    .apply { description = "已授权的关注事件；点击后核验并处理"; lockscreenVisibility = Notification.VISIBILITY_PRIVATE })
                manager.createNotificationChannel(NotificationChannel(RESTORED_CHANNEL, "关注提示恢复", NotificationManager.IMPORTANCE_LOW)
                    .apply { setSound(null, null); enableVibration(false); lockscreenVisibility = Notification.VISIBILITY_PRIVATE })
                val posted = manager.activeNotifications.mapNotNull { it.tag }.toSet()
                posted.filter { it !in ids }.forEach { manager.cancel(it, 0) }
                for (id in ledger.toPost(ids, settings.getStringSet("restore", emptySet()).orEmpty())) {
                    val launch = context.packageManager.getLaunchIntentForPackage(context.packageName) ?: continue
                    launch.data = Uri.parse("niannian-internal://notification/$id")
                    launch.addFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP or Intent.FLAG_ACTIVITY_SINGLE_TOP)
                    launch.putExtra(NOTICE_ID, id).putExtra(RECIPIENT, user)
                    val pending = PendingIntent.getActivity(context, 0, launch, PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
                    val notice = Notification.Builder(context, if (id in ledger.seen) RESTORED_CHANNEL else CHANNEL)
                        .setSmallIcon(android.R.drawable.ic_dialog_info).setContentTitle("念念 · 家人关注")
                        .setContentText("有一条关注提示（Mock 识别），点击核实并处理。")
                        .setContentIntent(pending).setAutoCancel(true).setOnlyAlertOnce(true)
                        .setVisibility(Notification.VISIBILITY_PRIVATE).setCategory(Notification.CATEGORY_SOCIAL)
                        .setTimeoutAfter(30 * 60 * 1000L).build()
                    manager.notify(id, 0, notice)
                }
                settings.edit().putString("ledger", ledger.recordSeenIds(ids).toString()).remove("restore").apply()
            }
            true
        } catch (cancelled: CancellationException) { throw cancelled }
        catch (_: Exception) {
            hide(context)
            false
        }
    }
}

class NotificationSyncService : JobService() {
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private var job: Job? = null
    override fun onStartJob(params: JobParameters): Boolean {
        val owner = application as? NotificationRepositoryOwner ?: return false
        job = scope.launch {
            var retry = true
            try { retry = !withTimeout(120000) { BackgroundNotifications.sync(applicationContext, owner.notificationRepository) } }
            catch (_: TimeoutCancellationException) { BackgroundNotifications.hide(applicationContext) }
            finally { if (isActive) jobFinished(params, retry) }
        }
        return true
    }
    override fun onStopJob(params: JobParameters): Boolean { job?.cancel(); return BackgroundNotifications.enabled(this) }
    override fun onDestroy() { scope.cancel(); super.onDestroy() }
}

internal data class MobileNotificationLedger(val scope: String, val seen: Map<String, Long>) {
    fun toPost(current: Set<String>, restore: Set<String> = emptySet()): Set<String> = current.filter {
        it !in seen || it in restore
    }.toSet()
    fun recordSeenIds(current: Set<String>, now: Long = System.currentTimeMillis()): JSONObject {
        val history = JSONObject()
        seen.filterValues { it > now - 7 * 86400000L }.forEach { (id, time) -> history.put(id, time) }
        current.forEach { if (!history.has(it)) history.put(it, now) }
        return JSONObject().put("scope", scope).put("seen", history)
    }
    companion object {
        fun parse(raw: String?, scope: String): MobileNotificationLedger {
            val value = runCatching { JSONObject(raw ?: "{}") }.getOrDefault(JSONObject())
            if (value.optString("scope") != scope) return MobileNotificationLedger(scope, emptyMap())
            val seen = value.optJSONObject("seen") ?: JSONObject()
            return MobileNotificationLedger(scope, seen.keys().asSequence().associateWith { seen.getLong(it) })
        }
    }
}
