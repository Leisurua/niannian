package org.example.niannian.feature.conversation

internal enum class VoiceCommand { REPEAT, SLOWER, NORMAL_SPEED, STOP, END }

/** Match complete commands only; questions, quoted speech and longer sentences remain chat. */
internal fun voiceCommand(text: String): VoiceCommand? = when (
    text.trim().trimEnd('。', '！', '!', '.', '，', ',').trim()
) {
    "再说一遍", "请再说一遍", "再讲一遍", "再读一遍", "重复一遍" -> VoiceCommand.REPEAT
    "慢一点", "说慢一点", "请说慢一点", "慢点说", "说慢点" -> VoiceCommand.SLOWER
    "恢复语速", "正常语速", "恢复正常语速" -> VoiceCommand.NORMAL_SPEED
    "停一下", "暂停", "停止", "别说了", "不要说了" -> VoiceCommand.STOP
    "结束聊天", "结束对话", "不聊了" -> VoiceCommand.END
    else -> null
}

/** Device speech services. Callbacks run on the main thread; no audio is stored by the app. */
interface ConversationVoice {
    fun listen(partial: (String) -> Unit, final: (String) -> Unit, failed: (String) -> Unit, captured: () -> Unit)
    fun finishListening()
    fun speak(text: String, slow: Boolean, started: () -> Unit, finished: () -> Unit, failed: (String) -> Unit)
    fun startPcm(started: () -> Unit, finished: () -> Unit, failed: (String) -> Unit) { failed("此设备不支持云端声音播放。") }
    fun pcmChunk(bytes: ByteArray) {}
    fun endPcm() {}
    fun stop()
    fun close()
}
