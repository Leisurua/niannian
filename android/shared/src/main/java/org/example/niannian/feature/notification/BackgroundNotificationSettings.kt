package org.example.niannian.feature.notification

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import android.provider.Settings
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.compose.LocalLifecycleOwner
import kotlinx.coroutines.delay
import org.example.niannian.data.FamilyRepository

@Composable
fun BackgroundNotificationSettings(repository: FamilyRepository, user: String) {
    val context = LocalContext.current.applicationContext
    val lifecycle = LocalLifecycleOwner.current.lifecycle
    var foreground by remember { mutableStateOf(lifecycle.currentState.isAtLeast(Lifecycle.State.STARTED)) }
    var enabled by remember { mutableStateOf(BackgroundNotifications.enabled(context)) }
    var permitted by remember { mutableStateOf(BackgroundNotifications.permitted(context)) }
    var message by remember { mutableStateOf("") }
    fun enable() {
        enabled = runCatching { BackgroundNotifications.enable(context) }.getOrDefault(false)
        message = if (enabled) "已开启，界面关闭后由系统定期同步。" else "系统未允许安排后台任务，请重试。"
    }
    val permission = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
        permitted = granted && BackgroundNotifications.permitted(context)
        if (permitted) enable() else message = "系统通知权限未开启，可进入通知设置允许。"
    }
    DisposableEffect(lifecycle) {
        val observer = LifecycleEventObserver { _, event ->
            if (event == Lifecycle.Event.ON_START) {
                foreground = true; enabled = BackgroundNotifications.enabled(context)
                permitted = BackgroundNotifications.permitted(context)
            }
            if (event == Lifecycle.Event.ON_STOP) foreground = false
        }
        lifecycle.addObserver(observer)
        onDispose { lifecycle.removeObserver(observer) }
    }
    LaunchedEffect(foreground, enabled, permitted, user) {
        if (!foreground || !enabled || !permitted || user.isBlank()) return@LaunchedEffect
        BackgroundNotifications.schedule(context)
        while (true) {
            val success = BackgroundNotifications.sync(context, repository)
            enabled = BackgroundNotifications.enabled(context)
            if (!success) message = "暂未同步成功，请检查网络；后台任务会继续重试。"
            if (!enabled) break
            delay(30000)
        }
    }
    Card(Modifier.fillMaxWidth().padding(vertical = 8.dp)) {
        Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Text("本机后台通知：" + if (enabled && permitted) "已开启" else "未开启")
            Text("关闭界面后仍由系统同步，通常每 15 分钟一次，省电时可能延迟。点击通知可进入处理。")
            Text("及时通知请在家庭设置完成 ntfy 订阅，并在对应长辈的通知偏好开启推送；本机定期收件可用于补收。")
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                if (enabled) TextButton(onClick = { BackgroundNotifications.stop(context); enabled = false; message = "本机后台通知已关闭。" }) { Text("关闭本机通知") }
                else Button(onClick = {
                    if (Build.VERSION.SDK_INT >= 33 && context.checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED)
                        permission.launch(Manifest.permission.POST_NOTIFICATIONS)
                    else if (BackgroundNotifications.permitted(context)) enable()
                    else message = "请在系统通知设置中允许念念发送通知。"
                }) { Text("开启本机后台通知") }
                TextButton(onClick = {
                    context.startActivity(Intent(Settings.ACTION_APP_NOTIFICATION_SETTINGS)
                        .putExtra(Settings.EXTRA_APP_PACKAGE, context.packageName).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
                }) { Text("系统通知设置") }
            }
            if (message.isNotBlank()) Text(message)
        }
    }
}
