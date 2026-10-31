package org.example.niannian.feature.voice

import org.junit.Assert.assertArrayEquals
import org.junit.Test

class VoiceAudioTest {
    @Test fun recordingRoundTripsThroughSharedWavFormat() {
        val pcm = ByteArray(480) { (it % 127).toByte() }
        assertArrayEquals(pcm, VoiceRecorder.pcm(VoiceRecorder.wav(pcm)))
    }

    @Test(expected = IllegalArgumentException::class)
    fun wrongSampleRateIsRejectedBeforePlayback() {
        val wav = VoiceRecorder.wav(ByteArray(480))
        wav[24] = 0
        VoiceRecorder.pcm(wav)
    }
}
