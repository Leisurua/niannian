package org.example.niannian.feature.voice

import android.Manifest
import android.content.pm.PackageManager
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.compose.LocalLifecycleOwner
import kotlinx.coroutines.*
import org.example.niannian.feature.family.Member
import org.example.niannian.feature.conversation.ConversationModel

private val statuses = mapOf("UPLOADING" to "等待录音上传", "PENDING" to "等待本人授权", "QUEUED" to "等待制作",
    "GENERATING" to "正在制作", "READY" to "等待本人试听确认", "ACTIVE" to "已启用", "FAILED" to "制作失败",
    "REVOKED" to "已撤回", "DELETED" to "已删除")

@Composable
fun FamilyVoicesPanel(model: VoiceProfilesModel, family: String, user: String, members: List<Member>) {
    val state by model.state.collectAsState()
    val context = LocalContext.current
    val lifecycle = LocalLifecycleOwner.current
    val scope = rememberCoroutineScope()
    val recorder = remember(context) { VoiceRecorder(context.applicationContext) }
    val player = remember { PcmPlayer() }
    var recording by remember { mutableStateOf(false) }
    var bytes by remember { mutableStateOf<ByteArray?>(null) }
    var owner by remember(family, user) { mutableStateOf(user) }
    var name by remember(family, user) { mutableStateOf("") }
    var message by remember { mutableStateOf("") }
    var confirmation by remember { mutableStateOf<Pair<FamilyVoice, String>?>(null) }
    var audioTask by remember { mutableStateOf<Job?>(null) }
    fun startRecording() {
        runCatching { player.stop(); bytes = null; recorder.start(); recording = true; message = "请自然朗读约15–20秒，最长60秒。" }
            .onFailure { message = "麦克风不可用，请检查权限或重试。" }
    }
    val permission = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
        if (granted && lifecycle.lifecycle.currentState.isAtLeast(Lifecycle.State.STARTED)) startRecording()
        else message = "未允许麦克风，不能录入声音。"
    }
    fun preview(load: suspend () -> ByteArray) {
        audioTask?.cancel(); player.stop()
        audioTask = scope.launch {
            try {
                val pcm = VoiceRecorder.pcm(load())
                player.start({}, { message = "试听结束。" }, { message = it })
                withContext(Dispatchers.IO) {
                    var offset = 0
                    while (offset < pcm.size) {
                        ensureActive()
                        val end = minOf(offset + 8192, pcm.size)
                        check(player.offerPreview(pcm.copyOfRange(offset, end)))
                        offset = end
                    }
                    player.finish()
                }
            } catch (cancelled: CancellationException) { throw cancelled }
            catch (_: Exception) { player.stop(); message = "试听不可用，请刷新声音状态。" }
        }
    }
    LaunchedEffect(family, user) { model.bind(family, user, false) }
    LaunchedEffect(recording) { if (recording) { delay(60000); if (recording) {
        recording = false
        runCatching { withContext(Dispatchers.IO) { recorder.finish() } }.onSuccess { bytes = it }.onFailure { message = "录音未完成，请重录。" }
    } } }
    DisposableEffect(lifecycle, family, user) {
        val observer = LifecycleEventObserver { _, event -> if (event == Lifecycle.Event.ON_STOP) {
            recorder.cancel(); recording = false; bytes = null; player.stop(); audioTask?.cancel(); confirmation = null
        } }
        lifecycle.lifecycle.addObserver(observer)
        onDispose { lifecycle.lifecycle.removeObserver(observer); recorder.cancel(); player.stop(); audioTask?.cancel(); bytes = null }
    }
    confirmation?.let { (row, action) ->
        AlertDialog(onDismissRequest = { confirmation = null }, title = { Text(when(action) {
            "approve" -> "本人授权声音制作"; "activate" -> "确认试听效果并发布"; else -> "撤回并删除声音"
        }) }, text = { Text(when(action) {
            "approve" -> "请确认录音确实是您本人，并已试听。允许将这段录音发送至阿里云百炼制作音色，供本家庭当前及以后加入的老人使用。念念仍是AI，不代表您本人。成功后删除念念侧原录音；供应商可能留存调用数据，可随时撤回。"
            "activate" -> "请确认已经试听，声音清楚且能体现您的音色。发布后替换您的旧音色，供本家庭老人选择。"
            else -> "立即停止使用该声音，并清理录音、试听与供应商音色。供应商副本的删除进度以服务记录为准。"
        }) }, confirmButton = { Button(onClick = { model.command(row, action); confirmation = null }) { Text("本人确认") } },
            dismissButton = { TextButton(onClick = { confirmation = null }) { Text("取消") } })
    }
    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
        Text("家人声音", fontSize = 24.sp)
        Text("允许协助家人录音，声音本人必须登录授权并试听确认。只录本人单独说话，不含背景音乐；请勿朗读隐私信息。")
        Text("朗读参考：你好，我是你的家人。今天过得怎么样？记得按时吃饭，也要喝些温水。有空的时候，我们一起聊聊最近的生活。")
        members.filter { it.status == "ACTIVE" }.forEach { member ->
            TextButton(enabled = !recording && !state.busy, onClick = { owner = member.userId; name = member.name }) {
                Text((if (owner == member.userId) "✓ " else "") + member.name + if (member.userId == user) "（本人）" else "（协助录入）")
            }
        }
        OutlinedTextField(name, { name = it.take(50) }, label = { Text("音色显示名称") }, enabled = !state.busy && !recording)
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Button(enabled = !state.busy, onClick = {
                if (recording) {
                    recording = false
                    scope.launch { runCatching { withContext(Dispatchers.IO) { recorder.finish() } }
                        .onSuccess { bytes = it; message = "录音已暂存本机内存，请试听后上传。" }
                        .onFailure { message = "请至少录制10秒清晰语音。" } }
                } else if (context.checkSelfPermission(Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED) startRecording()
                else permission.launch(Manifest.permission.RECORD_AUDIO)
            }) { Text(if (recording) "录完了" else "开始／重新录音") }
            TextButton(onClick = { audioTask?.cancel(); player.stop() }) { Text("停止试听") }
        }
        bytes?.let { sample ->
            Button(enabled = !recording, onClick = { preview { sample } }) { Text("试听刚录的声音") }
            Button(enabled = !state.busy && !recording && name.isNotBlank(), onClick = {
                model.upload(owner, name, sample); bytes = null; player.stop()
            }) { Text("私密上传，等待声音本人确认") }
        }
        Button(enabled = !state.busy, onClick = { model.refresh(false) }) { Text(if (state.busy) "正在处理…" else "刷新制作状态") }
        if (message.isNotBlank()) Text(message)
        if (state.message.isNotBlank()) Text(state.message)
        state.voices.forEach { row ->
            Card(Modifier.fillMaxWidth()) { Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                Text(row.name + " · " + (statuses[row.status] ?: row.status))
                if (row.status == "PENDING") Button(onClick = { preview { model.audio(row, true) } }) { Text("试听原录音") }
                if (row.status in listOf("READY", "ACTIVE")) Button(onClick = { preview { model.audio(row, false) } }) { Text("试听合成声音") }
                if (row.owner == user) {
                    if (row.status == "PENDING") Button(enabled = !state.busy, onClick = { confirmation = row to "approve" }) { Text("本人授权云端制作") }
                    if (row.status == "READY") Button(enabled = !state.busy, onClick = { confirmation = row to "activate" }) { Text("满意，允许家人使用") }
                    if (row.status !in listOf("DELETED", "REVOKED")) TextButton(enabled = !state.busy, onClick = { confirmation = row to "delete" }) { Text("撤回／删除") }
                }
            } }
        }
    }
}

@Composable
fun VoicePicker(model: VoiceProfilesModel, conversation: ConversationModel, family: String, user: String) {
    val state by model.state.collectAsState()
    val chat by conversation.state.collectAsState()
    var approval by remember { mutableStateOf<FamilyVoice?>(null) }
    val scope = rememberCoroutineScope()
    val player = remember { PcmPlayer() }
    var previewJob by remember { mutableStateOf<Job?>(null) }
    var message by remember { mutableStateOf("") }
    var expanded by remember { mutableStateOf(false) }
    LaunchedEffect(family, user) { model.bind(family, user, true) }
    LaunchedEffect(state.selected, state.voices) {
        if (state.family == family && state.user == user && !state.busy) {
            val chosen = state.voices.firstOrNull { it.id == state.selected }
            if (chat.voiceProfileId != chosen?.id) conversation.selectVoice(chosen?.id, chosen?.name ?: "念念普通声音")
        }
    }
    DisposableEffect(family, user) { onDispose { previewJob?.cancel(); player.stop() } }
    approval?.let { row -> AlertDialog(onDismissRequest = { approval = null }, title = { Text("允许云端朗读") },
        text = { Text("念念将把需要朗读的回复文本发送给阿里云百炼，使用${row.name}授权的音色合成。供应商可能留存调用数据，您可以随时关闭。念念仍是AI，不是真实家人。") },
        confirmButton = { Button(onClick = { model.select(row.id, true) { conversation.selectVoice(row.id, row.name) }; approval = null }) { Text("允许并使用") } },
        dismissButton = { TextButton(onClick = { approval = null }) { Text("使用普通声音") } }) }
    Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
        Text("当前声音：${chat.voiceName} · AI合成", fontSize = 20.sp)
        TextButton(onClick = { expanded = !expanded; if (expanded) model.refresh(true) }) { Text(if (expanded) "收起声音选择" else "选择／试听家人声音") }
        if (expanded) {
            Button(enabled = !state.busy, onClick = { previewJob?.cancel(); player.stop(); model.select(null, state.cloudAllowed) { conversation.selectVoice(null, "念念普通声音") } }) { Text("念念普通声音") }
            state.voices.filter { it.status == "ACTIVE" }.forEach { row ->
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Button(enabled = !state.busy, onClick = {
                        previewJob?.cancel(); player.stop()
                        if (state.cloudAllowed) model.select(row.id, true) { conversation.selectVoice(row.id, row.name) } else approval = row
                    }) { Text(row.name) }
                    TextButton(onClick = {
                        previewJob?.cancel(); player.stop()
                        if (chat.connected) conversation.interrupt()
                        previewJob = scope.launch {
                            try {
                                val pcm = VoiceRecorder.pcm(model.audio(row, false))
                                player.start({}, {}, { message = it })
                                withContext(Dispatchers.IO) {
                                    var offset = 0
                                    while (offset < pcm.size) {
                                        ensureActive(); val end = minOf(offset + 8192, pcm.size)
                                        check(player.offerPreview(pcm.copyOfRange(offset, end))); offset = end
                                    }
                                    player.finish()
                                }
                            } catch (e: CancellationException) { throw e }
                            catch (_: Exception) { player.stop(); message = "试听不可用，请刷新声音列表。" }
                        }
                    }) { Text("试听") }
                }
            }
            TextButton(onClick = { previewJob?.cancel(); player.stop() }) { Text("停止试听") }
            if (state.cloudAllowed) TextButton(enabled = !state.busy, onClick = {
                previewJob?.cancel(); player.stop(); model.select(null, false) { conversation.selectVoice(null, "念念普通声音") }
            }) { Text("撤回云端朗读授权") }
            if (state.message.isNotBlank()) Text(state.message)
            if (message.isNotBlank()) Text(message)
            if (state.voices.isEmpty()) Text("暂无已获本人授权并发布的家人音色。")
        }
    }
}
