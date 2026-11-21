package org.example.niannian.data

import java.net.URI

object ConnectionPolicy {
    fun origin(value: String, debug: Boolean): String {
        val uri = try { URI(value.trim()) } catch (_: Exception) {
            throw IllegalArgumentException("服务地址格式不正确。")
        }
        require(uri.host != null && uri.rawUserInfo == null && uri.rawQuery == null && uri.rawFragment == null &&
            uri.rawPath in listOf("", "/") && (uri.port == -1 || uri.port in 1..65535)) { "请输入不含账号和路径的服务地址。" }
        require(uri.scheme == "https" || (debug && uri.scheme == "http" && uri.host in
            setOf("10.0.2.2", "127.0.0.1", "localhost"))) { "请使用 HTTPS；调试版仅允许本机或模拟器的 HTTP。" }
        return uri.toASCIIString().trimEnd('/')
    }

    fun invitation(value: String): String {
        val token = value.trim()
        if (token.matches(Regex("(?:[A-Za-z2-7]{4}[- ]){3}[A-Za-z2-7]{4}"))) {
            return token.replace("-", "").replace(" ", "").uppercase()
        }
        require(token.matches(Regex("[A-Za-z0-9_-]{16,512}"))) { "请输入家人提供的完整家庭配对码。" }
        return token
    }

    fun displayPairingCode(token: String): String =
        if (token.matches(Regex("[A-Z2-7]{16}"))) token.chunked(4).joinToString("-") else token
}
