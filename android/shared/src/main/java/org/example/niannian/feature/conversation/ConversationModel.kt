package org.example.niannian.feature.conversation

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.delay
import org.json.JSONObject
import java.time.Instant
import java.util.UUID

interface ConversationSocket {
    fun send(text: String): Boolean
    fun close()
}

interface ConversationGateway {
    suspend fun create(family: String): String
    suspend fun status(id: String): String
    suspend fun end(id: String)
    suspend fun connect(id: String, message: (String) -> Unit, closed: (Int) -> Unit): ConversationSocket
}

data class ChatMessage(val fromUser: Boolean, val text: String)

data class ConversationState(val family: String = "", val user: String = "", val id: String = "",
    val state: String = "IDLE", val connected: Boolean = false, val busy: Boolean = false,
    val reply: String = "", val message: String = "", val slow: Boolean = false, val recapId: String = "",
    val llmMode: String = "", val messages: List<ChatMessage> = emptyList(), val retryText: String = "",
    val recording: Boolean = false, val recognizing: Boolean = false, val speaking: Boolean = false,
    val voiceEnabled: Boolean = false, val partialTranscript: String = "", val slowSpeech: Boolean = false,
    val voiceAllowed: Boolean = false)

class ConversationModel(private val gateway: ConversationGateway, private val scope: CoroutineScope? = null) : ViewModel() {
    private val current = MutableStateFlow(ConversationState())
    val state = current.asStateFlow()
    private var generation = 0
    private var clientSequence = 0L
    private var serverSequence = 0L
    private var awaitingHandshake = true
    private var socket: ConversationSocket? = null
    private var job: Job? = null
    private var deadline: Job? = null
    private var voiceDeadline: Job? = null
    private var voice: ConversationVoice? = null
    private var voiceGeneration = 0
    private var replyFloor = 0L
    private var interrupted = false
    private val earlyFrames = mutableListOf<String>()
    private val tasks get() = scope ?: viewModelScope

    fun attachVoice(device: ConversationVoice) { voice?.close(); voice = device }
    fun detachVoice(device: ConversationVoice) {
        if (voice === device) { stopVoice(); voice = null }
        device.close()
    }

    private fun stopVoice() {
        voiceGeneration++
        voiceDeadline?.cancel()
        voice?.stop()
        current.value = current.value.copy(recording = false, recognizing = false, speaking = false, partialTranscript = "")
    }

    fun clear() {
        generation++
        stopVoice()
        job?.cancel()
        deadline?.cancel()
        socket?.close()
        socket = null
        clientSequence = 0
        serverSequence = 0
        replyFloor = 0
        interrupted = false
        earlyFrames.clear()
        current.value = ConversationState()
    }

    fun bind(family: String, user: String) {
        if (current.value.family == family && current.value.user == user) return
        clear()
        current.value = ConversationState(family = family, user = user)
    }

    fun start() {
        if (current.value.busy || current.value.connected || current.value.family.isEmpty()) return
        val stamp = ++generation
        current.value = current.value.copy(busy = true, reply = "", message = "正在连接…")
        job = tasks.launch {
            try {
                val id = if (current.value.id.isEmpty()) gateway.create(current.value.family) else current.value.id
                if (stamp != generation) return@launch
                current.value = current.value.copy(id = id)
                val status = gateway.status(id)
                if (stamp != generation) return@launch
                if (status != "ACTIVE") {
                    current.value = current.value.copy(id = "", busy = false, message = "本次会话已结束，请开始新会话。")
                    clientSequence = 0
                    serverSequence = 0
                    return@launch
                }
                awaitingHandshake = true
                val connected = gateway.connect(id,
                    { raw -> tasks.launch { if (stamp == generation) {
                        if (socket == null && earlyFrames.size < 4) earlyFrames.add(raw) else receive(raw)
                    } } },
                    { code -> tasks.launch { if (stamp == generation) disconnected(code) } })
                if (stamp == generation) {
                    socket = connected
                    val queued = earlyFrames.toList()
                    earlyFrames.clear()
                    queued.forEach { if (stamp == generation) receive(it) }
                    if (awaitingHandshake) deadline = tasks.launch {
                        delay(10000)
                        if (stamp == generation && awaitingHandshake) disconnected(0)
                    }
                } else connected.close()
            } catch (cancelled: CancellationException) { throw cancelled }
            catch (_: Exception) { if (stamp == generation) disconnected(0) }
        }
    }

    private fun disconnected(code: Int) {
        generation++
        stopVoice()
        deadline?.cancel()
        earlyFrames.clear()
        socket?.close()
        socket = null
        current.value = current.value.copy(connected = false, busy = false, reply = "", messages = emptyList(),
            retryText = "", llmMode = "", voiceAllowed = false, voiceEnabled = false,
            state = if (code in listOf(4401, 4403)) "ERROR" else "OFFLINE",
            message = if (code in listOf(4401, 4403)) "无法访问此会话，请检查登录和家庭资格。"
                else "连接已断开。本次输入不会自动重发，请重新连接。")
    }

    internal fun receive(raw: String) {
        try {
            require(raw.toByteArray(Charsets.UTF_8).size <= 16384)
            val event = JSONObject(raw)
            require(event.getString("conversation_id") == current.value.id)
            val sequence = event.getLong("sequence")
            val type = event.getString("type")
            require(sequence > serverSequence)
            if (awaitingHandshake) require(type == "session.ready") else require(sequence == serverSequence + 1)
            serverSequence = sequence
            val payload = event.getJSONObject("payload")
            if (type != "session.ready" && type != "pong" && type != "voice.permission") {
                if (event.has("in_reply_to")) {
                    val request = event.getLong("in_reply_to")
                    require(request in 1..clientSequence)
                    if (request < replyFloor) return
                } else if (interrupted) return
            }
            when (type) {
                "session.ready" -> {
                    val mode = payload.optString("llm_mode", "mock")
                    require(mode in listOf("mock", "real"))
                    current.value = current.value.copy(llmMode = mode)
                    if (payload.has("voice_allowed")) {
                        require(payload.get("voice_allowed") is Boolean)
                        updateVoicePermission(payload.getBoolean("voice_allowed"))
                    }
                    if (awaitingHandshake) {
                        deadline?.cancel()
                        current.value = current.value.copy(connected = true, busy = false, state = "LISTENING",
                            messages = emptyList(), message = "连接内的聊天记录仅临时显示；重新连接后请重新说明话题。")
                        awaitingHandshake = false
                        send("session.start", JSONObject().put("client_session_id", UUID.randomUUID().toString()).put("input_mode", "TEXT"))
                    }
                }
                "voice.permission" -> {
                    require(payload.get("allowed") is Boolean)
                    updateVoicePermission(payload.getBoolean("allowed"))
                }
                "assistant.state" -> {
                    val value = payload.getString("state")
                    require(value in listOf("IDLE", "LISTENING", "THINKING", "SPEAKING", "WARNING", "OFFLINE", "ERROR"))
                    current.value = current.value.copy(state = when {
                        current.value.recording -> "LISTENING"
                        current.value.recognizing -> "THINKING"
                        current.value.speaking && current.value.state == "SPEAKING" -> "SPEAKING"
                        else -> value
                    }, busy = value == "THINKING")
                    if (value != "THINKING") deadline?.cancel()
                }
                "assistant.text" -> {
                    val text = payload.getString("text")
                    require(text.length <= 2000)
                    current.value = current.value.copy(reply = text,
                        messages = (current.value.messages + ChatMessage(false, text)).takeLast(20))
                    if (current.value.voiceEnabled && !interrupted && !current.value.recording && !current.value.recognizing
                        && event.has("in_reply_to") && event.getLong("in_reply_to") == replyFloor) speak(text)
                }
                "warning" -> {
                    val category = payload.getString("reason_category")
                    val text = payload.getString("display_text")
                    require(category.isNotBlank() && category.length <= 64)
                    require(text.isNotBlank() && text.length <= 2000)
                    current.value = current.value.copy(state = "WARNING", message = text)
                }
                "signal.created" -> {
                    UUID.fromString(payload.getString("signal_event_id"))
                    require(payload.getString("type") in listOf("PHYSICAL_DISCOMFORT", "EMOTION_EXPRESSION",
                        "IMPORTANT_MEMORY", "MISS_FAMILY", "SCAM_RISK", "EMERGENCY"))
                    require(payload.getString("severity") in listOf("L0", "L1", "L2", "L3", "L4"))
                }
                "error" -> {
                    deadline?.cancel()
                    current.value = current.value.copy(busy = false,
                        message = "暂时无法完成，请稍后重新发送。")
                }
                "pong" -> Unit
                else -> error("Unsupported event")
            }
        } catch (_: Exception) {
            disconnected(0)
        }
    }

    private fun send(type: String, payload: JSONObject = JSONObject()): Boolean {
        if (!current.value.connected) return false
        val frame = JSONObject().put("type", type).put("conversation_id", current.value.id)
            .put("sequence", ++clientSequence).put("occurred_at", Instant.now().toString()).put("payload", payload)
        if (socket?.send(frame.toString()) != true) { disconnected(0); return false }
        return true
    }

    fun input(text: String): Boolean {
        if (!current.value.connected || current.value.busy || current.value.recording || current.value.recognizing
            || text.isBlank() || text.length > 2000) return false
        stopVoice()
        if (!send("text.input", JSONObject().put("text", text))) return false
        replyFloor = clientSequence
        interrupted = false
        current.value = current.value.copy(busy = true, state = "THINKING", reply = "", message = "",
            retryText = text, messages = (current.value.messages + ChatMessage(true, text)).takeLast(20))
        val stamp = generation
        deadline?.cancel()
        deadline = tasks.launch { delay(25000); if (stamp == generation && current.value.busy) disconnected(0) }
        return true
    }

    fun interrupt() {
        stopVoice()
        deadline?.cancel()
        interrupted = true
        if (send("interrupt")) {
            replyFloor = clientSequence
            current.value = current.value.copy(reply = "", busy = false, state = "IDLE", message = "已停止。可以重新说话或打字。")
        }
    }
    fun repeat() {
        if (!current.value.busy && !current.value.recording && !current.value.recognizing) {
            stopVoice()
            if (send("repeat")) { replyFloor = clientSequence; interrupted = false }
        }
    }
    fun slowDown() {
        if (!current.value.busy) {
            current.value = current.value.copy(slow = !current.value.slow)
        }
    }
    fun voiceEntry() {
        if (!current.value.connected) return
        if (!current.value.voiceAllowed) return voicePermissionDenied("请先在“家庭与授权设置 → 用于我与念念的交流”中允许语音处理，或继续打字。")
        val device = voice ?: return voicePermissionDenied("设备语音服务未就绪，您可以继续打字。")
        interrupt()
        if (!current.value.connected) return
        val stamp = voiceGeneration
        current.value = current.value.copy(recording = true, state = "LISTENING", voiceEnabled = true,
            message = "请说话，说完可点“说完了”。")
        voiceDeadline = tasks.launch {
            delay(30000)
            if (stamp == voiceGeneration && current.value.recording) finishListening()
        }
        device.listen(
            partial = { text -> if (stamp == voiceGeneration && current.value.recording) {
                current.value = current.value.copy(partialTranscript = text.take(2000))
            } },
            final = { text -> if (stamp == voiceGeneration) {
                stopVoice()
                if (text.isBlank() || text.length > 2000) {
                    current.value = current.value.copy(state = "IDLE", message = "没有听清或内容过长，请再说一次或打字。")
                } else input(text)
            } },
            failed = { message -> if (stamp == voiceGeneration) voiceFailure(message) })
    }

    fun finishListening() {
        if (!current.value.recording) return
        val stamp = voiceGeneration
        current.value = current.value.copy(recording = false, recognizing = true, state = "THINKING", message = "正在识别…")
        voiceDeadline?.cancel()
        voiceDeadline = tasks.launch {
            delay(10000)
            if (stamp == voiceGeneration) voiceFailure("识别等待超时，请重试或继续打字。")
        }
        voice?.finishListening()
    }

    fun voicePermissionDenied(message: String = "未开启麦克风权限，您仍可使用文字聊天。") {
        current.value = current.value.copy(message = message)
    }

    private fun voiceFailure(message: String) {
        stopVoice()
        current.value = current.value.copy(state = "IDLE", message = message)
    }

    private fun speak(text: String) {
        if (!current.value.voiceAllowed) return
        val device = voice ?: return
        stopVoice()
        val stamp = voiceGeneration
        current.value = current.value.copy(speaking = true)
        voiceDeadline = tasks.launch {
            delay(10000)
            if (stamp == voiceGeneration) voiceFailure("朗读启动超时，请查看文字或稍后重试。")
        }
        device.speak(text, current.value.slowSpeech,
            started = { if (stamp == voiceGeneration) {
                current.value = current.value.copy(state = "SPEAKING")
                voiceDeadline?.cancel()
                voiceDeadline = tasks.launch {
                    delay(180000)
                    if (stamp == voiceGeneration) voiceFailure("朗读已停止，您可以继续聊天。")
                }
            } },
            finished = { if (stamp == voiceGeneration) { stopVoice(); current.value = current.value.copy(state = "IDLE") } },
            failed = { message -> if (stamp == voiceGeneration) voiceFailure(message) })
    }

    fun toggleSpeech() {
        if (!current.value.voiceAllowed) return voicePermissionDenied("请先允许语音处理，或继续查看文字。")
        stopVoice()
        current.value = current.value.copy(voiceEnabled = !current.value.voiceEnabled, state = if (current.value.busy) "THINKING" else "IDLE")
    }

    fun toggleSpeechRate() {
        current.value = current.value.copy(slowSpeech = !current.value.slowSpeech)
        if (current.value.speaking) repeat()
    }

    private fun updateVoicePermission(allowed: Boolean) {
        val wasAllowed = current.value.voiceAllowed
        current.value = current.value.copy(voiceAllowed = allowed)
        if (!allowed) {
            val active = current.value.recording || current.value.recognizing || current.value.speaking
            stopVoice()
            current.value = current.value.copy(voiceEnabled = false,
                state = if (current.value.busy) "THINKING" else if (active) "IDLE" else current.value.state,
                message = if (wasAllowed) "语音处理授权已撤回或到期，已停止语音；可以继续打字。" else current.value.message)
        }
    }
    suspend fun awaitIdle() { job?.join() }

    fun end() {
        val id = current.value.id
        val family = current.value.family
        val user = current.value.user
        val priorClientSequence = clientSequence
        val priorServerSequence = serverSequence
        clear()
        current.value = ConversationState(family = family, user = user, busy = true)
        val stamp = generation
        job = tasks.launch {
            try {
                if (id.isNotEmpty()) gateway.end(id)
                if (stamp == generation) current.value = current.value.copy(busy = false, recapId = id,
                    message = "本次会话已结束。编号：$id。已允许生成回顾时，可在下方请求或查看本次摘要；不会展示逐字稿。")
            } catch (cancelled: CancellationException) { throw cancelled }
            catch (_: Exception) {
                if (stamp == generation) {
                    clientSequence = priorClientSequence
                    serverSequence = priorServerSequence
                    current.value = current.value.copy(id = id, busy = false, state = "OFFLINE",
                        message = "结束结果未确认，请重试结束；不会自动重发对话。")
                }
            }
        }
    }
    override fun onCleared() { clear(); voice?.close(); voice = null; super.onCleared() }
}
