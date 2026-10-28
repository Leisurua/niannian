package org.example.niannian.feature.family

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.compose.LocalLifecycleOwner
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import org.example.niannian.core.common.parseApiInstant
import org.example.niannian.feature.conversation.*
import org.example.niannian.feature.memory.*
import org.example.niannian.feature.notification.*
import org.example.niannian.feature.message.*
import org.example.niannian.feature.reminder.*
import java.time.Instant
import java.time.LocalDate
import java.time.LocalTime
import java.time.ZoneId
import java.time.ZonedDateTime

internal enum class HomeFeature(val title: String) {
    REMINDERS("生活提醒"), MEMORIES("家庭记忆"), CHAT("和念念聊聊"),
    CONVERSATION("主动陪伴与交流回顾"), NOTIFICATIONS("家人通知"), MESSAGES("家人留言"), REPORTS("统计与周报")
}

internal class HomeModels(
    val reminders: ReminderModel,
    val memories: MemoryModel,
    val tools: ConversationToolsModel,
    val conversation: ConversationModel? = null,
    val notifications: NotificationModel? = null,
    val onNotifications: () -> Unit = {},
    val messages: MessageModel? = null,
    val notificationSettings: @Composable () -> Unit = {}
)

internal fun homeFamily(state: CompanionState): String =
    state.selected?.takeIf { state.loggedIn && it.status == "ACTIVE" }?.id.orEmpty()

internal fun homeConnectionLabel(state: CompanionState): String = when {
    !state.loggedIn -> "尚未登录"
    state.busy -> "正在核对连接…"
    state.offline -> "当前离线 · 等待重新连接"
    state.error.isNotBlank() -> "连接或权限需要重新确认"
    state.selected == null -> "尚未选择家庭"
    state.selected.status != "ACTIVE" -> "等待本人确认加入"
    else -> "已连接 · ${state.selected.name}"
}

internal fun homeConnectionStatus(state: CompanionState): String =
    if (state.loggedIn && !state.busy && !state.offline && state.error.isBlank() && homeFamily(state).isNotBlank())
        "🟢 已联机：${state.userName} · 家庭：${state.selected?.name}"
    else homeConnectionLabel(state)

internal fun homeFamilyReminderRows(state: CompanionState, reminders: ReminderState, subject: String,
    now: Instant = Instant.now()): List<FamilyReminderRow> {
    if (state.offline || state.error.isNotBlank() || reminders.offline || homeFamily(state).isBlank() ||
        reminders.family != homeFamily(state) || reminders.user != state.userId || subject.isBlank()) return emptyList()
    return reminders.rules.filter { it.optBoolean("active", true) && it.optString("owner_user_id") == subject }.map { rule ->
        val zone = ZoneId.of(rule.getString("timezone"))
        val day = if (rule.getString("recurrence_kind") == "ONCE") LocalDate.parse(rule.getString("start_date"))
            else now.atZone(zone).toLocalDate()
        val scheduled = day.atTime(LocalTime.parse(rule.getString("schedule_time_local"))).atZone(zone).toInstant()
        val executions = rule.optJSONArray("executions")
        val execution = (0 until (executions?.length() ?: 0)).map { executions!!.getJSONObject(it) }
            .firstOrNull { parseApiInstant(it.getString("scheduled_at")) == scheduled }
        FamilyReminderRow(rule.getString("id"), rule.getString("schedule_time_local").take(5),
            rule.getString("title"), rule.getString("content"), execution?.optString("feedback_status") == "DONE",
            isMedication = rule.getString("type") == "MEDICATION")
    }.sortedBy { it.time }.let { rows ->
        val next = rows.firstOrNull { !it.done }?.id
        rows.map { it.copy(isNext = it.id == next) }
    }
}

internal fun homeCurrentReminderCards(state: CompanionState, reminders: ReminderState,
    now: Instant = Instant.now()): List<ReminderCard> = homeReminderCards(state, reminders)
    .groupBy { it.reminderId }.values.map { cards ->
        val today = cards.filter {
            val time = ZonedDateTime.parse(it.time)
            time.toLocalDate() == now.atZone(time.zone).toLocalDate()
        }
        today.firstOrNull() ?: cards.filter { ZonedDateTime.parse(it.time).toInstant() > now }
            .minByOrNull { ZonedDateTime.parse(it.time).toInstant() }
            ?: cards.maxBy { ZonedDateTime.parse(it.time).toInstant() }
    }.sortedBy { ZonedDateTime.parse(it.time).toInstant() }

internal fun homeConsentGranted(value: Permission, now: Instant = Instant.now()): Boolean =
    value.status == "GRANTED" && (value.expiry.isBlank() ||
        runCatching { parseApiInstant(value.expiry).isAfter(now) }.getOrDefault(false))

internal fun homeReminderCards(state: CompanionState, reminders: ReminderState): List<ReminderCard> =
    if (homeFamily(state).isNotBlank() && reminders.family == homeFamily(state) && reminders.user == state.userId)
        reminders.cards else emptyList()

internal fun homeMemoryItems(state: CompanionState, memories: MemoryState): List<MemoryItem> =
    if (!state.offline && state.error.isBlank() && memories.error.isBlank() && homeFamily(state).isNotBlank() &&
        memories.familyId == homeFamily(state) && memories.userId == state.userId) memories.items else emptyList()

internal fun homeSubjects(state: CompanionState, elder: Boolean): List<Pair<String, String>> =
    if (homeFamily(state).isBlank()) emptyList() else if (elder) listOf(state.userId to state.userName)
    else state.members.filter { it.role == "ELDER" && it.status == "ACTIVE" }.map { it.userId to it.name }

// The home and its feature sheets share the Activity's existing models. Stopping the
// Activity hides private content; an account/family change cannot render old scopes.
@Composable
internal fun BindHomeModels(state: CompanionState, account: CompanionModel, models: HomeModels,
    subject: String, feature: HomeFeature?) {
    val owner = LocalLifecycleOwner.current
    var foreground by remember(owner) { mutableStateOf(owner.lifecycle.currentState.isAtLeast(Lifecycle.State.STARTED)) }
    var checkedAuthorization by remember(models) { mutableStateOf<String?>(null) }
    fun clear() {
        models.reminders.hide(); models.memories.clear(); models.conversation?.clear()
        models.tools.clear(); models.notifications?.clear(); models.messages?.clear()
    }
    DisposableEffect(owner, models) {
        val observer = LifecycleEventObserver { _, event ->
            if (event == Lifecycle.Event.ON_STOP) { foreground = false; clear() }
            if (event == Lifecycle.Event.ON_START) { foreground = true; account.reload() }
        }
        owner.lifecycle.addObserver(observer)
        onDispose { owner.lifecycle.removeObserver(observer); clear() }
    }
    val family = homeFamily(state)
    val chat = models.conversation?.state?.collectAsState()?.value
    LaunchedEffect(foreground, family, state.userId, chat?.reminderRevision) {
        if (foreground && family.isNotBlank() && chat?.family == family && chat.user == state.userId &&
            chat.reminderRevision > 0 && !state.offline && state.error.isBlank()) models.reminders.refresh()
    }
    val authorization = state.permissions.toString() + state.selfPermissions.toString() + state.members.toString()
    LaunchedEffect(foreground, family, state.userId, state.busy, state.offline, state.error, subject, feature, authorization) {
        if (!foreground || family.isBlank()) { clear(); return@LaunchedEffect }
        if (state.busy) return@LaunchedEffect
        models.reminders.bind(family, state.userId)
        if (state.offline || state.error.isNotBlank()) {
            models.memories.clear(); models.conversation?.clear(); models.tools.clear(); models.notifications?.clear(); models.messages?.clear()
            return@LaunchedEffect
        }
        if (checkedAuthorization != authorization) {
            models.memories.clear(); models.conversation?.clear(); models.tools.clear(); models.notifications?.clear(); models.messages?.clear()
            checkedAuthorization = authorization
        }
        models.memories.bind(family, state.userId)
        models.messages?.bind(family, state.userId)
        if (subject.isNotBlank()) {
            models.tools.bind(family, subject)
            models.notifications?.let { it.bind(family, subject, state.userId); it.startPolling() }
        } else { models.tools.clear(); models.notifications?.clear() }
    }
    LaunchedEffect(foreground, family, state.userId, feature) {
        if (!foreground || family.isBlank() || feature != null) return@LaunchedEffect
        var ticks = 0
        while (true) {
            delay(15000)
            models.reminders.tick()
            if (++ticks % 2 == 0) {
                account.reload()
                models.reminders.refresh()
                models.memories.refresh()
            }
        }
    }
}

@Composable
internal fun HomeConnectionCard(state: CompanionState, model: CompanionModel, onSettings: () -> Unit) {
    var address by remember(state.address) { mutableStateOf(state.address) }
    HomeCard {
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
            Text(homeConnectionLabel(state), style = MaterialTheme.typography.titleMedium,
                modifier = Modifier.weight(1f).padding(top = 12.dp))
            if (state.loggedIn) TextButton(onClick = {
                if (state.pendingWrite) model.retry() else model.reload()
            }, enabled = !state.busy) { Text(if (state.pendingWrite) "重试操作" else "刷新连接") }
        }
        Text("AI 陪伴 · 支持语音与文字 · 连接后显示服务状态", fontSize = 14.sp)
        if (state.error.isNotBlank()) Text(state.error, color = MaterialTheme.colorScheme.error)
        if (state.message.isNotBlank()) Text(state.message)
        if (state.pendingWrite) Text("上次操作的结果尚未确认，请先重试。")
        if (!state.loggedIn) {
            OutlinedTextField(address, { address = it }, label = { Text("服务地址") },
                enabled = !state.busy, singleLine = true, modifier = Modifier.fillMaxWidth())
            HomeButton("演示登录", !state.busy) { model.login(address) }
            HomeButton("通过 USB 连接本机", !state.busy) { model.login("http://127.0.0.1:8000") }
        }
        TextButton(onClick = onSettings, enabled = !state.busy) { Text("家庭、邀请与授权设置") }
    }
}

@Composable
internal fun HomeCard(modifier: Modifier = Modifier, content: @Composable ColumnScope.() -> Unit) {
    Surface(shape = RoundedCornerShape(24.dp), color = MaterialTheme.colorScheme.surface,
        modifier = modifier.fillMaxWidth()) {
        Column(Modifier.padding(20.dp), verticalArrangement = Arrangement.spacedBy(12.dp), content = content)
    }
}

@Composable
internal fun HomeButton(label: String, enabled: Boolean = true, onClick: () -> Unit) {
    Button(onClick = onClick, enabled = enabled, shape = RoundedCornerShape(28.dp),
        modifier = Modifier.fillMaxWidth().heightIn(min = 52.dp)) { Text(label, fontSize = 16.sp) }
}

@Composable
internal fun HomeMemorySection(state: CompanionState, model: MemoryModel, subject: String = "",
    onOpen: () -> Unit) {
    val memory by model.state.collectAsState()
    val items = homeMemoryItems(state, memory).filter { subject.isBlank() || it.subject == subject }
    val enabled = homeFamily(state).isNotBlank() && !state.offline && state.error.isBlank() &&
        !state.busy && !state.pendingWrite && !memory.busy && !memory.pending
    HomeCard {
        Text("家庭记忆", style = MaterialTheme.typography.headlineSmall)
        Text("只有本人授权且已人工确认的记忆，才会用于陪伴。", fontSize = 14.sp)
        if (memory.error.isNotBlank()) Text(memory.error, color = MaterialTheme.colorScheme.error)
        if (memory.message.isNotBlank()) Text(memory.message)
        if (memory.busy) LinearProgressIndicator(Modifier.fillMaxWidth())
        if (memory.pending) HomeButton("重试记忆操作", !memory.busy && !state.offline) { model.retry() }
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            OutlinedButton(onClick = { model.showCandidates(false) }, enabled = enabled) { Text("已确认记忆") }
            OutlinedButton(onClick = { model.showCandidates(true) }, enabled = enabled) { Text("待确认候选") }
        }
        if (items.isEmpty() && !memory.busy) Text(when {
            state.offline -> "离线时不展示家庭记忆。"
            homeFamily(state).isBlank() -> "请先登录并加入家庭。"
            memory.error.isNotBlank() -> "暂时无法读取，请检查当前授权后重试。"
            memory.candidates -> "暂无可访问的待确认候选。"
            else -> "暂无已确认且获准使用的记忆。"
        })
        items.take(6).forEach { item ->
            OutlinedCard(onClick = { onOpen(); model.detail(item.id) }, enabled = enabled,
                shape = RoundedCornerShape(18.dp), modifier = Modifier.fillMaxWidth()) {
                Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text(item.title, style = MaterialTheme.typography.titleMedium)
                    Text(item.content, maxLines = 3)
                    Text(if (item.status == "PENDING") "待人工核对，不作为事实" else "已人工确认")
                    if (item.attachments.isNotEmpty()) Text("${item.attachments.size} 张照片 · 点击查看")
                }
            }
        }
        HomeButton("添加记忆 / 查看全部与照片", enabled, onOpen)
    }
}

@Composable
internal fun HomeFeatureSheet(feature: HomeFeature, state: CompanionState, models: HomeModels,
    subjects: List<Pair<String, String>>, elder: Boolean, initialTopic: String? = null,
    conversationId: String = "", startWithVoice: Boolean = false, onClose: () -> Unit) {
    val family = homeFamily(state)
    val unavailable = state.busy || state.offline || state.pendingWrite || state.error.isNotBlank()
    val scope = rememberCoroutineScope()
    var closing by remember { mutableStateOf(false) }
    fun close() {
        if (closing) return
        val conversation = models.conversation?.takeIf { feature == HomeFeature.CHAT && it.state.value.id.isNotBlank() }
        if (conversation == null) onClose() else {
            closing = true
            scope.launch {
                conversation.end()
                conversation.awaitIdle()
                if (conversation.state.value.id.isBlank() && !conversation.state.value.busy) onClose()
                else closing = false
            }
        }
    }
    Dialog(onDismissRequest = ::close,
        properties = DialogProperties(usePlatformDefaultWidth = false, decorFitsSystemWindows = false)) {
        BackHandler(onBack = ::close)
        Column(Modifier.fillMaxSize().background(MaterialTheme.colorScheme.background).safeDrawingPadding()) {
            Row(Modifier.fillMaxWidth().padding(horizontal = 20.dp, vertical = 8.dp), horizontalArrangement = Arrangement.SpaceBetween) {
                Text(feature.title, style = MaterialTheme.typography.titleLarge, modifier = Modifier.weight(1f).padding(top = 12.dp))
                TextButton(onClick = ::close, enabled = !closing) { Text(if (closing) "正在结束…" else "返回首页") }
            }
            Column(Modifier.weight(1f).then(if (feature == HomeFeature.CHAT) Modifier.fillMaxWidth()
                else Modifier.verticalScroll(rememberScrollState())).padding(16.dp),
                verticalArrangement = Arrangement.spacedBy(16.dp)) {
                if (family.isBlank()) Text("请先登录并确认加入家庭。") else when (feature) {
                    HomeFeature.REPORTS -> WeeklyReportPanel(models.tools, family, subjects, elder, unavailable,
                        state.permissions.toString() + state.selfPermissions.toString() + state.members.toString())
                    HomeFeature.REMINDERS -> ReminderPanel(models.reminders, family, state.userId, subjects, unavailable, models.onNotifications)
                    HomeFeature.MESSAGES -> models.messages?.let {
                        MessagePanel(it, family, state.userId, elder, unavailable, manageLifecycle = false)
                    }
                    HomeFeature.MEMORIES -> MemoryPanel(models.memories, family, state.userId, subjects, unavailable)
                    HomeFeature.CHAT -> models.conversation?.let { conversation ->
                        val chat by conversation.state.collectAsState()
                        var sent by remember(family, state.userId, initialTopic) { mutableStateOf(false) }
                        LaunchedEffect(family, state.userId) {
                            conversation.bind(family, state.userId)
                            if (!unavailable) conversation.start()
                        }
                        LaunchedEffect(chat.connected) {
                            if (chat.connected && initialTopic != null && !sent && !unavailable) {
                                sent = true; conversation.input(initialTopic)
                            }
                        }
                        ConversationPanel(conversation, family, state.userId, unavailable, startWithVoice)
                    }
                    HomeFeature.CONVERSATION -> {
                        val conversation = models.conversation?.state?.collectAsState()?.value
                        ConversationToolsPanel(models.tools, family, subjects, elder, unavailable,
                            conversationId.ifBlank { conversation?.recapId?.ifEmpty { conversation.id }.orEmpty() })
                    }
                    HomeFeature.NOTIFICATIONS -> models.notifications?.let {
                        NotificationPanel(it, family, state.userId, subjects, unavailable,
                            state.permissions.toString() + state.members.toString(), elder = elder)
                    }
                }
            }
        }
    }
}

@Composable
internal fun HomeTheme(content: @Composable () -> Unit) {
    MaterialTheme(colorScheme = lightColorScheme(
        primary = Color(0xFFB0532D), onPrimary = Color.White, secondary = Color(0xFF4C5A42),
        secondaryContainer = Color(0xFFDCE3D4), onSecondaryContainer = Color(0xFF2A2420),
        background = Color(0xFFF6F1EA), surface = Color(0xFFFFFDF9), surfaceVariant = Color(0xFFEFE7DC),
        onBackground = Color(0xFF2A2420), onSurface = Color(0xFF2A2420), outline = Color(0xFF857A70)
    ), content = content)
}
