package org.example.niannian.elder

import android.app.Activity
import android.app.ActivityManager
import android.app.KeyguardManager
import android.app.admin.DeviceAdminReceiver
import android.app.admin.DevicePolicyManager
import android.content.BroadcastReceiver
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.content.pm.PackageManager
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.flow.MutableStateFlow

class TabletAdminReceiver : DeviceAdminReceiver()

class TabletRecoveryReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action != "org.example.niannian.elder.EXIT_TABLET_MODE") return
        val released = TabletPolicy(context).release()
        setResultCode(if (released) Activity.RESULT_OK else Activity.RESULT_CANCELED)
        setResultData(if (released) "Tablet mode released" else "Tablet policy could not be released")
    }
}

private class TabletPolicy(private val context: Context) {
    private val manager = context.getSystemService(DevicePolicyManager::class.java)
    private val admin = ComponentName(context, TabletAdminReceiver::class.java)
    private val home = ComponentName(context.packageName, "org.example.niannian.elder.TabletHome")
    private val packages = context.packageManager
    val owner: Boolean get() = manager.isDeviceOwnerApp(context.packageName)
    val configured: Boolean get() = owner && manager.isLockTaskPermitted(context.packageName) &&
        packages.getComponentEnabledSetting(home) == PackageManager.COMPONENT_ENABLED_STATE_ENABLED

    fun configure() {
        check(owner)
        setHomeEnabled(true)
        manager.addPersistentPreferredActivity(admin, IntentFilter(Intent.ACTION_MAIN).apply {
            addCategory(Intent.CATEGORY_HOME)
            addCategory(Intent.CATEGORY_DEFAULT)
        }, home)
        manager.setLockTaskPackages(admin, arrayOf(context.packageName))
        check(configured)
    }

    fun release(): Boolean {
        if (!owner) return false
        val homeReleased = runCatching { manager.clearPackagePersistentPreferredActivities(admin, context.packageName) }
        val taskReleased = runCatching { manager.setLockTaskPackages(admin, emptyArray()) }
        val aliasReleased = runCatching { setHomeEnabled(false) }
        return homeReleased.isSuccess && taskReleased.isSuccess && aliasReleased.isSuccess
    }

    private fun setHomeEnabled(enabled: Boolean) {
        packages.setComponentEnabledSetting(home,
            if (enabled) PackageManager.COMPONENT_ENABLED_STATE_ENABLED else PackageManager.COMPONENT_ENABLED_STATE_DISABLED,
            PackageManager.DONT_KILL_APP)
    }
}

internal class TabletMode(private val activity: Activity) {
    private val policy = TabletPolicy(activity)
    private val activities = activity.getSystemService(ActivityManager::class.java)
    private val keyguard = activity.getSystemService(KeyguardManager::class.java)
    private val status = MutableStateFlow("")
    val locked: Boolean get() = policy.configured && activities.lockTaskModeState == ActivityManager.LOCK_TASK_MODE_LOCKED

    fun resume() {
        status.value = when {
            !policy.owner -> "普通应用模式。启用单应用锁定需要管理员先配置设备所有者。"
            !policy.configured -> "普通应用模式。设备所有者已配置，可以启用平板模式。"
            keyguard.isKeyguardLocked -> "解锁平板后进入单应用模式。"
            else -> runCatching {
                if (!locked) activity.startLockTask()
                if (locked) "单应用模式已启用。重启并解锁后由系统进入念念。"
                else "系统尚未进入单应用锁定，请由管理员检查平板策略。"
            }.getOrElse {
                if (policy.release()) "无法启动单应用锁定，已恢复普通应用模式。"
                else "无法启动单应用锁定，请管理员通过维护命令恢复。"
            }
        }
    }

    private fun activate() {
        if (!policy.owner) return
        try {
            policy.configure()
            resume()
        } catch (_: Exception) {
            status.value = if (policy.release()) "平板模式配置失败，已恢复普通应用模式。"
                else "平板模式配置失败，请管理员通过维护命令恢复。"
        }
    }

    @Composable
    fun Settings() {
        val current by status.collectAsState()
        var confirming by remember { mutableStateOf(false) }
        Text("专用平板模式", fontSize = 22.sp)
        Text(current, fontSize = 18.sp)
        if (policy.owner && !locked) {
            Button(onClick = { confirming = true }, modifier = Modifier.fillMaxWidth().heightIn(min = 52.dp)) {
                Text("启用平板模式", fontSize = 18.sp)
            }
        }
        if (confirming) {
            AlertDialog(onDismissRequest = { confirming = false }, title = { Text("启用单应用锁定？") },
                text = { Text("启用后，此平板开机解锁会进入念念，普通使用时无法返回系统桌面。恢复由管理员在维护终端完成。") },
                confirmButton = { Button(onClick = { confirming = false; activate() }) { Text("启用") } },
                dismissButton = { TextButton(onClick = { confirming = false }) { Text("取消") } })
        }
    }
}
