package org.example.niannian.feature.conversation

import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import okio.ByteString
import java.util.concurrent.TimeUnit

class ConversationTransport {
    private val client = OkHttpClient.Builder().followRedirects(false).followSslRedirects(false)
        .connectTimeout(10, TimeUnit.SECONDS).pingInterval(15, TimeUnit.SECONDS).build()

    fun connect(url: String, token: String, message: (String) -> Unit, closed: (Int) -> Unit): ConversationSocket {
        val request = Request.Builder().url(url).header("Authorization", "Bearer $token").build()
        val socket = client.newWebSocket(request, object : WebSocketListener() {
            override fun onMessage(webSocket: WebSocket, text: String) {
                if (text.toByteArray(Charsets.UTF_8).size > 16384) { webSocket.cancel(); closed(4400) }
                else message(text)
            }
            override fun onMessage(webSocket: WebSocket, bytes: ByteString) { webSocket.cancel(); closed(4400) }
            override fun onClosing(webSocket: WebSocket, code: Int, reason: String) { webSocket.close(code, null); closed(code) }
            override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
                closed(if (response?.code in listOf(401, 403)) 4403 else 0)
            }
        })
        return object : ConversationSocket {
            override fun send(text: String) = socket.send(text)
            override fun close() = socket.cancel()
        }
    }
}
