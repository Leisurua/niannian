package org.example.niannian.feature.memory

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.security.MessageDigest

interface MemoryGateway {
    suspend fun call(path: String, method: String = "GET", body: JSONObject? = null,
        idempotent: Boolean = false, version: Long? = null): JSONObject
    suspend fun list(path: String): List<JSONObject>
    suspend fun upload(url: String, headers: JSONObject, bytes: ByteArray)
    suspend fun download(url: String): ByteArray
    suspend fun retry()
    fun hasPending(): Boolean
}

class MemoryFailure(message: String) : Exception(message)

data class MemoryItem(val id: String, val title: String, val content: String, val status: String, val version: Long,
    val subject: String, val attachments: List<String>)
data class MemoryState(val familyId: String = "", val userId: String = "", val busy: Boolean = false,
    val pending: Boolean = false, val items: List<MemoryItem> = emptyList(), val selected: MemoryItem? = null,
    val error: String = "", val message: String = "", val photo: ByteArray? = null, val candidates: Boolean = false)

class MemoryModel(private val gateway: MemoryGateway, private val taskScope: CoroutineScope? = null) : ViewModel() {
    private val current = MutableStateFlow(MemoryState())
    val state = current.asStateFlow()
    private var generation = 0
    private var job: Job? = null

    fun clear() {
        generation++
        job?.cancel()
        current.value = MemoryState()
    }

    suspend fun awaitIdle() { job?.join() }

    fun bind(familyId: String, userId: String): Job? {
        if (current.value.familyId == familyId && current.value.userId == userId) return null
        clear()
        current.value = MemoryState(familyId = familyId, userId = userId)
        return refresh()
    }

    private fun action(work: suspend (Int) -> Unit): Job? {
        if (current.value.busy || current.value.familyId.isBlank()) return null
        val stamp = generation
        current.value = current.value.copy(busy = true, error = "", message = "", photo = null)
        job = (taskScope ?: viewModelScope).launch {
            try { work(stamp) }
            catch (cancelled: CancellationException) { throw cancelled }
            catch (failure: Exception) {
                if (stamp == generation) current.value = current.value.copy(items = emptyList(), selected = null, photo = null,
                    error = if (failure is MemoryFailure || failure is IllegalArgumentException) failure.message?.take(160).orEmpty()
                        else "暂时无法读取，请检查连接或授权后重试。")
            } finally {
                if (stamp == generation) current.value = current.value.copy(busy = false, pending = gateway.hasPending())
            }
        }
        return job
    }

    private fun item(value: JSONObject): MemoryItem {
        val photos = value.optJSONArray("attachments")
        return MemoryItem(value.getString("id"), value.getString("title"), value.getString("content"),
            value.getString("verification_status"), value.getLong("version"), value.getString("subject_user_id"),
            (0 until (photos?.length() ?: 0)).map { photos!!.getJSONObject(it).getString("id") })
    }

    private suspend fun load(stamp: Int) {
        val snapshot = current.value
        val suffix = if (snapshot.candidates) "&pending_confirmation=true" else ""
        val rows = gateway.list("/v1/memories?family_id=${snapshot.familyId}&limit=100$suffix").map(::item)
        if (stamp == generation) current.value = current.value.copy(items = rows, selected = null, photo = null)
    }

    fun refresh() = action { load(it) }
    fun showCandidates(value: Boolean): Job? {
        if (current.value.busy) return null
        current.value = current.value.copy(candidates = value)
        return refresh()
    }
    fun detail(id: String) = action { stamp ->
        val result = item(gateway.call("/v1/memories/$id"))
        if (stamp == generation) current.value = current.value.copy(selected = result)
    }
    fun create(subject: String, title: String, content: String) = action { stamp ->
        require(subject.isNotBlank() && title.isNotBlank() && content.isNotBlank()) { "请选择长辈并填写标题和内容。" }
        gateway.call("/v1/memories", "POST", JSONObject().put("family_id", current.value.familyId)
            .put("subject_user_id", subject).put("type", "EVENT").put("title", title).put("content", content)
            .put("required_consent_scope", "FAMILY_MEMORY").put("verification_status", "PENDING"), true)
        if (stamp == generation) {
            current.value = current.value.copy(candidates = true)
            load(stamp)
            current.value = current.value.copy(message = "已保存为待确认候选，尚未作为家庭事实使用。")
        }
    }
    fun edit(id: String, version: Long, title: String, content: String) = action { stamp ->
        gateway.call("/v1/memories/$id", "PATCH", JSONObject().put("title", title).put("content", content), version = version)
        load(stamp)
        if (stamp == generation) current.value = current.value.copy(message = "修改已保存，请到待确认列表重新确认。")
    }
    fun transition(id: String, command: String) = action { stamp ->
        require(command in listOf("confirm", "reject", "revoke"))
        gateway.call("/v1/memories/$id/$command", "POST", JSONObject(), true)
        load(stamp)
    }
    fun delete(id: String) = action { stamp ->
        gateway.call("/v1/memories/$id", "DELETE", JSONObject(), true)
        load(stamp)
    }
    fun feedback(id: String) = action { stamp ->
        gateway.call("/v1/memories/$id/feedback", "POST", JSONObject().put("kind", "INCORRECT"), true)
        if (stamp == generation) current.value = current.value.copy(message = "已记录内容有误反馈，原事实未被自动修改。")
    }
    fun retry() = action { stamp -> gateway.retry(); load(stamp) }

    // GetContent stops the Activity. Restore only this panel's scope, then
    // re-read the target through the authorized API before handling its result.
    suspend fun resumePhotoSelection(familyId: String, userId: String, id: String,
        mime: String?, readBytes: () -> ByteArray) {
        val snapshot = current.value
        if (snapshot.familyId.isNotBlank() &&
            (snapshot.familyId != familyId || snapshot.userId != userId)) return
        bind(familyId, userId)
        awaitIdle()
        if (current.value.familyId != familyId || current.value.userId != userId ||
            current.value.error.isNotEmpty() || current.value.pending) return
        detail(id)?.join()
        if (current.value.familyId != familyId || current.value.userId != userId ||
            current.value.selected?.id != id || current.value.error.isNotEmpty()) return
        if (mime != null) uploadPhoto(id, mime, readBytes)?.join()
    }

    fun uploadPhoto(id: String, mime: String, readBytes: () -> ByteArray) = action { stamp ->
        val bytes = withContext(Dispatchers.IO) { readBytes() }
        require(bytes.isNotEmpty() && bytes.size <= 5 * 1024 * 1024) { "照片需小于 5 MB。" }
        require(mime in listOf("image/jpeg", "image/png", "image/webp")) { "请选择 JPG、PNG 或 WebP 照片。" }
        val checksum = MessageDigest.getInstance("SHA-256").digest(bytes).joinToString("") { "%02x".format(it) }
        val request = gateway.call("/v1/files/upload-requests", "POST", JSONObject().put("memory_id", id)
            .put("media_type", "PHOTO").put("mime_type", mime).put("size_bytes", bytes.size).put("checksum", checksum))
        gateway.upload(request.getString("upload_url"), request.getJSONObject("required_headers"), bytes)
        val fileId = request.getJSONObject("file").getString("id")
        val confirmed = gateway.call("/v1/files/$fileId/confirm", "POST", JSONObject().put("checksum", checksum), true)
        require(confirmed.getString("status") == "AVAILABLE") { "照片未通过内容检查，已隔离；请换一张照片。" }
        val result = item(gateway.call("/v1/memories/$id"))
        if (stamp == generation) current.value = current.value.copy(selected = result, message = "照片已检查并去除附加元数据。")
    }
    fun photo(id: String) = action { stamp ->
        val signed = gateway.call("/v1/files/$id/download-url")
        val bytes = gateway.download(signed.getString("download_url"))
        if (stamp == generation) current.value = current.value.copy(photo = bytes)
    }
}
