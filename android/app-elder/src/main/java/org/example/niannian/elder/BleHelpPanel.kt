package org.example.niannian.elder

import android.os.Build
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.SideEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.sp
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.compose.LocalLifecycleOwner
import kotlinx.coroutines.CancellationException
import org.example.niannian.data.ApiFailure
import org.example.niannian.data.FamilyRepository

private const val SENDING = "已收到实体按钮按键，正在向当前家庭提交求助。"
private const val TRY_PHONE = "需要立即帮助时，请联系身边的人或使用系统电话。"

@Composable
internal fun BleHelpSettings(button: BleHelpButton, canBind: Boolean) {
    val state by button.state.collectAsState()
    val permission = rememberLauncherForActivityResult(ActivityResultContracts.RequestMultiplePermissions()) {
        if (button.availablePermissions()) {
            if (button.state.value.bound) button.reconnectNow() else button.scan()
        } else button.reconnectNow()
    }
    Text("蓝牙求助按钮", fontSize = 22.sp)
    if (!canBind) {
        Text("登录并选择已加入的家庭后可绑定实体按钮。", fontSize = 18.sp)
        return
    }
    if (state.message.isNotBlank()) Text(state.message, fontSize = 18.sp)
    if (Build.VERSION.SDK_INT < 31) return
    if (state.bound) {
        DeviceButton("连接或恢复附近设备权限") {
            if (button.availablePermissions()) button.reconnectNow() else permission.launch(blePermissions)
        }
        DeviceButton("解除本应用的按钮绑定") { button.clearBinding() }
    } else if (!state.pairing) {
        Text("让 ESP32-C3 按钮进入配对模式。选择地址尾号与串口一致的设备，并在系统提示中输入串口配对码。", fontSize = 17.sp)
        state.candidates.forEach { address ->
            DeviceButton("绑定按钮 · " + address.takeLast(5)) { button.select(address) }
        }
        if (!state.scanning) DeviceButton("搜索念念按钮") {
            if (button.availablePermissions()) button.scan() else permission.launch(blePermissions)
        }
    }
}

private data class PhysicalHelp(val id: String, val sending: Boolean = true, val retry: Boolean = false,
    val message: String = SENDING)

@Composable
internal fun BleHelpHost(button: BleHelpButton, target: HelpButtonTarget?, repository: FamilyRepository) {
    val lifecycle = LocalLifecycleOwner.current.lifecycle
    var request by remember(target) { mutableStateOf<PhysicalHelp?>(null) }
    SideEffect { button.activate(target) }
    DisposableEffect(button, lifecycle) {
        val observer = LifecycleEventObserver { _, event ->
            if (event == Lifecycle.Event.ON_START) button.setVisible(true)
            if (event == Lifecycle.Event.ON_STOP) button.setVisible(false)
        }
        lifecycle.addObserver(observer)
        onDispose {
            lifecycle.removeObserver(observer)
            button.setVisible(false)
            button.activate(null)
        }
    }
    LaunchedEffect(button, target) {
        if (target != null) button.presses.collect { id ->
            if (request?.sending != true) request = PhysicalHelp(id)
        }
    }
    val pending = request
    LaunchedEffect(target, pending?.id, pending?.sending) {
        if (target == null || pending?.sending != true) return@LaunchedEffect
        try {
            val result = repository.requestBleHelp(target.family, target.user, pending.id)
            request = pending.copy(sending = false, message = result.getString("help_message"))
        } catch (cancelled: CancellationException) {
            throw cancelled
        } catch (error: Exception) {
            val retry = error !is ApiFailure || error.status !in 400..499 || error.status in listOf(408, 429)
            request = pending.copy(sending = false, retry = retry, message = if (retry)
                "提交结果未确认，可在网络恢复后用同一按键编号重试。$TRY_PHONE"
            else "求助未提交，请核对登录和家庭资格。$TRY_PHONE")
        }
    }
    if (pending != null) {
        AlertDialog(onDismissRequest = { if (!pending.sending) request = null },
            title = { Text("实体按钮求助", fontSize = 24.sp) },
            text = { Text(pending.message, Modifier.verticalScroll(rememberScrollState()), fontSize = 20.sp) },
            confirmButton = {
                if (pending.retry) Button(onClick = { request = PhysicalHelp(pending.id) }) { Text("重试同一请求") }
                else Button(onClick = { request = null }, enabled = !pending.sending) { Text("知道了") }
            }, dismissButton = {
                if (pending.retry) TextButton(onClick = { request = null }) { Text("关闭") }
            })
    }
}
