package org.example.niannian.feature.voice

import androidx.compose.runtime.staticCompositionLocalOf
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import org.example.niannian.data.FamilyRepository
import org.json.JSONObject

data class FamilyVoice(val id: String, val owner: String, val name: String, val status: String, val version: Int)
data class VoiceProfilesState(val family: String = "", val user: String = "", val busy: Boolean = false,
    val voices: List<FamilyVoice> = emptyList(), val selected: String? = null,
    val cloudAllowed: Boolean = false, val message: String = "", val available: Boolean = false)
val LocalVoiceProfiles = staticCompositionLocalOf<VoiceProfilesModel?> { null }

class VoiceProfilesModel(private val repository: FamilyRepository, private val scope: CoroutineScope) {
    private val current = MutableStateFlow(VoiceProfilesState())
    val state = current.asStateFlow()
    private var generation = 0
    private var task: Job? = null
    fun bind(family: String, user: String, elder: Boolean) {
        if (current.value.family == family && current.value.user == user) return
        generation++; task?.cancel(); current.value = VoiceProfilesState(family = family, user = user)
        if (family.isNotBlank()) refresh(elder)
    }
    private fun action(work: suspend (Int) -> Unit) {
        if (current.value.busy || current.value.family.isBlank()) return
        val stamp = generation
        current.value = current.value.copy(busy = true, message = "")
        task = scope.launch {
            try { work(stamp) }
            catch (e: CancellationException) { throw e }
            catch (_: Exception) { if (stamp == generation) current.value = current.value.copy(message = "声音操作未完成，请刷新并检查连接、授权与服务配置。") }
            finally { if (stamp == generation) current.value = current.value.copy(busy = false) }
        }
    }
    private suspend fun load(elder: Boolean, stamp: Int) {
        val family = current.value.family
        val result = repository.call("/v1/voice-profiles?family_id=$family&available=$elder")
        val items = result.getJSONArray("items")
        val rows = (0 until items.length()).map { items.getJSONObject(it) }.map {
            FamilyVoice(it.getString("id"), it.getString("owner_user_id"), it.getString("display_name"), it.getString("status"), it.optInt("version", 1))
        }
        val preference = if (elder) repository.call("/v1/voice-preferences?family_id=$family") else JSONObject()
        if (stamp == generation) current.value = current.value.copy(voices = rows,
            selected = preference.optString("voice_profile_id").takeUnless { it.isBlank() || it == "null" },
            cloudAllowed = preference.optBoolean("cloud_tts_allowed"), available = result.optBoolean("available", true))
    }
    fun refresh(elder: Boolean) = action { load(elder, it) }
    fun upload(owner: String, name: String, audio: ByteArray) = action { stamp ->
        val created = repository.call("/v1/voice-profiles", "POST", JSONObject()
            .put("family_id", current.value.family).put("owner_user_id", owner).put("display_name", name))
        repository.uploadVoice(created.getString("id"), audio)
        load(false, stamp)
    }
    fun command(row: FamilyVoice, command: String) = action { stamp ->
        require(command in listOf("approve", "activate", "delete"))
        repository.call("/v1/voice-profiles/${row.id}" + if (command == "delete") "" else "/$command",
            if (command == "delete") "DELETE" else "POST", if (command == "delete") null else JSONObject())
        load(false, stamp)
    }
    suspend fun audio(row: FamilyVoice, original: Boolean) = repository.voiceAudio(row.id, if (original) "sample" else "preview")
    fun select(id: String?, allowed: Boolean, selected: () -> Unit = {}) = action { stamp ->
        repository.call("/v1/voice-preferences", "PUT", JSONObject().put("family_id", current.value.family)
            .put("voice_profile_id", id ?: JSONObject.NULL).put("cloud_tts_allowed", allowed))
        if (stamp == generation) { current.value = current.value.copy(selected = id, cloudAllowed = allowed); selected() }
    }
}
