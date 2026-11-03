package org.example.niannian.elder

import android.content.Context
import java.io.IOException
import kotlin.coroutines.resume
import kotlin.coroutines.resumeWithException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withContext
import org.json.JSONObject
import org.vosk.Model
import org.vosk.Recognizer
import org.vosk.android.RecognitionListener
import org.vosk.android.SpeechService
import org.vosk.android.StorageService

private val modelCopy = Mutex()
private const val WAKE_GRAMMAR = """["你好 小念", "[unk]"]"""

internal fun hasWakeModel(context: Context): Boolean =
    runCatching { context.assets.open("wake-cn/uuid").use { it.read() >= 0 } }.getOrDefault(false)

internal suspend fun waitForWakePhrase(context: Context, ready: () -> Unit) = withContext(Dispatchers.IO) {
    val path = modelCopy.withLock { StorageService.sync(context.applicationContext, "wake-cn", "wake-model") }
    Model(path).use { model ->
        Recognizer(model, 16_000f, WAKE_GRAMMAR).use { recognizer ->
            withContext(Dispatchers.Main) {
                val microphone = SpeechService(recognizer, 16_000f)
                try {
                    suspendCancellableCoroutine { waiting ->
                        val listener = object : RecognitionListener {
                            override fun onPartialResult(hypothesis: String?) = Unit
                            override fun onFinalResult(hypothesis: String?) = Unit
                            override fun onTimeout() = onError(IOException("Wake microphone timed out"))
                            override fun onError(exception: Exception) {
                                if (waiting.isActive) waiting.resumeWithException(exception)
                            }
                            override fun onResult(hypothesis: String?) {
                                val phrase = runCatching {
                                    JSONObject(hypothesis.orEmpty()).optString("text").filterNot(Char::isWhitespace)
                                }.getOrDefault("")
                                if (waiting.isActive && phrase == "你好小念") waiting.resume(Unit)
                            }
                        }
                        if (microphone.startListening(listener)) ready()
                        else waiting.resumeWithException(IOException("Wake microphone unavailable"))
                    }
                } finally {
                    microphone.cancel()
                    microphone.shutdown()
                }
            }
        }
    }
}
