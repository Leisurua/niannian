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

data class ConversationState(val family: String = "", val user: String = "", val id: String = "",
    val state: String = "IDLE", val connected: Boolean = false, val busy: Boolean = false,
    val reply: String = "", val message: String = "", val slow: Boolean = false)

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
    private val earlyFrames = mutableListOf<String>()
    private val tasks get() = scope ?: viewModelScope

    fun clear() {
        generation++
        job?.cancel()
        deadline?.cancel()
        socket?.close()
        socket = null
        clientSequence = 0
        serverSequence = 0
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
        deadline?.cancel()
        earlyFrames.clear()
        socket?.close()
        socket = null
        current.value = current.value.copy(connected = false, busy = false, reply = "",
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
            when (type) {
                "session.ready" -> {
                    if (awaitingHandshake) {
                        deadline?.cancel()
                        current.value = current.value.copy(connected = true, busy = false, state = "LISTENING", message = "")
                        awaitingHandshake = false
                        send("session.start", JSONObject().put("client_session_id", UUID.randomUUID().toString()).put("input_mode", "TEXT"))
                    }
                }
                "assistant.state" -> {
                    val value = payload.getString("state")
                    require(value in listOf("IDLE", "LISTENING", "THINKING", "SPEAKING", "WARNING", "OFFLINE", "ERROR"))
                    current.value = current.value.copy(state = value, busy = value == "THINKING")
                    if (value != "THINKING") deadline?.cancel()
                }
                "assistant.text" -> {
                    val text = payload.getString("text")
                    require(text.length <= 2000)
                    current.value = current.value.copy(reply = text)
                }
                "error" -> current.value = current.value.copy(busy = false, message = "暂时无法完成，请稍后再试。当前仅显示文字。")
                "pong" -> Unit
                else -> error("Unsupported event")
            }
        } catch (_: Exception) {
            disconnected(0)
        }
    }

    private fun send(type: String, payload: JSONObject = JSONObject()) {
        if (!current.value.connected) return
        val frame = JSONObject().put("type", type).put("conversation_id", current.value.id)
            .put("sequence", ++clientSequence).put("occurred_at", Instant.now().toString()).put("payload", payload)
        if (socket?.send(frame.toString()) != true) disconnected(0)
    }

    fun input(text: String) {
        if (!current.value.connected || current.value.busy || text.isBlank() || text.length > 2000) return
        current.value = current.value.copy(busy = true, state = "THINKING", reply = "", message = "")
        send("text.input", JSONObject().put("text", text))
        val stamp = generation
        deadline?.cancel()
        deadline = tasks.launch { delay(25000); if (stamp == generation && current.value.busy) disconnected(0) }
    }

    fun interrupt() { deadline?.cancel(); send("interrupt"); current.value = current.value.copy(reply = "", busy = false) }
    fun repeat() { if (!current.value.busy) send("repeat") }
    fun slowDown() {
        if (!current.value.busy) {
            current.value = current.value.copy(slow = true, message = "当前为文字演示，已放大文字；没有正在播放的语音。")
            send("slow_down")
        }
    }
    fun voiceEntry() {
        current.value = current.value.copy(message = "麦克风尚未启用。可以点选下方模拟话题，或使用文字备用入口；不会采集声音。")
        if (!current.value.connected) start()
    }
    fun volume() {
        current.value = current.value.copy(message = "当前没有播放语音，音量未改变。实际播放接入后可使用设备音量键。")
    }
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
                if (stamp == generation) current.value = current.value.copy(busy = false,
                    message = "本次会话已结束。摘要功能尚未开放，不保存或展示完整逐字稿。")
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
    override fun onCleared() { clear(); super.onCleared() }
}
