package org.example.niannian.feature.conversation

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.drop
import kotlinx.coroutines.flow.collect
import java.time.Duration
import java.time.Instant

data class PortraitGrant(val id: String, val expiresAt: Instant?)
interface PortraitGateway { suspend fun grant(family: String, user: String): PortraitGrant? }
interface AvatarStore {
    val revision: StateFlow<Int>
    fun invalidate()
    suspend fun load(binding: String): ByteArray?
    suspend fun save(binding: String, bytes: ByteArray, expectedRevision: Int)
}
data class AvatarState(val family: String = "", val user: String = "", val grantId: String = "",
    val validUntil: Instant = Instant.EPOCH, val pack: AvatarPack? = null, val storageRevision: Int = -1,
    val busy: Boolean = false, val message: String = "", val packChecksum: String = "") {
    val allowed get() = grantId.isNotBlank() && validUntil.isAfter(Instant.now())
}

class AvatarModel(private val gateway: PortraitGateway, private val store: AvatarStore,
    private val scope: CoroutineScope? = null) : ViewModel() {
    private val tasks get() = scope ?: viewModelScope
    private val current = MutableStateFlow(AvatarState())
    val state = current.asStateFlow()
    val storageRevision = store.revision
    private var generation = 0
    private var importGeneration = 0
    private var polling: Job? = null
    private var importing: Job? = null
    private var expiry: Job? = null
    private val invalidations = tasks.launch {
        store.revision.drop(1).collect {
            importGeneration++; importing?.cancel()
            current.value = current.value.copy(pack = null, busy = false, storageRevision = -1)
        }
    }

    fun bind(family: String, user: String) {
        if (current.value.family == family && current.value.user == user && polling?.isActive == true) return
        hide()
        if (family.isBlank() || user.isBlank()) return
        current.value = AvatarState(family = family, user = user)
        val stamp = generation
        polling = tasks.launch {
            while (isActive) { refresh(stamp, family, user); delay(15000) }
        }
    }

    fun hide() {
        generation++; importGeneration++
        polling?.cancel(); importing?.cancel(); expiry?.cancel()
        current.value = AvatarState()
    }

    fun recheck(family: String, user: String) { hide(); bind(family, user) }

    private suspend fun refresh(stamp: Int, family: String, user: String) {
        val requestedAt = Instant.now()
        try {
            val grant = withTimeout(10000) { gateway.grant(family, user) }
            if (generation != stamp) return
            expiry?.cancel()
            if (grant == null || grant.expiresAt?.isAfter(Instant.now()) == false) {
                importing?.cancel(); importGeneration++
                store.invalidate()
                current.value = AvatarState(family = family, user = user,
                    message = "自定义形象需本人允许“数字人形象”授权，默认形象仍可使用。")
                return
            }
            val until = minOf(requestedAt.plusSeconds(30), grant.expiresAt ?: Instant.MAX)
            if (!until.isAfter(Instant.now())) throw IllegalStateException("Consent check expired")
            val binding = "$family:$user:${grant.id}"
            val storageStamp = store.revision.value
            var pack = current.value.pack.takeIf { current.value.grantId == grant.id }
            var checksum = current.value.packChecksum.takeIf { pack != null }.orEmpty()
            if (pack == null) {
                val bytes = store.load(binding)
                if (bytes != null) checksum = avatarChecksum(bytes)
                if (bytes != null) pack = try { withContext(Dispatchers.IO) { AvatarPack.parse(bytes) } }
                catch (_: IllegalArgumentException) { store.invalidate(); null }
            }
            if (generation != stamp) return
            if (storageStamp != store.revision.value) pack = null
            if (!until.isAfter(Instant.now())) throw IllegalStateException("Consent check expired")
            current.value = current.value.copy(grantId = grant.id, validUntil = until, pack = pack,
                packChecksum = if (pack == null) "" else checksum,
                storageRevision = store.revision.value,
                message = if (pack == null) "可导入用 Talking Head Anime 3 制作的角色包。" else current.value.message)
            expiry = tasks.launch {
                delay(Duration.between(Instant.now(), until).toMillis().coerceAtLeast(0))
                if (generation == stamp) {
                    importGeneration++; importing?.cancel()
                    current.value = current.value.copy(pack = null, grantId = "", busy = false,
                        message = "形象授权需要重新核对，暂时使用默认形象。")
                    if (grant.expiresAt?.isAfter(Instant.now()) == false) store.invalidate()
                }
            }
        } catch (cancelled: CancellationException) {
            if (cancelled !is TimeoutCancellationException) throw cancelled
            unavailable(stamp)
        } catch (_: Exception) { unavailable(stamp) }
    }

    private fun unavailable(stamp: Int) {
        if (stamp != generation) return
        expiry?.cancel(); importing?.cancel(); importGeneration++
        current.value = current.value.copy(pack = null, grantId = "", busy = false,
            message = "暂时无法核对形象授权，已恢复默认形象，请联网后重试。")
    }

    fun importPack(read: suspend () -> ByteArray): Job? {
        val snapshot = current.value
        if (!snapshot.allowed || snapshot.busy) return null
        val stamp = generation
        val importStamp = ++importGeneration
        val revision = store.revision.value
        current.value = snapshot.copy(busy = true, message = "正在读取角色包…")
        importing = tasks.launch {
            try {
                val grant = withTimeout(10000) { gateway.grant(snapshot.family, snapshot.user) }
                if (grant == null || grant.id != snapshot.grantId || grant.expiresAt?.isAfter(Instant.now()) == false) {
                    if (stamp == generation) { store.invalidate(); unavailable(stamp) }
                    return@launch
                }
                val bytes = withTimeout(15000) { withContext(Dispatchers.IO) { read() } }
                val pack = withContext(Dispatchers.IO) { AvatarPack.parse(bytes) }
                if (stamp != generation || importStamp != importGeneration || !current.value.allowed
                    || current.value.grantId != snapshot.grantId) return@launch
                store.save("${snapshot.family}:${snapshot.user}:${snapshot.grantId}", bytes, revision)
                if (stamp == generation && importStamp == importGeneration && current.value.allowed
                    && current.value.grantId == snapshot.grantId) {
                    current.value = current.value.copy(pack = pack, storageRevision = revision,
                        packChecksum = avatarChecksum(bytes),
                        message = "已启用本机自定义形象，仍由念念 AI 与您交流。")
                }
            } catch (cancelled: CancellationException) {
                if (cancelled !is TimeoutCancellationException) throw cancelled
                if (stamp == generation) current.value = current.value.copy(message = "读取角色包超时，请重试。")
            } catch (_: Exception) {
                if (stamp == generation) current.value = current.value.copy(message = "角色包无效或无法读取，请使用念念制作脚本重新导出。")
            } finally {
                if (stamp == generation && importStamp == importGeneration) current.value = current.value.copy(busy = false)
            }
        }
        return importing
    }

    fun remove() {
        importGeneration++; importing?.cancel(); store.invalidate()
        current.value = current.value.copy(pack = null, busy = false, message = "本机自定义形象已删除，已恢复默认形象。")
    }

    suspend fun activateGenerated(job: RemoteAvatar, bytes: ByteArray): Boolean {
        if (current.value.family != job.family || current.value.user != job.user) return false
        recheck(job.family, job.user)
        withTimeout(10000) { while (!current.value.allowed) delay(20) }
        if (current.value.grantId != job.grantId || current.value.family != job.family || current.value.user != job.user) return false
        val importing = importPack { bytes } ?: return false
        importing.join()
        return current.value.pack != null && current.value.packChecksum == job.checksum
    }
    override fun onCleared() { hide(); invalidations.cancel(); super.onCleared() }
}
