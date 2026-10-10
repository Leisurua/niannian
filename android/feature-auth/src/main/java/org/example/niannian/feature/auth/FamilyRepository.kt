package org.example.niannian.feature.auth

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.ensureActive
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLEncoder
import java.security.MessageDigest
import java.util.UUID

class ApiFailure(val status: Int, val code: String, message: String) : Exception(message)

data class RetriedWrite(val path: String, val response: JSONObject)

class FamilyRepository(
    private val store: SessionStore,
    private val debug: Boolean,
    private val connectionFactory: (URL) -> HttpURLConnection = { it.openConnection() as HttpURLConnection }
) {
    fun hasSession() = store.load().has("access_token")
    fun savedOrigin() = store.load().optString("origin", "http://10.0.2.2:8000")
    fun clear() = store.clear()
    fun hasPending() = store.load().optBoolean("pending", false)
    fun pendingInvitation() = store.load().optString("invitation", "")
    fun invitationFamily() = store.load().optString("invitation_family", "")
    fun saveInvitation(value: String, familyId: String = "") {
        val session = store.load()
        session.put("invitation", value).put("invitation_family", familyId)
        store.save(session)
    }

    private fun clearPending() {
        val session = store.load()
        session.put("pending", false)
        listOf("pending_path", "pending_method", "pending_body", "pending_key", "pending_fingerprint")
            .forEach { session.remove(it) }
        store.save(session)
    }

    suspend fun retryPending(): RetriedWrite {
        val session = store.load()
        check(session.optBoolean("pending")) { "没有需要重试的请求。" }
        val path = session.getString("pending_path")
        return RetriedWrite(path, call(path, session.getString("pending_method"),
            JSONObject(session.getString("pending_body")), true))
    }

    suspend fun readAll(path: String): List<JSONObject> {
        val rows = mutableListOf<JSONObject>()
        val seen = mutableSetOf<String>()
        var nextPath = path
        repeat(100) {
            val response = call(nextPath)
            val items = response.getJSONArray("items")
            for (index in 0 until items.length()) rows.add(items.getJSONObject(index))
            val page = response.getJSONObject("page")
            if (!page.getBoolean("has_more")) return rows
            val cursor = page.optString("next_cursor").takeUnless { it.isBlank() || it == "null" }
            if (cursor == null || !seen.add(cursor)) throw ApiFailure(502, "INVALID_PAGE", "列表未能完整读取，请重新加载。")
            nextPath = path + (if ('?' in path) "&" else "?") + "cursor=" + URLEncoder.encode(cursor, "UTF-8")
        }
        throw ApiFailure(502, "PAGE_LIMIT", "列表过长，暂未完整读取，请稍后重试。")
    }

    private fun exchange(origin: String, path: String, method: String, body: JSONObject?, access: String?, key: String?, ifMatch: String? = null): JSONObject {
        val connection = connectionFactory(URL(origin + path))
        try {
            connection.instanceFollowRedirects = false
            connection.connectTimeout = 10000
            connection.readTimeout = 10000
            connection.requestMethod = method
            connection.setRequestProperty("Accept", "application/json")
            access?.let { connection.setRequestProperty("Authorization", "Bearer $it") }
            key?.let { connection.setRequestProperty("Idempotency-Key", it) }
            ifMatch?.let { connection.setRequestProperty("If-Match", it) }
            body?.let {
                connection.doOutput = true
                connection.setRequestProperty("Content-Type", "application/json; charset=utf-8")
                connection.outputStream.use { stream -> stream.write(it.toString().toByteArray(Charsets.UTF_8)) }
            }
            val status = connection.responseCode
            val stream = if (status in 200..299) connection.inputStream else connection.errorStream
            val content = stream?.bufferedReader(Charsets.UTF_8)?.use { reader ->
                val result = StringBuilder()
                val buffer = CharArray(4096)
                while (true) {
                    val count = reader.read(buffer)
                    if (count < 0) break
                    require(result.length + count <= 1_048_576) { "服务响应过大，请稍后重试。" }
                    result.append(buffer, 0, count)
                }
                result.toString()
            }.orEmpty()
            val json = if (content.isBlank()) JSONObject() else try { JSONObject(content) } catch (_: Exception) {
                throw ApiFailure(status, "INVALID_RESPONSE", "服务响应无法读取，请检查服务地址。")
            }
            if (status !in 200..299) {
                val error = json.optJSONObject("error")
                throw ApiFailure(status, error?.optString("code").orEmpty(),
                    error?.optString("message")?.takeIf { it.isNotBlank() } ?: "服务暂不可用，请稍后重试。")
            }
            return json
        } finally { connection.disconnect() }
    }

    suspend fun login(address: String, elder: Boolean, deviceId: String) = withContext(Dispatchers.IO) {
        val origin = ConnectionPolicy.origin(address, debug)
        val body = JSONObject().put("credential", JSONObject().put("type", "DEMO")
            .put("identifier", if (elder) "demo-elder" else "demo-child"))
            .put("device", JSONObject().put("device_id", deviceId).put("name", if (elder) "演示长辈设备" else "演示家人设备").put("app_version", "0.1.0"))
        val result = exchange(origin, "/v1/auth/login", "POST", body, null, null)
        currentCoroutineContext().ensureActive()
        store.save(JSONObject().put("origin", origin).put("access_token", result.getString("access_token"))
            .put("refresh_token", result.getString("refresh_token")))
    }

    private suspend fun refreshSessionOrRequireLogin(origin: String, session: JSONObject) {
        try {
            val pair = exchange(origin, "/v1/auth/refresh", "POST",
                JSONObject().put("refresh_token", session.getString("refresh_token")), null, null)
            currentCoroutineContext().ensureActive()
            session.put("access_token", pair.getString("access_token")).put("refresh_token", pair.getString("refresh_token"))
            store.save(session)
        } catch (cancelled: CancellationException) {
            store.clear()
            throw cancelled
        } catch (failure: Exception) {
            store.clear()
            if (failure is ApiFailure && failure.status == 401) throw failure
            throw ApiFailure(401, "AUTH_REFRESH_UNCONFIRMED", "登录更新结果未确认，请重新登录。")
        }
    }

    suspend fun call(path: String, method: String = "GET", body: JSONObject? = null, idempotent: Boolean = false, expectedVersion: Long? = null): JSONObject = withContext(Dispatchers.IO) {
        var session = store.load()
        val origin = ConnectionPolicy.origin(session.getString("origin"), debug)
        var key: String? = null
        if (idempotent) {
            val fingerprint = MessageDigest.getInstance("SHA-256").digest((method + path + body.toString()).toByteArray())
                .joinToString("") { "%02x".format(it) }
            require(!session.optBoolean("pending") || session.optString("pending_fingerprint") == fingerprint) {
                "上次请求的结果尚未确认，请先重试或刷新状态。"
            }
            key = if (session.optString("pending_fingerprint") == fingerprint) session.getString("pending_key") else UUID.randomUUID().toString()
            session.put("pending_fingerprint", fingerprint).put("pending_key", key).put("pending", true)
                .put("pending_path", path).put("pending_method", method).put("pending_body", body.toString())
            currentCoroutineContext().ensureActive()
            store.save(session)
        }
        val result = try {
            try {
                exchange(origin, path, method, body, session.getString("access_token"), key, expectedVersion?.toString())
            } catch (error: ApiFailure) {
                if (error.status != 401 || error.code != "AUTH_TOKEN_EXPIRED") throw error
                refreshSessionOrRequireLogin(origin, session)
                exchange(origin, path, method, body, session.getString("access_token"), key, expectedVersion?.toString())
            }
        } catch (error: ApiFailure) {
            if (error.status == 401) store.clear()
            else if (idempotent && error.status in 400..499 && error.status !in listOf(408, 429)) clearPending()
            throw error
        }
        currentCoroutineContext().ensureActive()
        if (idempotent) {
            clearPending()
        }
        result
    }
}
