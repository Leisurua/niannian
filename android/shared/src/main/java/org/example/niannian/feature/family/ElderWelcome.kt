package org.example.niannian.feature.family

import android.content.Context
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.compose.LocalLifecycleOwner
import kotlinx.coroutines.delay
import org.example.niannian.feature.conversation.AndroidConversationVoice

private const val IDENTITY = "您好，我是念念，是一个 AI 陪伴助手，不是真实家人。"
private const val ABILITIES = "我可以陪您聊天、查看提醒，也可以帮您向家人发送求助。请勿在聊天中提供密码或验证码。"
private const val PRIVACY = "语音、家庭记忆、交流摘要、互动统计和分享给家人等功能需要分别授权。您可以随时在家庭与授权设置查看或撤回。不开启这些功能也可以打字聊天。"

@Composable
internal fun ElderWelcome(openSettings: () -> Unit) {
    val context = LocalContext.current
    val preferences = remember(context) { context.getSharedPreferences("elder-welcome", Context.MODE_PRIVATE) }
    var seen by remember(preferences) { mutableStateOf(preferences.getBoolean("seen", false)) }
    if (seen) return

    val voice = remember(context) { AndroidConversationVoice(context) }
    val lifecycle = LocalLifecycleOwner.current.lifecycle
    var reading by remember { mutableStateOf(false) }
    var unavailable by remember { mutableStateOf(false) }
    LaunchedEffect(reading) {
        if (reading) {
            delay(60_000)
            voice.stop()
            reading = false
            unavailable = true
        }
    }
    DisposableEffect(lifecycle, voice) {
        val observer = LifecycleEventObserver { _, event ->
            if (event == Lifecycle.Event.ON_PAUSE) {
                voice.stop()
                reading = false
            }
        }
        lifecycle.addObserver(observer)
        onDispose {
            lifecycle.removeObserver(observer)
            voice.close()
        }
    }
    fun acknowledge() {
        preferences.edit().putBoolean("seen", true).apply()
        seen = true
    }
    AlertDialog(onDismissRequest = {}, title = { Text("认识念念", fontSize = 26.sp) },
        text = {
            Column(Modifier.verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                Text(IDENTITY, fontSize = 20.sp)
                Text(ABILITIES, fontSize = 18.sp)
                Text(PRIVACY, fontSize = 18.sp)
                TextButton(enabled = !reading, onClick = {
                    reading = true
                    unavailable = false
                    voice.speak("$IDENTITY $ABILITIES $PRIVACY", slow = true, started = {},
                        finished = { reading = false }, failed = { reading = false; unavailable = true })
                }) { Text(if (reading) "正在朗读" else "朗读说明", fontSize = 18.sp) }
                if (unavailable) Text("设备朗读暂不可用，请查看文字说明。", fontSize = 18.sp)
            }
        },
        confirmButton = { Button(onClick = ::acknowledge) { Text("我知道了", fontSize = 18.sp) } },
        dismissButton = { TextButton(onClick = { acknowledge(); openSettings() }) { Text("查看授权设置", fontSize = 18.sp) } })
}
