package org.example.niannian.elder

import android.content.Context
import java.io.IOException
import kotlin.coroutines.resume
import kotlin.coroutines.resumeWithException
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.coroutines.withContext
import kotlinx.coroutines.launch
import org.example.niannian.feature.conversation.AndroidConversationVoice
import org.example.niannian.feature.conversation.ConversationVoice
import org.json.JSONObject
import org.vosk.android.RecognitionListener
import org.vosk.android.SpeechService

private val hanSpacing = Regex("(?<=[\\u3400-\\u9fff])\\s+|\\s+(?=[\\u3400-\\u9fff])")

internal fun elderConversationVoice(context: Context): ConversationVoice {
    val system = AndroidConversationVoice(context)
    return if (hasWakeModel(context)) OfflineConversationVoice(context.applicationContext, system) else system
}

/** Reuse the bundled wake model for open-vocabulary recognition and keep device playback. */
private class OfflineConversationVoice(private val context: Context, private val playback: ConversationVoice) :
    ConversationVoice by playback {
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
    private var listening: Job? = null
    private var finishCapture: (() -> Unit)? = null

    override fun listen(ready: () -> Unit, partial: (String) -> Unit, final: (String) -> Unit,
        failed: (String) -> Unit, captured: () -> Unit) {
        val previous = listening
        stop()
        listening = scope.launch {
            try {
                previous?.join()
                val text = withOfflineRecognizer(context) { recognizer ->
                    withContext(Dispatchers.Main) {
                        val microphone = SpeechService(recognizer, OFFLINE_SAMPLE_RATE)
                        try {
                            suspendCancellableCoroutine { turn ->
                                fun complete(text: String) {
                                    if (!turn.isActive) return
                                    captured()
                                    turn.resume(text)
                                }
                                val listener = object : RecognitionListener {
                                    override fun onPartialResult(hypothesis: String?) {
                                        if (turn.isActive) partial(transcript(hypothesis, "partial"))
                                    }
                                    override fun onResult(hypothesis: String?) {
                                        val text = transcript(hypothesis, "text")
                                        if (text.isNotBlank()) complete(text)
                                    }
                                    override fun onFinalResult(hypothesis: String?) = complete(transcript(hypothesis, "text"))
                                    override fun onTimeout() = complete("")
                                    override fun onError(exception: Exception) {
                                        if (turn.isActive) turn.resumeWithException(exception)
                                    }
                                }
                                finishCapture = { if (!microphone.stop()) complete("") }
                                if (microphone.startListening(listener)) ready()
                                else turn.resumeWithException(IOException("Microphone unavailable"))
                            }
                        } finally {
                            finishCapture = null
                            microphone.cancel()
                            microphone.shutdown()
                        }
                    }
                }
                final(text)
            } catch (cancelled: CancellationException) {
                throw cancelled
            } catch (_: SecurityException) {
                failed("未获准使用麦克风，您可以继续打字。")
            } catch (_: Exception) {
                failed("本机中文识别暂时不可用，请重试或继续打字。")
            }
        }
    }

    override fun finishListening() { finishCapture?.invoke() }

    override fun speak(text: String, slow: Boolean, started: () -> Unit, finished: () -> Unit, failed: (String) -> Unit) {
        listening?.cancel()
        playback.speak(text, slow, started, finished, failed)
    }

    override fun startPcm(started: () -> Unit, finished: () -> Unit, failed: (String) -> Unit) {
        listening?.cancel()
        playback.startPcm(started, finished, failed)
    }

    override fun stop() {
        listening?.cancel()
        playback.stop()
    }

    override fun close() {
        scope.cancel()
        playback.close()
    }

    private fun transcript(hypothesis: String?, key: String): String = runCatching {
        JSONObject(hypothesis.orEmpty()).optString(key).trim().replace(hanSpacing, "")
    }.getOrDefault("")
}
