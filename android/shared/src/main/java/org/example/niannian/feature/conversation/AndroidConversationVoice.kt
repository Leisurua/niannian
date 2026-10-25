package org.example.niannian.feature.conversation

import android.content.Context
import android.content.Intent
import android.media.AudioAttributes
import android.media.AudioFocusRequest
import android.media.AudioManager
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.speech.RecognitionListener
import android.speech.RecognizerIntent
import android.speech.SpeechRecognizer
import android.speech.tts.TextToSpeech
import android.speech.tts.UtteranceProgressListener
import java.util.Locale

/** Uses the user's installed speech services, which may use the network. */
class AndroidConversationVoice(context: Context) : ConversationVoice {
    private val app = context.applicationContext
    private val main = Handler(Looper.getMainLooper())
    private val audio = app.getSystemService(Context.AUDIO_SERVICE) as AudioManager
    private var recognizer: SpeechRecognizer? = null
    private var tts: TextToSpeech? = null
    private var ttsReady = false
    private var epoch = 0L
    private var closed = false
    private var pendingSpeech: (() -> Unit)? = null
    private var failedSpeech: ((String) -> Unit)? = null
    private var activeSpeech: String? = null
    private var focus: AudioFocusRequest? = null
    private val attributes = AudioAttributes.Builder().setUsage(AudioAttributes.USAGE_MEDIA)
        .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH).build()

    override fun listen(partial: (String) -> Unit, final: (String) -> Unit, failed: (String) -> Unit, captured: () -> Unit) {
        stop()
        if (closed) return
        val stamp = epoch
        fun fail(message: String) {
            if (stamp != epoch || closed) return
            stop()
            failed(message)
        }
        try {
            if (!SpeechRecognizer.isRecognitionAvailable(app)) {
                fail("设备没有可用的语音识别服务，请在系统设置中启用，或继续打字。")
                return
            }
            val service = SpeechRecognizer.createSpeechRecognizer(app)
            recognizer = service
            service.setRecognitionListener(object : RecognitionListener {
                override fun onReadyForSpeech(params: Bundle?) = Unit
                override fun onBeginningOfSpeech() = Unit
                override fun onRmsChanged(rmsdB: Float) = Unit
                override fun onBufferReceived(buffer: ByteArray?) = Unit
                override fun onEndOfSpeech() { if (stamp == epoch && !closed) captured() }
                override fun onEvent(eventType: Int, params: Bundle?) = Unit
                override fun onPartialResults(partialResults: Bundle?) {
                    if (stamp == epoch && !closed) partial(
                        partialResults?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)?.firstOrNull().orEmpty())
                }
                override fun onResults(results: Bundle?) {
                    if (stamp != epoch || closed) return
                    val text = results?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)?.firstOrNull().orEmpty()
                    stop()
                    final(text)
                }
                override fun onError(error: Int) = fail(when (error) {
                    SpeechRecognizer.ERROR_INSUFFICIENT_PERMISSIONS -> "未获准使用麦克风，您可以继续打字。"
                    SpeechRecognizer.ERROR_NO_MATCH, SpeechRecognizer.ERROR_SPEECH_TIMEOUT -> "没有听清，请再说一次或改用打字。"
                    SpeechRecognizer.ERROR_NETWORK, SpeechRecognizer.ERROR_NETWORK_TIMEOUT -> "语音识别网络不可用，请稍后重试或打字。"
                    else -> "语音识别暂时不可用，请重试或继续打字。"
                })
            })
            service.startListening(Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH)
                .putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
                .putExtra(RecognizerIntent.EXTRA_LANGUAGE, "zh-CN")
                .putExtra(RecognizerIntent.EXTRA_PARTIAL_RESULTS, true)
                .putExtra(RecognizerIntent.EXTRA_MAX_RESULTS, 1))
        } catch (_: SecurityException) {
            fail("未获准使用麦克风，您可以继续打字。")
        } catch (_: Exception) {
            fail("语音识别暂时不可用，请重试或继续打字。")
        }
    }

    override fun finishListening() {
        try { recognizer?.stopListening() } catch (_: Exception) { stop() }
    }

    override fun speak(text: String, slow: Boolean, started: () -> Unit, finished: () -> Unit, failed: (String) -> Unit) {
        stop()
        if (closed) return
        val stamp = epoch
        val utterance = stamp.toString()
        failedSpeech = failed
        fun fail() {
            if (stamp != epoch || closed) return
            stop()
            failed("朗读暂时不可用，请查看文字；可在系统设置中检查中文语音引擎。")
        }
        pendingSpeech = {
            if (stamp == epoch && !closed) {
                try {
                    val engine = tts
                    if (engine == null || engine.setLanguage(Locale.SIMPLIFIED_CHINESE) < 0) {
                        fail()
                    } else {
                        engine.setAudioAttributes(attributes)
                        engine.setSpeechRate(if (slow) 0.75f else 1.0f)
                        engine.setOnUtteranceProgressListener(object : UtteranceProgressListener() {
                            private fun deliver(id: String?, action: () -> Unit) {
                                main.post { if (!closed && stamp == epoch && id == activeSpeech) action() }
                            }
                            override fun onStart(utteranceId: String?) = deliver(utteranceId, started)
                            override fun onDone(utteranceId: String?) = deliver(utteranceId) { stop(); finished() }
                            @Deprecated("Android callback")
                            override fun onError(utteranceId: String?) = deliver(utteranceId) { fail() }
                            override fun onError(utteranceId: String?, errorCode: Int) = deliver(utteranceId) { fail() }
                            override fun onStop(utteranceId: String?, interrupted: Boolean) = deliver(utteranceId) { stop(); finished() }
                        })
                        val request = AudioFocusRequest.Builder(AudioManager.AUDIOFOCUS_GAIN_TRANSIENT)
                            .setAudioAttributes(attributes).setOnAudioFocusChangeListener({ change ->
                                if (change < 0 && stamp == epoch) { stop(); finished() }
                            }, main).build()
                        focus = request
                        if (audio.requestAudioFocus(request) != AudioManager.AUDIOFOCUS_REQUEST_GRANTED) {
                            fail()
                        } else {
                            activeSpeech = utterance
                            if (engine.speak(text, TextToSpeech.QUEUE_FLUSH, null, utterance) == TextToSpeech.ERROR) fail()
                        }
                    }
                } catch (_: Exception) { fail() }
            }
        }
        if (ttsReady) {
            val action = pendingSpeech; pendingSpeech = null; action?.invoke()
        } else if (tts == null) {
            try {
                tts = TextToSpeech(app) { status -> main.post {
                    if (!closed) {
                        if (status == TextToSpeech.SUCCESS) {
                            ttsReady = true
                            val action = pendingSpeech; pendingSpeech = null; action?.invoke()
                        } else {
                            val callback = failedSpeech
                            stop()
                            tts?.shutdown(); tts = null
                            callback?.invoke("设备中文朗读服务不可用，您可以继续查看文字。")
                        }
                    }
                } }
            } catch (_: Exception) { fail() }
        }
    }

    override fun stop() {
        epoch++
        pendingSpeech = null
        failedSpeech = null
        activeSpeech = null
        val recognition = recognizer; recognizer = null
        try { recognition?.cancel() } catch (_: Exception) { }
        try { recognition?.destroy() } catch (_: Exception) { }
        try { tts?.stop() } catch (_: Exception) { }
        focus?.let { audio.abandonAudioFocusRequest(it) }; focus = null
    }

    override fun close() {
        closed = true
        stop()
        tts?.shutdown(); tts = null; ttsReady = false
    }
}
