package org.example.niannian.feature.voice

import android.media.*
import android.os.Handler
import android.os.Looper
import java.io.ByteArrayOutputStream
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.util.concurrent.ArrayBlockingQueue
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicInteger

/** In-memory PCM only; bounded buffers, cancellation invalidates late callbacks. */
class PcmPlayer {
    private val epoch = AtomicInteger()
    private val main = Handler(Looper.getMainLooper())
    private var queue: ArrayBlockingQueue<ByteArray>? = null
    @Volatile private var track: AudioTrack? = null
    private var failure: ((String) -> Unit)? = null
    fun start(started: () -> Unit, finished: () -> Unit, failed: (String) -> Unit) {
        stop()
        val stamp = epoch.get()
        val pending = ArrayBlockingQueue<ByteArray>(32)
        queue = pending; failure = failed
        Thread {
            var output: AudioTrack? = null
            try {
                val minimum = AudioTrack.getMinBufferSize(24000, AudioFormat.CHANNEL_OUT_MONO, AudioFormat.ENCODING_PCM_16BIT)
                require(minimum > 0)
                output = AudioTrack.Builder().setAudioAttributes(AudioAttributes.Builder()
                    .setUsage(AudioAttributes.USAGE_MEDIA).setContentType(AudioAttributes.CONTENT_TYPE_SPEECH).build())
                    .setAudioFormat(AudioFormat.Builder().setSampleRate(24000).setChannelMask(AudioFormat.CHANNEL_OUT_MONO)
                        .setEncoding(AudioFormat.ENCODING_PCM_16BIT).build()).setBufferSizeInBytes(maxOf(minimum, 8192)).build()
                if (epoch.get() != stamp) return@Thread
                track = output
                var playing = false
                var announced = false
                var written = 0L
                while (epoch.get() == stamp) {
                    val data = pending.poll(15, TimeUnit.SECONDS) ?: error("Audio timeout")
                    if (data.isEmpty()) break
                    if (!playing) { output.play(); playing = true }
                    var offset = 0
                    while (offset < data.size && epoch.get() == stamp) {
                        val count = output.write(data, offset, data.size - offset, AudioTrack.WRITE_BLOCKING)
                        check(count > 0); offset += count; written += count / 2
                    }
                    if (!announced) { announced = true; main.post { if (epoch.get() == stamp) started() } }
                }
                while (epoch.get() == stamp && (output.playbackHeadPosition.toLong() and 0xffffffffL) < written) Thread.sleep(20)
                main.post { if (epoch.get() == stamp) finished() }
            } catch (_: Exception) { main.post { if (epoch.get() == stamp) failed("声音播放不可用，请查看文字。") } }
            finally { if (track === output) track = null; runCatching { output?.release() } }
        }.apply { isDaemon = true; name = "niannian-pcm" }.start()
    }
    fun chunk(data: ByteArray) {
        require(data.isNotEmpty() && data.size <= 8192 && data.size % 2 == 0)
        if (queue?.offer(data) == false) { val callback = failure; stop(); callback?.invoke("声音缓冲已满，已停止播放，请重试。") }
    }
    fun offerPreview(data: ByteArray): Boolean = queue?.offer(data, 5, TimeUnit.SECONDS) == true
    fun finish() {
        if (queue?.offer(ByteArray(0)) == false) { val callback = failure; stop(); callback?.invoke("声音缓冲已满，已停止播放。") }
    }
    fun stop() {
        epoch.incrementAndGet(); queue?.clear(); queue?.offer(ByteArray(0)); queue = null; failure = null
        runCatching { track?.pause(); track?.flush() }
    }
}

class VoiceRecorder {
    @Volatile private var active = false
    @Volatile private var recorder: AudioRecord? = null
    private var thread: Thread? = null
    private var result: ByteArray? = null
    fun start() {
        check(!active)
        val minimum = AudioRecord.getMinBufferSize(24000, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT)
        require(minimum > 0)
        val input = AudioRecord(MediaRecorder.AudioSource.VOICE_RECOGNITION, 24000,
            AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT, maxOf(minimum, 8192))
        require(input.state == AudioRecord.STATE_INITIALIZED)
        recorder = input; result = null; active = true
        input.startRecording()
        thread = Thread {
            val bytes = ByteArrayOutputStream()
            try {
                val buffer = ByteArray(4096)
                while (active && bytes.size() < 24000 * 2 * 60) {
                    val size = input.read(buffer, 0, minOf(buffer.size, 24000 * 2 * 60 - bytes.size()))
                    if (size <= 0) break
                    bytes.write(buffer, 0, size)
                }
                if (bytes.size() >= 24000 * 2 * 10) result = wav(bytes.toByteArray())
            } finally { active = false; runCatching { input.stop() }; input.release(); recorder = null }
        }.apply { isDaemon = true; name = "niannian-record"; start() }
    }
    fun finish(): ByteArray {
        active = false; runCatching { recorder?.stop() }; thread?.join(2000)
        return result ?: error("请录制至少10秒清晰语音。")
    }
    fun cancel() { active = false; result = null; runCatching { recorder?.stop() } }
    companion object {
        fun wav(pcm: ByteArray): ByteArray = ByteBuffer.allocate(44 + pcm.size).order(ByteOrder.LITTLE_ENDIAN)
            .put("RIFF".toByteArray()).putInt(36 + pcm.size).put("WAVEfmt ".toByteArray()).putInt(16)
            .putShort(1).putShort(1).putInt(24000).putInt(48000).putShort(2).putShort(16)
            .put("data".toByteArray()).putInt(pcm.size).put(pcm).array()
        fun pcm(wav: ByteArray): ByteArray {
            require(wav.size >= 44 && String(wav, 0, 4) == "RIFF" && String(wav, 8, 4) == "WAVE")
            val buffer = ByteBuffer.wrap(wav).order(ByteOrder.LITTLE_ENDIAN)
            var offset = 12; var valid = false
            while (offset + 8 <= wav.size) {
                val size = buffer.getInt(offset + 4); require(size >= 0 && size <= wav.size - offset - 8)
                val kind = String(wav, offset, 4)
                if (kind == "fmt ") {
                    require(size >= 16 && buffer.getShort(offset + 8).toInt() == 1 && buffer.getShort(offset + 10).toInt() == 1
                        && buffer.getInt(offset + 12) == 24000 && buffer.getShort(offset + 22).toInt() == 16)
                    valid = true
                }
                if (kind == "data") { require(valid && size % 2 == 0); return wav.copyOfRange(offset + 8, offset + 8 + size) }
                offset += 8 + size + size % 2
            }
            error("WAV data missing")
        }
    }
}
