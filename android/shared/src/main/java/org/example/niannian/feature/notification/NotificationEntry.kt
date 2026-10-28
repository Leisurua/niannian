package org.example.niannian.feature.notification

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.compose.LocalLifecycleOwner
import kotlinx.coroutines.CancellationException
import org.example.niannian.data.FamilyRepository
import org.example.niannian.data.notificationGateway
import java.util.UUID

private data class NotificationRoute(val family: String, val owner: String)

@Composable
fun NotificationEntry(repository: FamilyRepository, launch: NotificationLaunch?, user: String,
    loggedIn: Boolean, onClose: () -> Unit) {
    val lifecycle = LocalLifecycleOwner.current.lifecycle
    var foreground by remember { mutableStateOf(lifecycle.currentState.isAtLeast(Lifecycle.State.STARTED)) }
    var route by remember(launch, user) { mutableStateOf<NotificationRoute?>(null) }
    var error by remember(launch, user) { mutableStateOf("") }
    val scope = rememberCoroutineScope()
    val model = remember(launch, user) { NotificationModel(repository.notificationGateway(), scope) }
    DisposableEffect(lifecycle, model) {
        val observer = LifecycleEventObserver { _, event ->
            if (event == Lifecycle.Event.ON_STOP) { foreground = false; route = null; model.clear() }
            if (event == Lifecycle.Event.ON_START) foreground = true
        }
        lifecycle.addObserver(observer)
        onDispose { lifecycle.removeObserver(observer); model.clear() }
    }
    LaunchedEffect(launch, user, loggedIn, foreground) {
        route = null; error = ""
        if (launch == null || !loggedIn || user.isBlank() || !foreground) return@LaunchedEffect
        if (launch.recipient != user) { error = "此通知属于其他账号，请切换到接收通知的账号后再打开。"; return@LaunchedEffect }
        try {
            require(UUID.fromString(launch.id).toString() == launch.id)
            val value = repository.call("/v1/notifications/${launch.id}")
            if (repository.savedUserId() != user) return@LaunchedEffect
            route = NotificationRoute(value.getString("family_id"), value.getString("owner_user_id"))
        } catch (cancelled: CancellationException) { throw cancelled }
        catch (_: Exception) { error = "暂时无法打开。请检查网络、登录和当前授权；通知也可能已到期或被撤回。" }
    }
    if (launch == null || !loggedIn || user.isBlank() || !foreground) return
    Dialog(onDismissRequest = onClose, properties = DialogProperties(usePlatformDefaultWidth = false)) {
        Surface(Modifier.fillMaxWidth().fillMaxHeight(0.9f).padding(12.dp)) {
            Column(Modifier.padding(12.dp).verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                TextButton(onClick = onClose) { Text("返回首页") }
                if (error.isNotBlank()) Text(error)
                else route?.let {
                    NotificationPanel(model, it.family, user, listOf(it.owner to "通知对应的长辈"),
                        false, user, initialNotificationId = launch.id)
                } ?: Text("正在核验通知和当前授权…")
            }
        }
    }
}

@Composable
fun ElderSignalProgress(model: NotificationModel?, onOpen: () -> Unit) {
    if (model == null) return
    val state by model.state.collectAsState()
    Card(Modifier.fillMaxWidth().padding(top = 12.dp)) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text("家人的处理进度", style = MaterialTheme.typography.titleLarge)
            state.items.take(3).forEach { Text(signalStatusLabel(it.eventStatus), style = MaterialTheme.typography.bodyLarge) }
            if (!state.loaded || state.busy) Text("正在核对处理进度，请保持网络连接。")
            else if (state.items.isEmpty()) Text("当前没有关注提示。")
            Button(onClick = onOpen, modifier = Modifier.heightIn(min = 56.dp)) { Text("查看家人的处理记录") }
        }
    }
}
