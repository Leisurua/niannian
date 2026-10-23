package org.example.niannian.feature.conversation

/** Device speech services. Callbacks run on the main thread; no audio is stored by the app. */
interface ConversationVoice {
    fun listen(partial: (String) -> Unit, final: (String) -> Unit, failed: (String) -> Unit, captured: () -> Unit)
    fun finishListening()
    fun speak(text: String, slow: Boolean, started: () -> Unit, finished: () -> Unit, failed: (String) -> Unit)
    fun stop()
    fun close()
}
