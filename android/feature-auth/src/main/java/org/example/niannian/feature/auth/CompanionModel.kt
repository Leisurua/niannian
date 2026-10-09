package org.example.niannian.feature.auth

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import org.json.JSONArray
import org.json.JSONObject
import java.time.Instant

data class FamilyChoice(val id: String, val name: String, val role: String, val status: String)
data class Member(val id: String, val userId: String, val name: String, val role: String, val status: String, val version: Long, val permissions: List<String>)
data class Permission(val id: String, val scope: String, val status: String, val version: Long, val expiry: String)
data class CompanionState(
    val busy: Boolean = false, val loggedIn: Boolean = false, val address: String = "http://10.0.2.2:8000",
    val userId: String = "", val userName: String = "", val families: List<FamilyChoice> = emptyList(),
    val selected: FamilyChoice? = null, val creator: String = "", val members: List<Member> = emptyList(),
    val permissions: List<Permission> = emptyList(), val invite: String = "", val error: String = "",
    val message: String = "", val pendingWrite: Boolean = false, val offline: Boolean = false,
    val canManageMembers: Boolean = false
)

class CompanionModel(private val repository: FamilyRepository, val elder: Boolean, private val deviceId: String,
    private val taskScope: CoroutineScope? = null) : ViewModel() {
    private val current = MutableStateFlow(CompanionState())
    val state = current.asStateFlow()

    init { action {
        current.value = current.value.copy(address = repository.savedOrigin(), loggedIn = repository.hasSession())
        if (current.value.loggedIn) home()
    } }

    private fun action(work: suspend () -> Unit) {
        if (current.value.busy) return
        current.value = current.value.copy(busy = true, error = "", message = "")
        (taskScope ?: viewModelScope).launch {
            try { work() }
            catch (cancelled: CancellationException) { throw cancelled }
            catch (error: ApiFailure) {
                if (error.status == 401) current.value = CompanionState(address = current.value.address, error = "登录已失效，请重新登录。")
                else if (error.status == 403 || error.status == 404) current.value = current.value.copy(selected = null,
                    creator = "", members = emptyList(), permissions = emptyList(), invite = "", canManageMembers = false,
                    error = error.message.orEmpty())
                else current.value = current.value.copy(error = error.message.orEmpty())
            } catch (error: IllegalArgumentException) { current.value = current.value.copy(error = error.message ?: "请检查输入内容。") }
            catch (_: Exception) { current.value = current.value.copy(error = "连接或安全存储不可用，请检查网络和服务配置后重试。", offline = true) }
            finally { current.value = current.value.copy(busy = false, pendingWrite = runCatching { repository.hasPending() }.getOrDefault(false)) }
        }
    }

    fun login(address: String) = action {
        repository.login(address, elder, deviceId)
        current.value = CompanionState(busy = true, loggedIn = true, address = address)
        home()
    }

    private fun list(value: JSONArray): List<JSONObject> = (0 until value.length()).map { value.getJSONObject(it) }

    private suspend fun home(selectedId: String? = current.value.selected?.id) {
        val identity = repository.call("/v1/me")
        val me = identity.getJSONObject("user")
        val choices = repository.readAll("/v1/families?limit=100").map {
            FamilyChoice(it.getString("id"), it.getString("name"), it.getString("role"), it.getString("member_status"))
        }
        val selected = choices.find { it.id == selectedId } ?: choices.firstOrNull()
        current.value = current.value.copy(loggedIn = true, userId = me.getString("id"), userName = me.getString("display_name"),
            families = choices, selected = selected, members = emptyList(), permissions = emptyList(), creator = "", offline = false,
            invite = "", canManageMembers = false)
        if (selected?.status == "ACTIVE") {
            val family = repository.call("/v1/families/${selected.id}")
            val creator = family.getString("created_by_user_id")
            val membership = list(identity.getJSONArray("family_memberships")).find {
                it.getString("family_id") == selected.id && it.getString("status") == "ACTIVE"
            }
            val codes = membership?.optJSONArray("permission_codes") ?: JSONArray()
            val permissionCodes = (0 until codes.length()).map { codes.getString(it) }
            val admin = creator == me.getString("id") || "MEMBER_ADMIN" in permissionCodes
            val permissions = repository.readAll("/v1/consents?family_id=${selected.id}&limit=100")
                .filter { if (elder) it.getString("subject_user_id") == current.value.userId && it.getString("grantee_user_id") == creator else true }
                .groupBy { it.getString("subject_user_id") + it.getString("grantee_user_id") + it.getString("scope") }
                .values.map { rows -> rows.maxBy { it.getLong("version") } }
                .map { Permission(it.getString("id"), it.getString("scope"), it.getString("status"), it.getLong("version"), it.optString("expires_at", "")) }
            val members = if (!elder && (admin || "MEMBER_READ" in permissionCodes)) repository.readAll("/v1/families/${selected.id}/members?limit=100")
                .map { item -> val codes = item.getJSONArray("permission_codes")
                    Member(item.getString("id"), item.getString("user_id"), item.optString("display_name"), item.getString("role"),
                        item.getString("status"), item.getLong("version"), (0 until codes.length()).map { codes.getString(it) }) } else emptyList()
            current.value = current.value.copy(creator = creator, permissions = permissions, members = members, canManageMembers = admin)
        }
    }

    fun reload() = action { home() }
    fun choose(id: String) = action { current.value = current.value.copy(invite = ""); home(id) }
    fun createFamily(name: String) = action {
        require(name.isNotBlank()) { "请输入家庭称呼。" }
        val result = repository.call("/v1/families", "POST", JSONObject().put("name", name), true)
        current.value = current.value.copy(message = "家庭已创建。")
        home(result.getString("id"))
    }

    fun invite(role: String) = action {
        val family = current.value.selected ?: return@action
        val result = repository.call("/v1/families/${family.id}/invitations", "POST", JSONObject().put("target_role", role)
            .put("expires_at", Instant.now().plusSeconds(600).toString()).put("max_usage", 1), true)
        current.value = current.value.copy(invite = result.getString("token"), message = "邀请十分钟有效，仅供指定家人使用；不会自动授予任何数据权限。")
    }

    fun inspectInvitation(code: String) = action {
        val token = ConnectionPolicy.invitation(code)
        val member = repository.call("/v1/family-invitations/$token/accept", "POST", JSONObject())
        repository.saveInvitation(token, member.getString("family_id"))
        home(member.getString("family_id"))
        current.value = current.value.copy(message = "请与提供邀请码的家人核对身份、家庭名称和角色，再确认加入。")
    }

    fun confirmInvitation() = action {
        require(InvitationPolicy.canConfirm(current.value.selected?.id, current.value.selected?.status,
            repository.invitationFamily())) { "请重新读取当前家庭的邀请码，核对后再确认。" }
        val token = ConnectionPolicy.invitation(repository.pendingInvitation())
        val member = repository.call("/v1/family-invitations/$token/accept", "POST", JSONObject().put("confirm_identity", true))
        repository.saveInvitation("")
        home(member.getString("family_id"))
        current.value = current.value.copy(message = "已确认加入。各项授权默认关闭，由您逐项决定。")
    }

    fun grant(scope: String) = action {
        val snapshot = current.value
        val family = snapshot.selected ?: return@action
        require(elder && snapshot.creator.isNotEmpty() && snapshot.creator != snapshot.userId) { "请先加入家人创建的家庭。" }
        repository.call("/v1/consents", "POST", JSONObject().put("family_id", family.id).put("subject_user_id", snapshot.userId)
            .put("grantee_user_id", snapshot.creator).put("scope", scope).put("source", "SETTINGS"), true)
        home()
    }

    fun revoke(id: String) = action {
        require(elder) { "授权需由数据主体本人操作。" }
        repository.call("/v1/consents/$id/revoke", "POST", JSONObject(), true)
        home()
    }

    fun retry() = action {
        val retried = if (repository.hasPending()) repository.retryPending() else null
        val result = retried?.response
        val familyId = when {
            retried?.path == "/v1/families" -> result?.getString("id")
            result?.has("family_id") == true -> result.getString("family_id")
            else -> current.value.selected?.id
        }
        home(familyId)
        if (result?.has("token") == true && current.value.selected?.id == result.optString("family_id"))
            current.value = current.value.copy(invite = result.getString("token"))
    }

    fun revokeMember(member: Member) = action {
        val family = current.value.selected ?: return@action
        require(!elder && member.userId != current.value.userId) { "请使用本人退出操作。" }
        repository.call("/v1/families/${family.id}/members/${member.id}", "PATCH", JSONObject().put("status", "REVOKED"), expectedVersion = member.version)
        home()
    }

    fun allowMemberRead(member: Member) = action {
        val family = current.value.selected ?: return@action
        require(!elder) { "需要家庭管理权限。" }
        repository.call("/v1/families/${family.id}/members/${member.id}", "PATCH",
            JSONObject().put("permission_codes", JSONArray((member.permissions + "MEMBER_READ").distinct())), expectedVersion = member.version)
        home()
    }

    fun logout(allDevices: Boolean = false) = action {
        var reachedServer = false
        try { repository.call(if (allDevices) "/v1/auth/logout-all" else "/v1/auth/logout", "POST"); reachedServer = true }
        finally {
            repository.clear()
            current.value = CompanionState(busy = true, address = current.value.address,
                message = if (reachedServer) "已退出登录。" else "本机登录已清除；服务端及其他设备退出状态尚未确认。")
        }
    }
}
