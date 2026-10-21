package org.example.niannian.feature.family

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Card
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.activity.compose.BackHandler
import org.example.niannian.feature.reminder.ReminderModel
import org.example.niannian.feature.memory.MemoryModel
import org.example.niannian.feature.conversation.ConversationModel
import org.example.niannian.feature.conversation.ConversationToolsModel
import org.example.niannian.feature.notification.NotificationModel

private val scopeLabels = linkedMapOf("VOICE" to "语音处理", "PORTRAIT" to "数字人形象", "FAMILY_MEMORY" to "家庭记忆",
    "HEALTH_MEDICATION" to "健康与用药信息", "CONVERSATION_SUMMARY" to "交流摘要", "CAMERA_PROXIMITY" to "摄像头存在检测",
    "NOTIFICATION_TO_FAMILY" to "向家人发送关注提示")

private data class ConsentChange(val familyId: String, val scope: String, val revokeId: String? = null, val self: Boolean = false)

@Composable
fun CompanionScreen(model: CompanionModel, environmentLabel: String,
    reminders: ReminderModel, memories: MemoryModel, tools: ConversationToolsModel,
    conversation: ConversationModel? = null, notifications: NotificationModel? = null,
    onNotifications: () -> Unit = {}, offlineContent: @Composable () -> Unit = {}) {
    val state by model.state.collectAsState()
    val mutationUnavailable = state.busy || state.offline || state.pendingWrite
    var address by remember(state.address) { mutableStateOf(state.address) }
    var familyName by remember { mutableStateOf("") }
    var invitation by remember { mutableStateOf("") }
    var revokeMember by remember { mutableStateOf<Member?>(null) }
    var consentChange by remember { mutableStateOf<ConsentChange?>(null) }
    var showFamilySettings by remember { mutableStateOf(false) }
    val homeModels = remember(reminders, memories, tools, conversation, notifications) {
        HomeModels(reminders, memories, tools, conversation, notifications, onNotifications)
    }
    BackHandler(enabled = showFamilySettings) { showFamilySettings = false }
    if (!showFamilySettings) {
        HomeTheme {
            if (model.elder) {
                ElderDesignHome(
                    state = state,
                    model = model,
                    models = homeModels,
                    offlineContent = offlineContent,
                    onOpenFamilySettings = { showFamilySettings = true }
                )
            } else {
                FamilyDesignHome(
                    state = state,
                    model = model,
                    models = homeModels,
                    onOpenFamilySettings = { showFamilySettings = true }
                )
            }
        }
        return
    }
    HomeTheme {
        consentChange?.let { target ->
            val label = scopeLabels[target.scope] ?: target.scope
            val revoking = target.revokeId != null
            AlertDialog(onDismissRequest = { consentChange = null },
                title = { Text(if (revoking) "撤回$label" else "允许$label") },
                text = { Text(if (target.self && target.scope == "CONVERSATION_SUMMARY")
                    if (revoking) "停止生成并隐藏已有会话回顾，随后清理；基础聊天仍可用。"
                    else "允许生成我的会话回顾。仅保存脱敏主题，最长 24 小时；不保存逐字稿。分享给家人和通知分别授权。"
                    else if (target.self && target.scope == "VOICE")
                    if (revoking) "停止设备语音识别和朗读，您仍可打字聊天。"
                    else "允许点击说话和朗读回复。设备语音服务可能联网处理声音和朗读内容；应用不保存录音。此项不授予家属权限，可随时撤回。"
                    else if (target.self) if (revoking) "撤回后，念念将不能在您的交流中继续引用这项记忆，基础聊天仍可用。"
                    else "允许在您与念念的交流中引用已确认的${label}。此项不会授权家人查看，不会开启通知；有效至您撤回，您随时可以关闭。"
                    else if (revoking) "撤回后，当前家庭创建者不能继续使用这项授权。其他授权保持原设置，授权历史会保留。"
                    else "这会向当前家庭创建者授予“$label”权限。只有这一项会开启，您随时可以撤回。") },
                confirmButton = { Button(enabled = !mutationUnavailable && state.selected?.id == target.familyId,
                    onClick = {
                        if (target.revokeId != null) model.revoke(target.revokeId) else if (target.self) model.grantSelf(target.scope) else model.grant(target.scope)
                        consentChange = null
                    }) { Text(if (revoking) "确认撤回" else "确认允许") } },
                dismissButton = { OutlinedButton(onClick = { consentChange = null }) { Text("取消") } })
        }
        revokeMember?.let { target ->
            AlertDialog(onDismissRequest = { revokeMember = null }, title = { Text("撤销成员资格") },
                text = { Text("确认撤销${target.name}在当前家庭的访问资格？此操作不会删除授权历史。") },
                confirmButton = { Button(onClick = { model.revokeMember(target); revokeMember = null }) { Text("确认撤销") } },
                dismissButton = { OutlinedButton(onClick = { revokeMember = null }) { Text("取消") } })
        }
        Column(Modifier.fillMaxSize().safeDrawingPadding().verticalScroll(rememberScrollState()).padding(24.dp), verticalArrangement = Arrangement.spacedBy(16.dp)) {
            OutlinedButton(onClick = { showFamilySettings = false }, modifier = Modifier.fillMaxWidth().heightIn(min = 52.dp)) {
                Text(if (model.elder) "← 返回「念念 · 今日」首页" else "← 返回「念念 · 子女端」首页", fontSize = 18.sp)
            }
            Text("家庭与授权设置", fontSize = 28.sp)
            Text(environmentLabel, color = MaterialTheme.colorScheme.primary)
            Text("念念是 AI 陪伴助手，不是真实家人。此版本使用虚构 DEMO 账户，不提供诊断、真实通话或已经送达的承诺。", fontSize = 18.sp)
            if (state.busy) CircularProgressIndicator()
            if (state.error.isNotEmpty()) {
                Text(state.error, color = MaterialTheme.colorScheme.error, fontSize = 18.sp)
                if (state.offline && state.loggedIn) Text("以下为本次已加载信息，当前状态尚未重新确认。")
                if (!state.pendingWrite && state.loggedIn) Action("重新读取", state.busy) { model.reload() }
            }
            if (state.pendingWrite) {
                Text("上次操作的结果尚未确认，请先重试。", fontSize = 18.sp)
                Action("重试上次请求（防止重复提交）", state.busy) { model.retry() }
            }
            if (state.message.isNotEmpty()) Text(state.message, fontSize = 18.sp)
            if (!state.loggedIn) {
                OutlinedTextField(address, { address = it }, label = { Text("服务地址") }, modifier = Modifier.fillMaxWidth(), singleLine = true, enabled = !state.busy)
                Action(if (model.elder) "⚡ 一键真机 USB 登录 (127.0.0.1:8000)" else "⚡ 一键真机 USB 登录 (127.0.0.1:8000)", state.busy) {
                    address = "http://127.0.0.1:8000"
                    model.login("http://127.0.0.1:8000")
                }
                Action(if (model.elder) "以演示长辈登录" else "以演示家人登录", state.busy) { model.login(address) }
            } else {
                if (model.elder && state.offline && state.selected == null) offlineContent()
                Text("您好，${state.userName}", fontSize = 22.sp)
                Text("请选择家庭", fontSize = 20.sp)
                if (state.families.isEmpty()) Text("还没有家庭。家人可先创建家庭，再邀请长辈。")
                state.families.forEach { family ->
                    OutlinedButton(onClick = { model.choose(family.id) }, enabled = !state.busy,
                        modifier = Modifier.fillMaxWidth().heightIn(min = 56.dp)) {
                        Text(family.name + if (family.status == "PENDING") " · 待本人确认" else " · 已加入", fontSize = 18.sp)
                    }
                }
                if (!model.elder) {
                    OutlinedTextField(familyName, { familyName = it }, label = { Text("新家庭称呼") }, modifier = Modifier.fillMaxWidth(), enabled = !state.busy)
                    Action("创建家庭", mutationUnavailable) { model.createFamily(familyName) }
                }
                OutlinedTextField(invitation, { invitation = it }, label = { Text("家人提供的邀请码") }, modifier = Modifier.fillMaxWidth(), enabled = !state.busy)
                Action("读取邀请并核对", mutationUnavailable) { model.inspectInvitation(invitation) }
                val selected = state.selected
                if (selected?.status == "PENDING") {
                    Text("待确认家庭：${selected.name}；角色：${roleLabel(selected.role)}", fontSize = 20.sp)
                    Text("请先向提供邀请码的家人核对身份；确认加入不等于开启数据授权。")
                    Action("我已核对身份，确认加入", mutationUnavailable) { model.confirmInvitation() }
                }
                if (selected?.status == "ACTIVE") {
                    Text(selected.name, fontSize = 24.sp)
                    Text(if (model.elder) "今日 · 家庭已连接" else "家庭动态 · 已连接", fontSize = 20.sp)
                    Text(if (model.elder) "家庭记忆、语音/文字聊天和提醒已开放。" else "家庭记忆与提醒已开放。")
                    if (!model.elder) {
                        if (state.canManageMembers) Action("生成长辈邀请码", mutationUnavailable) { model.invite("ELDER") }
                        if (state.invite.isNotEmpty()) SelectionContainer { Text(state.invite, fontSize = 18.sp) }
                        state.members.forEach { member ->
                            Text("${member.name.ifEmpty { "历史成员" }} · ${roleLabel(member.role)} · ${statusLabel(member.status)}")
                            if (state.canManageMembers && member.userId != state.userId && member.status in listOf("PENDING", "ACTIVE")) {
                                Action("撤销${member.name}的成员资格", mutationUnavailable) { revokeMember = member }
                                if (member.status == "ACTIVE" && "MEMBER_READ" !in member.permissions)
                                    Action("允许${member.name}查看家庭成员", mutationUnavailable) { model.allowMemberRead(member) }
                            }
                        }
                        Text("长辈授权状态（仅本人可修改）", fontSize = 20.sp)
                        state.permissions.forEach { Text("${scopeLabels[it.scope] ?: it.scope}：${permissionLabel(it)}") }
                        if (state.permissions.isEmpty()) Text("尚未收到分项授权。")
                    } else {
                        Text("用于我与念念的交流", fontSize = 22.sp)
                        Text("默认关闭；拒绝不影响基础聊天，与分享给家人的授权分别设置。")
                        listOf("VOICE", "FAMILY_MEMORY", "HEALTH_MEDICATION", "CONVERSATION_SUMMARY").forEach { scope ->
                            val permission = state.selfPermissions.find { it.scope == scope }
                            val granted = permission?.let { permissionLabel(it) == "已授权" } == true
                            Text("${scopeLabels[scope]}：${permission?.let(::permissionLabel) ?: "未授权"}")
                            Action(if (scope == "CONVERSATION_SUMMARY") if (granted) "停止生成我的会话回顾" else "允许生成我的会话回顾"
                                else if (granted) "停止在交流中使用${scopeLabels[scope]}" else "允许在交流中使用${scopeLabels[scope]}", mutationUnavailable) {
                                consentChange = ConsentChange(selected.id, scope, if (granted) permission!!.id else null, self = true)
                            }
                        }
                        Text("我的授权 · 授予当前家庭创建者", fontSize = 22.sp)
                        Text("默认全部关闭，每项由您主动决定，可随时撤回。")
                        scopeLabels.forEach { (scope, label) ->
                            val permission = state.permissions.find { it.scope == scope }
                            Card(Modifier.fillMaxWidth()) {
                                Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                                    Text(label, fontSize = 20.sp)
                                    Text(permission?.let { permissionLabel(it) } ?: "未授权")
                                    if (permission != null && permissionLabel(permission) == "已授权")
                                        Action("撤回$label", mutationUnavailable) { consentChange = ConsentChange(selected.id, scope, permission.id) }
                                    else Action("允许$label", mutationUnavailable) { consentChange = ConsentChange(selected.id, scope) }
                                }
                            }
                        }
                    }
                }
                Action("刷新当前状态", state.busy) { model.reload() }
                Action("退出本机", state.busy) { model.logout() }
                Action("退出本账号所有设备", state.busy) { model.logout(true) }
                Text("语音依赖设备服务，真机效果待验证；摄像头、BLE、电话和 kiosk 尚未启用。")
            }
        }
    }
}

@Composable private fun Action(label: String, busy: Boolean, action: () -> Unit) {
    Button(onClick = action, enabled = !busy, modifier = Modifier.fillMaxWidth().heightIn(min = 56.dp)) { Text(label, fontSize = 18.sp) }
}

private fun roleLabel(role: String) = when (role) { "ELDER" -> "长辈"; "CHILD" -> "子女"; "CAREGIVER" -> "照护人"; "EMERGENCY_CONTACT" -> "紧急联系人"; else -> "未知角色" }
private fun statusLabel(status: String) = when (status) { "ACTIVE" -> "已加入"; "PENDING" -> "待确认"; "LEFT" -> "已离开"; "REVOKED" -> "已撤销"; else -> "未知状态" }
private fun permissionLabel(permission: Permission): String {
    if (permission.status == "REVOKED") return "已撤回"
    if (permission.status == "EXPIRED" || permission.status == "GRANTED" && !homeConsentGranted(permission)) return "已过期"
    return if (homeConsentGranted(permission)) "已授权" else "未授权"
}
