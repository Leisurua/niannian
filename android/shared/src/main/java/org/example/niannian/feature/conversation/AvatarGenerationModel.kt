package org.example.niannian.feature.conversation

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import org.example.niannian.data.ApiFailure
import org.json.JSONObject
import java.security.MessageDigest
import java.util.UUID

interface AvatarGenerationGateway {
    suspend fun call(path: String, method: String = "GET", body: JSONObject? = null, key: String? = null): JSONObject
    suspend fun grant(family: String, user: String): String
    suspend fun upload(url: String, headers: JSONObject, bytes: ByteArray)
    suspend fun download(id: String): ByteArray
}
data class RemoteAvatar(val id: String, val family: String, val user: String, val grantId: String,
    val status: String, val checksum: String, val error: String) {
    val label get() = when (status) {
        "UPLOADING" -> "等待照片上传"
        "QUEUED" -> "等待开始制作"
        "STYLIZING" -> "正在把照片转成动漫立绘"
        "PREPARING" -> "正在抠图并整理构图"
        "RENDERING" -> "正在制作表情和动作"
        "READY" -> "制作完成，请预览并确认"
        "ACTIVE" -> "已确认的陪伴形象"
        "FAILED" -> "制作未完成，请重新选择照片"
        else -> "任务已取消"
    }
}
data class AvatarGenerationState(val family: String = "", val user: String = "", val available: Boolean = false,
    val providerId: String = "", val providerLabel: String = "", val notice: String = "",
    val photo: ByteArray? = null, val job: RemoteAvatar? = null, val preview: AvatarPack? = null,
    val busy: Boolean = false, val message: String = "")

fun avatarChecksum(bytes: ByteArray) = MessageDigest.getInstance("SHA-256").digest(bytes).joinToString("") { "%02x".format(it) }

class AvatarGenerationModel(private val gateway: AvatarGenerationGateway,
    private val activate: suspend (RemoteAvatar, ByteArray) -> Boolean,
    private val removeLocal: (String) -> Unit, private val scope: CoroutineScope? = null) : ViewModel() {
    private val tasks get() = scope ?: viewModelScope
    private val current = MutableStateFlow(AvatarGenerationState())
    val state = current.asStateFlow()
    private var generation = 0
    private var operation = 0
    private var polling: Job? = null
    private var action: Job? = null
    private var candidate: ByteArray? = null

    fun bind(family: String, user: String) {
        if (current.value.family == family && current.value.user == user && polling?.isActive == true) return
        hide()
        if (family.isBlank() || user.isBlank()) return
        current.value = AvatarGenerationState(family = family, user = user)
        val stamp = generation
        polling = tasks.launch {
            while (isActive) { if (!current.value.busy) refresh(stamp); delay(3000) }
        }
    }
    fun hide() { generation++; polling?.cancel(); action?.cancel(); candidate = null; current.value = AvatarGenerationState() }

    private fun parse(value: JSONObject): RemoteAvatar {
        val snapshot = current.value
        require(value.getString("family_id") == snapshot.family && value.getString("owner_user_id") == snapshot.user)
        val id = value.getString("id"); UUID.fromString(id)
        val status = value.getString("status")
        require(status in listOf("UPLOADING", "QUEUED", "STYLIZING", "PREPARING", "RENDERING", "READY", "ACTIVE", "FAILED", "CANCELLED"))
        return RemoteAvatar(id, snapshot.family, snapshot.user, value.getString("consent_id"), status,
            if (value.isNull("pack_checksum")) "" else value.getString("pack_checksum"),
            if (value.isNull("error_code")) "" else value.getString("error_code"))
    }
    private suspend fun refresh(stamp: Int) {
        val requestOperation = operation
        fun valid() = stamp == generation && requestOperation == operation
        try {
            val caps = gateway.call("/v1/avatar-generation")
            if (!valid()) return
            current.value = current.value.copy(available = caps.getBoolean("available"),
                providerId = caps.getString("provider_id"), providerLabel = caps.getString("provider_label"), notice = caps.getString("notice"))
            val result = try { gateway.call("/v1/avatar-jobs/latest?family_id=${current.value.family}") }
            catch (error: ApiFailure) { if (error.status == 403) JSONObject().put("job", JSONObject.NULL) else throw error }
            if (!valid()) return
            if (result.isNull("job")) {
                candidate = null; current.value = current.value.copy(job = null, preview = null)
                return
            }
            val job = parse(result.getJSONObject("job"))
            val changed = current.value.job?.id != job.id || current.value.job?.checksum != job.checksum || job.status !in listOf("READY", "ACTIVE")
            current.value = current.value.copy(job = job, preview = if (changed) null else current.value.preview)
            if (changed) candidate = null
            if (job.status in listOf("READY", "ACTIVE") && candidate == null) {
                val bytes = gateway.download(job.id)
                if (!valid()) return
                require(avatarChecksum(bytes) == job.checksum)
                val preview = withContext(Dispatchers.IO) { AvatarPack.parse(bytes) }
                if (!valid()) return
                candidate = bytes
                current.value = current.value.copy(preview = preview, message = "请查看待机、倾听、思考和说话效果，满意后再确认启用。")
            }
        } catch (cancelled: CancellationException) { throw cancelled }
        catch (_: Exception) {
            if (valid()) { candidate = null; current.value = current.value.copy(photo = null, job = null, preview = null,
                available = false, message = "暂时无法读取制作状态或授权，请联网后重试；服务端任务不会自动重发。") }
        }
    }
    fun selectedPhoto(bytes: ByteArray) {
        if (!current.value.available || current.value.busy) return
        require(bytes.isNotEmpty() && bytes.size <= 5 * 1024 * 1024)
        current.value = current.value.copy(photo = bytes, message = "请确认照片及处理服务后授权制作。")
    }
    fun dismissPhoto() { current.value = current.value.copy(photo = null) }
    fun photoFailed() { current.value = current.value.copy(message = "照片无法读取，请选择清晰、单人的普通照片。") }

    fun create() {
        val snapshot = current.value
        val photo = snapshot.photo ?: return
        if (!snapshot.available || snapshot.busy || snapshot.job?.status in listOf("UPLOADING", "QUEUED", "STYLIZING", "PREPARING", "RENDERING")) return
        val stamp = generation
        operation++
        current.value = snapshot.copy(busy = true, photo = null, message = "正在授权并上传照片…")
        action = tasks.launch {
            try {
                val grant = gateway.grant(snapshot.family, snapshot.user)
                if (stamp != generation) return@launch
                val body = JSONObject().put("family_id", snapshot.family).put("consent_id", grant)
                    .put("provider_id", snapshot.providerId).put("authorized_photo", true)
                    .put("mime_type", "image/jpeg").put("size_bytes", photo.size).put("checksum", avatarChecksum(photo))
                val created = gateway.call("/v1/avatar-jobs", "POST", body, UUID.randomUUID().toString())
                if (stamp != generation) return@launch
                val job = parse(created)
                current.value = current.value.copy(job = job)
                gateway.upload(created.getString("upload_url"), created.getJSONObject("required_headers"), photo)
                if (stamp != generation) return@launch
                val queued = gateway.call("/v1/avatar-jobs/${job.id}/complete-upload", "POST", JSONObject(), UUID.randomUUID().toString())
                if (stamp == generation) current.value = current.value.copy(job = parse(queued), message = "照片已提交。可以离开页面，稍后回来查看制作结果。")
            } catch (cancelled: CancellationException) { throw cancelled }
            catch (_: Exception) { if (stamp == generation) current.value = current.value.copy(message = "上传结果未确认，请刷新查看；等待上传的任务可取消后重新选择照片。") }
            finally { if (stamp == generation) current.value = current.value.copy(busy = false) }
        }
    }

    fun confirm() {
        val snapshot = current.value; val job = snapshot.job ?: return; val bytes = candidate ?: return
        if (snapshot.busy || snapshot.preview == null) return
        val stamp = generation
        operation++
        current.value = snapshot.copy(busy = true, message = "正在确认并启用…")
        action = tasks.launch {
            try {
                val confirmed = gateway.call("/v1/avatar-jobs/${job.id}/confirm", "POST",
                    JSONObject().put("pack_checksum", job.checksum), UUID.randomUUID().toString())
                if (stamp != generation) return@launch
                val result = parse(confirmed)
                check(result.status == "ACTIVE" && result.checksum == job.checksum)
                check(activate(result, bytes))
                if (stamp == generation) current.value = current.value.copy(job = result, message = "已确认启用。念念 AI 将使用这个形象陪伴您。")
            } catch (cancelled: CancellationException) { throw cancelled }
            catch (_: Exception) { if (stamp == generation) current.value = current.value.copy(message = "启用结果未确认，请联网重新核对后再试。") }
            finally { if (stamp == generation) current.value = current.value.copy(busy = false) }
        }
    }

    fun cancel() {
        val job = current.value.job ?: return
        if (current.value.busy) return
        val stamp = generation
        operation++
        current.value = current.value.copy(busy = true)
        action = tasks.launch {
            try {
                gateway.call("/v1/avatar-jobs/${job.id}", "DELETE")
                if (stamp == generation) {
                    removeLocal(job.checksum); candidate = null
                    current.value = current.value.copy(job = null, preview = null, message = "任务已取消，服务端照片与角色资源将清理。")
                }
            } catch (cancelled: CancellationException) { throw cancelled }
            catch (_: Exception) { if (stamp == generation) current.value = current.value.copy(message = "取消未确认，请刷新后重试。") }
            finally { if (stamp == generation) current.value = current.value.copy(busy = false) }
        }
    }
    override fun onCleared() { hide(); super.onCleared() }
}
