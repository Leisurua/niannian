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
import org.json.JSONArray
import java.util.Base64
import org.example.niannian.core.common.parseApiInstant
import java.time.Instant
import java.time.ZoneId
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

data class ChatMessage(val fromUser: Boolean, val text: String, val sourceLabels: List<String> = emptyList())

data class ConversationState(val family: String = "", val user: String = "", val id: String = "",
    val state: String = "IDLE", val connected: Boolean = false, val busy: Boolean = false,
    val reply: String = "", val message: String = "", val slow: Boolean = false, val recapId: String = "",
    val llmMode: String = "", val messages: List<ChatMessage> = emptyList(), val retryText: String = "",
    val recording: Boolean = false, val recognizing: Boolean = false, val speaking: Boolean = false,
    val voiceEnabled: Boolean = false, val partialTranscript: String = "", val slowSpeech: Boolean = false,
    val voiceName: String = "念念普通声音", val voiceProfileId: String? = null,
    val proactiveInvitationId: String = "", val proactiveInvitationText: String = "",
    val voiceAllowed: Boolean = false, val speechPending: Boolean = false, val reminderRevision: Long = 0,
    val voiceRecovery: VoiceRecovery? = null, val canStopByVoice: Boolean = false) {
    val companionPhase: CompanionPhase get() = when {
        !connected -> CompanionPhase.IDLE
        recording -> CompanionPhase.LISTENING
        speaking -> CompanionPhase.SPEAKING
        recognizing || busy || speechPending -> CompanionPhase.THINKING
        else -> CompanionPhase.IDLE
    }
    val voiceActive: Boolean get() = recording || recognizing || speaking || speechPending
}

enum class VoiceRecovery { CONFIRM_IDENTITY, RETRY }

enum class CompanionPhase(val label: String) {
    IDLE("待机 · 念念在这里"), LISTENING("听您说话"), THINKING("思考中"), SPEAKING("正在朗读")
}

internal const val CONVERSATION_IDENTITY = "您好，我是念念 AI。"

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
    private var invitationDeadline: Job? = null
    private var voice: ConversationVoice? = null
    private var voiceSelectionPending = false
    private var cloudReply: Long? = null
    private var playbackId: String? = null
    private var voiceGeneration = 0
    private var replyFloor = 0L
    private var interrupted = false
    private val earlyFrames = mutableListOf<String>()
    private var weatherCityId: Int? = null
    private var introducedSessionId = ""
    private var handsFree = false
    private val tasks get() = scope ?: viewModelScope

    fun attachVoice(device: ConversationVoice) { stopVoice(); voice?.close(); voice = device }
    fun detachVoice(device: ConversationVoice) {
        if (voice === device) { stopVoice(); voice = null }
        device.close()
    }

    private fun stopVoice() {
        cloudReply = null
        playbackId = null
        voiceGeneration++
        voiceDeadline?.cancel()
        voice?.stop()
        current.value = current.value.copy(recording = false, recognizing = false, speaking = false,
            speechPending = false, partialTranscript = "", voiceRecovery = null, canStopByVoice = false)
    }

    fun clear() {
        handsFree = false
        clearInvitation()
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
        weatherCityId = null
        introducedSessionId = ""
        current.value = ConversationState()
    }

    fun bind(family: String, user: String) {
        if (current.value.family == family && current.value.user == user) return
        clear()
        current.value = ConversationState(family = family, user = user)
    }

    fun selectVoice(id: String?, name: String) {
        stopVoice()
        current.value = current.value.copy(voiceProfileId = id, voiceName = name)
        if (current.value.connected) voiceSelectionPending = send("voice.select", JSONObject().put("voice_profile_id", id ?: JSONObject.NULL))
    }

    fun setWeatherCity(id: Int?) { weatherCityId = id?.takeIf { it > 0 } }

    fun start() {
        voiceSelectionPending = false
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
        handsFree = false
        clearInvitation()
        generation++
        stopVoice()
        deadline?.cancel()
        earlyFrames.clear()
        socket?.close()
        socket = null
        val accessDenied = code in listOf(4401, 4403)
        current.value = current.value.copy(connected = false, busy = false, reply = "", messages = emptyList(),
            retryText = if (accessDenied) "" else current.value.retryText,
            llmMode = "", voiceAllowed = false, voiceEnabled = false,
            state = if (accessDenied) "ERROR" else "OFFLINE",
            message = if (accessDenied) "无法访问此会话，请检查登录和家庭资格。"
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
            val replyTo = if (event.has("in_reply_to")) event.getLong("in_reply_to") else null
            if (type !in listOf("session.ready", "pong", "voice.permission", "voice.selected", "tts.cancel")) {
                if (replyTo != null) {
                    require(replyTo in 1..clientSequence)
                    if (replyTo < replyFloor) return
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
                        send("session.start", JSONObject().put("client_session_id", UUID.randomUUID().toString()).put("input_mode", "TEXT")
                            .put("audio_capabilities", JSONArray().put("pcm_v1"))
                            .put("voice_profile_id", current.value.voiceProfileId ?: JSONObject.NULL))
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
                        current.value.speaking -> "SPEAKING"
                        else -> value
                    }, busy = value == "THINKING" || (value == "SPEAKING" && current.value.busy))
                    if (!current.value.busy) {
                        deadline?.cancel()
                        if (current.value.reply.isNotEmpty() && current.value.message.isEmpty()) {
                            current.value = current.value.copy(retryText = "")
                        }
                    }
                }
                "assistant.text" -> {
                    val text = payload.getString("text")
                    require(text.length <= 2000)
                    if (payload.has("proactive_invitation_id")) {
                        val id = payload.getString("proactive_invitation_id")
                        require(UUID.fromString(id).toString() == id)
                        val remaining = java.time.Duration.between(Instant.now(), parseApiInstant(payload.getString("expires_at"))).toMillis().coerceAtMost(300000)
                        if (remaining <= 0 || current.value.busy || current.value.voiceActive) return
                        clearInvitation()
                        current.value = current.value.copy(proactiveInvitationId = id, proactiveInvitationText = text)
                        invitationDeadline = tasks.launch {
                            delay(remaining)
                            if (current.value.proactiveInvitationId == id) clearInvitation()
                        }
                        return
                    }
                    val labels = payload.optJSONArray("source_labels")?.let { values ->
                        require(values.length() <= 5)
                        (0 until values.length()).map { values.getString(it).also { label -> require(label.length <= 60) } }
                    } ?: emptyList()
                    deadline?.cancel()
                    current.value = current.value.copy(reply = text, busy = false,
                        messages = (current.value.messages + ChatMessage(false, text, labels)).takeLast(20),
                        reminderRevision = current.value.reminderRevision + if (payload.optBoolean("reminders_changed", false)) 1 else 0)
                    if (current.value.voiceEnabled && current.value.voiceAllowed && !interrupted
                        && !current.value.recording && !current.value.recognizing && replyTo == replyFloor) {
                        when (payload.optString("speech_mode", "device")) {
                            "device" -> speak(text)
                            "cloud" -> if (!voiceSelectionPending && voice != null && current.value.voiceProfileId != null) {
                                cloudReply = replyTo
                                current.value = current.value.copy(speechPending = true)
                                val stamp = voiceGeneration
                                voiceDeadline = tasks.launch {
                                    delay(25000)
                                    if (stamp == voiceGeneration)
                                        voiceFailure("家人声音暂时无法播放。您可以看文字，或点“再说一遍”。")
                                }
                            }
                        }
                    }
                }
                "voice.selected" -> {
                    voiceSelectionPending = false
                    stopVoice()
                    current.value = current.value.copy(voiceProfileId = payload.optString("voice_profile_id").takeUnless { it.isBlank() || it == "null" },
                        voiceName = payload.optString("display_name", "念念普通声音"))
                }
                "tts.cancel" -> stopVoice()
                "tts.start" -> {
                    if (replyTo == null || replyTo != cloudReply || playbackId != null
                        || payload.optString("voice_profile_id") != current.value.voiceProfileId) return
                    require(payload.getInt("sample_rate") == 24000 && payload.getInt("channels") == 1)
                    playbackId = payload.getString("playback_id")
                    val stamp = voiceGeneration
                    voice?.startPcm(
                        { if (stamp == voiceGeneration) playbackStarted(stamp, current.value.reply) },
                        { if (stamp == voiceGeneration) finishPlayback() },
                        { message -> if (stamp == voiceGeneration) voiceFailure(message) })
                }
                "tts.chunk" -> if (payload.getString("playback_id") == playbackId) {
                    val bytes = Base64.getDecoder().decode(payload.getString("audio"))
                    require(bytes.size <= 8192 && bytes.size % 2 == 0)
                    voice?.pcmChunk(bytes)
                }
                "tts.end" -> if (payload.getString("playback_id") == playbackId) voice?.endPcm()
                "tts.error" -> {
                    if (replyTo == null || replyTo != cloudReply
                        || payload.optString("voice_profile_id") != current.value.voiceProfileId) return
                    if (payload.optString("playback_id") == playbackId || playbackId == null) {
                        stopVoice()
                        val fallback = payload.optString("fallback_text")
                        if (current.value.voiceAllowed && current.value.voiceEnabled && !interrupted && fallback.isNotBlank()) {
                            current.value = current.value.copy(message = "家人声音暂时用不了。念念会用普通声音朗读。")
                            speak(fallback)
                        } else current.value = current.value.copy(message = "家人声音暂时用不了。您可以看文字。")
                    }
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
                    handsFree = false
                    stopVoice()
                    current.value = current.value.copy(busy = false, state = "IDLE",
                        message = when (payload.optString("code")) {
                            "PROACTIVE_INVITATION_EXPIRED" -> "邀请已过期或设置已变化。您仍可直接说话或打字。"
                            "TURN_TIMEOUT" -> "这次回复等得太久了。您可以再试一次。"
                            else -> "这次没能完成。您可以再试一次。"
                        })
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
        if (type !in listOf("ping", "session.start")) clearInvitation()
        val frame = JSONObject().put("type", type).put("conversation_id", current.value.id)
            .put("sequence", ++clientSequence).put("occurred_at", Instant.now().toString()).put("payload", payload)
        if (socket?.send(frame.toString()) != true) { disconnected(0); return false }
        return true
    }

    private fun clearInvitation() {
        invitationDeadline?.cancel()
        current.value = current.value.copy(proactiveInvitationId = "", proactiveInvitationText = "")
    }

    fun respondToInvitation(action: String): Boolean {
        require(action in listOf("ACCEPT", "DECLINE", "PAUSE_TODAY"))
        val id = current.value.proactiveInvitationId
        if (id.isBlank()) return false
        return input(when (action) { "ACCEPT" -> "我愿意聊一会儿"; "DECLINE" -> "暂时不聊"; else -> "今天少打扰我" }, id, action)
    }

    fun input(text: String, invitationId: String? = null, invitationResponse: String? = null): Boolean {
        if (!current.value.connected || current.value.busy || current.value.recording || current.value.recognizing
            || text.isBlank() || text.length > 2000) return false
        when (voiceCommand(text)) {
            VoiceCommand.REPEAT -> { repeat(); return true }
            VoiceCommand.SLOWER -> { setSpeechRate(true, replay = true); return true }
            VoiceCommand.NORMAL_SPEED -> { setSpeechRate(false, replay = true); return true }
            VoiceCommand.STOP -> { interrupt(); return true }
            VoiceCommand.END -> { end(); return true }
            null -> Unit
        }
        stopVoice()
        val payload = JSONObject().put("text", text).put("timezone", ZoneId.systemDefault().id)
            .put("speech_rate", if (current.value.slowSpeech) 0.8 else 1.0)
        weatherCityId?.let { payload.put("weather_city_id", it) }
        if (invitationId != null) payload.put("proactive_invitation_id", invitationId).put("proactive_response", invitationResponse)
        current.value = current.value.copy(retryText = if (invitationId == null) text else "")
        if (!send("text.input", payload)) return false
        replyFloor = clientSequence
        interrupted = false
        current.value = current.value.copy(busy = true, state = "THINKING", reply = "", message = "",
            messages = (current.value.messages + ChatMessage(true, text)).takeLast(20))
        awaitTurn()
        return true
    }

    private fun awaitTurn() {
        val stamp = generation
        val request = replyFloor
        deadline?.cancel()
        deadline = tasks.launch {
            delay(25000)
            if (stamp == generation && request == replyFloor && current.value.busy)
                stopTurn("这次回复等得太久了。您可以再试一次。", keepInput = true)
        }
    }

    fun interrupt() = stopTurn("已停止。可以重新说话或打字。")

    private fun stopTurn(message: String, keepInput: Boolean = false) {
        handsFree = false
        stopVoice()
        deadline?.cancel()
        interrupted = true
        if (!keepInput) current.value = current.value.copy(retryText = "")
        if (send("interrupt")) {
            replyFloor = clientSequence
            current.value = current.value.copy(busy = false, state = "IDLE", message = message)
        }
    }
    fun repeat() {
        if (current.value.connected && !current.value.busy && !current.value.recording && !current.value.recognizing) {
            stopVoice()
            if (current.value.reply.isEmpty()) {
                current.value = current.value.copy(state = "IDLE", message = "还没有可重播的回答，请先说话或打字。")
                return
            }
            if (send("repeat", JSONObject().put("speech_rate", if (current.value.slowSpeech) 0.8 else 1.0))) {
                replyFloor = clientSequence; interrupted = false
                current.value = current.value.copy(busy = true, state = "THINKING", message = "正在准备重播…")
                awaitTurn()
            }
        }
    }
    fun slowDown() {
        if (!current.value.busy) {
            current.value = current.value.copy(slow = !current.value.slow)
        }
    }
    fun voiceEntry(announceIdentity: Boolean = false, handsFree: Boolean = false) {
        if (!current.value.connected) return
        if (!current.value.voiceAllowed) return voicePermissionDenied("请先在“家庭与授权设置 → 用于我与念念的交流”中允许语音处理，或继续打字。")
        val device = voice ?: return voicePermissionDenied("设备语音服务未就绪，您可以继续打字。")
        interrupt()
        if (!current.value.connected) return
        this.handsFree = handsFree
        val id = current.value.id
        if (announceIdentity && introducedSessionId != id) {
            introducedSessionId = id
            speak(CONVERSATION_IDENTITY, onComplete = { startListening(device) }, onFailure = {
                introducedSessionId = ""
                voiceFailure("身份提示暂时无法朗读。请看文字，再点“继续说话”。", VoiceRecovery.CONFIRM_IDENTITY)
            })
        } else startListening(device)
    }

    fun confirmVoiceIdentity(handsFree: Boolean = false) {
        val value = current.value
        if (!value.connected || !value.voiceAllowed || value.voiceRecovery != VoiceRecovery.CONFIRM_IDENTITY) return
        introducedSessionId = value.id
        voiceEntry(announceIdentity = true, handsFree = handsFree)
    }

    private fun startListening(device: ConversationVoice) {
        val stamp = voiceGeneration
        current.value = current.value.copy(recognizing = true, state = "THINKING", voiceEnabled = true,
            message = "正在准备麦克风…")
        voiceDeadline = tasks.launch {
            delay(15000)
            if (stamp == voiceGeneration) voiceFailure("麦克风还没准备好。您可以重说或打字。", VoiceRecovery.RETRY)
        }
        device.listen(
            ready = {
                if (stamp == voiceGeneration && !current.value.recording) {
                    current.value = current.value.copy(recording = true, recognizing = false, state = "LISTENING",
                        message = "请说话，说完可点“说完了”。")
                    voiceDeadline?.cancel()
                    voiceDeadline = tasks.launch {
                        delay(30000)
                        if (stamp == voiceGeneration && current.value.recording) finishListening()
                    }
                }
            },
            partial = { text -> if (stamp == voiceGeneration && current.value.recording) {
                current.value = current.value.copy(partialTranscript = text.take(2000))
            } },
            final = { text -> if (stamp == voiceGeneration) {
                if (text.isBlank() || text.length > 2000) {
                    val message = if (text.isBlank()) "刚才没听清。您可以再说一遍。"
                        else "刚才那段有些长。您可以分开说。"
                    voiceFailure(message, VoiceRecovery.RETRY)
                } else {
                    stopVoice()
                    input(text)
                }
            } },
            failed = { message -> if (stamp == voiceGeneration) voiceFailure(message, VoiceRecovery.RETRY) },
            captured = { if (stamp == voiceGeneration) awaitRecognition() })
    }

    fun finishListening() {
        if (!current.value.recording) return
        awaitRecognition()
        voice?.finishListening()
    }

    private fun awaitRecognition() {
        if (!current.value.recording) return
        val stamp = voiceGeneration
        current.value = current.value.copy(recording = false, recognizing = true, state = "THINKING", message = "正在识别…")
        voiceDeadline?.cancel()
        voiceDeadline = tasks.launch {
            delay(10000)
            if (stamp == voiceGeneration) voiceFailure("这次没识别出来。您可以重说或打字。", VoiceRecovery.RETRY)
        }
    }

    fun voicePermissionDenied(message: String = "未开启麦克风权限，您仍可使用文字聊天。") {
        current.value = current.value.copy(message = message)
    }

    private fun voiceFailure(message: String, recovery: VoiceRecovery? = null) {
        handsFree = false
        stopVoice()
        current.value = current.value.copy(state = "IDLE", message = message, voiceRecovery = recovery)
    }

    private fun resumeHandsFree() {
        val value = current.value
        if (handsFree && value.connected && value.voiceAllowed && value.voiceEnabled && !value.busy)
            voice?.let(::startListening)
    }

    private fun playbackStarted(stamp: Int, text: String) {
        voiceDeadline?.cancel()
        val canStopByVoice = handsFree && voice?.supportsPlaybackStop == true && playbackStopAllowed(text)
        current.value = current.value.copy(speechPending = false, speaking = true, state = "SPEAKING",
            canStopByVoice = canStopByVoice)
        if (canStopByVoice) voice?.listenForPlaybackStop {
            if (stamp == voiceGeneration && handsFree && current.value.speaking) {
                interrupt()
                handsFree = true
                resumeHandsFree()
            }
        }
    }

    private fun finishPlayback(onComplete: (() -> Unit)? = null) {
        stopVoice()
        current.value = current.value.copy(state = "IDLE")
        if (onComplete != null) onComplete() else resumeHandsFree()
    }

    private fun speak(text: String, onComplete: (() -> Unit)? = null, onFailure: (() -> Unit)? = null) {
        if (!current.value.voiceAllowed) return
        val device = voice ?: return
        stopVoice()
        val stamp = voiceGeneration
        current.value = current.value.copy(speechPending = true)
        fun complete(error: String? = null) {
            if (stamp != voiceGeneration) return
            if (error == null) finishPlayback(onComplete)
            else if (onFailure != null) onFailure()
            else voiceFailure(error)
        }
        voiceDeadline = tasks.launch {
            delay(10000)
            complete("朗读启动超时，请查看文字或稍后重试。")
        }
        device.speak(text, current.value.slowSpeech,
            started = { if (stamp == voiceGeneration) {
                playbackStarted(stamp, text)
                voiceDeadline = tasks.launch {
                    delay(180000)
                    complete("朗读已停止，您可以继续聊天。")
                }
            } },
            finished = { complete() }, failed = { complete(it) })
    }

    fun toggleSpeech() {
        if (!current.value.voiceAllowed) return voicePermissionDenied("请先允许语音处理，或继续查看文字。")
        handsFree = false
        stopVoice()
        current.value = current.value.copy(voiceEnabled = !current.value.voiceEnabled, state = if (current.value.busy) "THINKING" else "IDLE")
    }

    fun toggleSpeechRate() {
        setSpeechRate(!current.value.slowSpeech, current.value.speaking || current.value.speechPending)
    }

    private fun setSpeechRate(slow: Boolean, replay: Boolean) {
        current.value = current.value.copy(slowSpeech = slow,
            state = if (current.value.busy) "THINKING" else current.value.state,
            message = if (slow) "已设为慢速朗读。" else "已恢复正常语速。")
        if (replay && current.value.reply.isNotEmpty()) repeat()
    }

    private fun updateVoicePermission(allowed: Boolean) {
        val wasAllowed = current.value.voiceAllowed
        current.value = current.value.copy(voiceAllowed = allowed)
        if (!allowed) {
            handsFree = false
            val active = current.value.voiceActive
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
