package org.example.niannian.feature.family

import org.example.niannian.feature.conversation.PersimmonCompanionOrb

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.slideInVertically
import androidx.compose.animation.slideOutVertically
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import java.time.LocalDate
import java.time.LocalTime

private val FPaper = Color(0xFFF6F1EA)
private val FPaperDeep = Color(0xFFEFE7DC)
private val FPaperCard = Color(0xFFFFFDF9)
private val FInk = Color(0xFF2A2420)
private val FInkSoft = Color(0xFF5C524A)
private val FInkMute = Color(0xFF857A70)
private val FLine = Color(0xFFE6DDD1)

private val FPersimmon50 = Color(0xFFFBEDE5)
private val FPersimmon100 = Color(0xFFF6D9C8)
private val FPersimmon500 = Color(0xFFC8643B)
private val FPersimmon600 = Color(0xFFB0532D)
private val FPersimmon700 = Color(0xFF8F4224)

private val FSage50 = Color(0xFFEEF1EA)
private val FSage100 = Color(0xFFDCE3D4)
private val FSage700 = Color(0xFF4C5A42)
private val FHeroBg = Color(0xFFF9E3D3)
private val FHeroGlow = Color(0xFFFCD2B4)

private enum class FamilyNavTab { CARE, POST, MEMORIES, SETTINGS }

internal data class FamilyReminderRow(
    val id: String,
    val time: String,
    val title: String,
    val detail: String,
    val done: Boolean,
    val isNext: Boolean = false,
    val isMedication: Boolean = false
)

private data class FamilyMemoryCandidateRow(
    val id: String,
    val title: String,
    val content: String,
    val source: String,
    val confirmed: Boolean
)

@Composable
internal fun FamilyDesignHome(
    state: CompanionState,
    model: CompanionModel,
    models: HomeModels,
    onOpenFamilySettings: () -> Unit
) {
    val scrollState = rememberScrollState()
    val scope = rememberCoroutineScope()
    val family = homeFamily(state)
    val subjects = homeSubjects(state, false)
    var selectedSubject by remember(state.userId, family) { mutableStateOf("") }
    val subject = subjects.firstOrNull { it.first == selectedSubject } ?: subjects.firstOrNull()
    val subjectName = subject?.second ?: "尚未选择长辈"
    val subjectId = subject?.first.orEmpty()
    var feature by remember(state.userId, family) { mutableStateOf<HomeFeature?>(null) }
    val remindersState by models.reminders.state.collectAsState()
    val memoriesState by models.memories.state.collectAsState()
    val toolsState by models.tools.state.collectAsState()
    BindHomeModels(state, model, models, subjectId, feature)

    var activeTab by remember { mutableStateOf(FamilyNavTab.CARE) }
    var toast by remember { mutableStateOf<String?>(null) }


    var addReminderSheetOpen by remember { mutableStateOf(false) }
    var newRemTime by remember { mutableStateOf("17:30") }
    var newRemTitle by remember { mutableStateOf("") }

    var familySettingSheetOpen by remember { mutableStateOf(false) }

    val momReminders = homeFamilyReminderRows(state, remindersState, subjectId)
    val backendMemories = homeMemoryItems(state, memoriesState).filter { it.subject == subjectId }
    val memoryCandidates = backendMemories.map { item ->
        val confirmed = item.status == "CONFIRMED"
        FamilyMemoryCandidateRow(item.id, item.title, item.content,
            if (confirmed) "已人工核对 · 存入家庭记忆库" else "待人工核对 · 不作为事实引用", confirmed)
    }

    LaunchedEffect(toast) {
        if (toast != null) {
            delay(2600)
            toast = null
        }
    }

    val childName = state.userName.ifBlank { "家人" }

    Box(
        modifier = Modifier
            .fillMaxSize()
            .background(FPaper)
    ) {
        Column(modifier = Modifier.fillMaxSize()) {
            Column(
                modifier = Modifier
                    .weight(1f)
                    .verticalScroll(scrollState)
                    .padding(bottom = 32.dp)
            ) {
                // 1. Header
                Column(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(horizontal = 24.dp)
                        .padding(top = 14.dp)
                ) {
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Box(
                                modifier = Modifier
                                    .size(34.dp)
                                    .clip(CircleShape)
                                    .background(FSage700),
                                contentAlignment = Alignment.Center
                            ) {
                                Text(
                                    text = "念",
                                    fontFamily = FontFamily.Serif,
                                    fontWeight = FontWeight.Bold,
                                    fontSize = 15.sp,
                                    color = Color.White
                                )
                            }
                            Spacer(modifier = Modifier.width(8.dp))
                            Text(
                                text = "念念",
                                fontFamily = FontFamily.Serif,
                                fontWeight = FontWeight.Bold,
                                fontSize = 18.sp,
                                letterSpacing = 2.sp,
                                color = FInk
                            )
                            Spacer(modifier = Modifier.width(8.dp))
                            Surface(shape = CircleShape, color = FSage50) {
                                Text(
                                    text = "子女端",
                                    fontSize = 12.sp,
                                    fontWeight = FontWeight.SemiBold,
                                    color = FSage700,
                                    modifier = Modifier.padding(horizontal = 9.dp, vertical = 3.dp)
                                )
                            }
                        }

                        Surface(
                            shape = CircleShape,
                            color = if (state.loggedIn) FSage100 else FPaperDeep,
                            modifier = Modifier
                                .clip(CircleShape)
                                .clickable { familySettingSheetOpen = true }
                        ) {
                            Text(
                                text = if (state.loggedIn) "● ${state.selected?.name ?: "家庭"} · " + when {
                                    state.offline -> "离线"
                                    state.error.isNotBlank() -> "待确认"
                                    state.busy -> "核对中"
                                    family.isBlank() -> "待加入"
                                    else -> "已联机"
                                } else "尚未登录 · 连接家庭",
                                fontSize = 13.sp,
                                fontWeight = FontWeight.Medium,
                                color = if (state.loggedIn) FSage700 else FInk,
                                modifier = Modifier.padding(horizontal = 13.dp, vertical = 8.dp)
                            )
                        }
                    }

                    Spacer(modifier = Modifier.height(18.dp))
                    HomeWeatherCard("${state.userId}:$family:$subjectId")
                    if (subjects.size > 1) {
                        subjects.forEach { (id, name) ->
                            TextButton(onClick = { selectedSubject = id }) {
                                Text(if (id == subjectId) "✓ $name" else name)
                            }
                        }
                    }

                    Spacer(modifier = Modifier.height(6.dp))
                    Text(
                        text = "您好，$childName",
                        fontFamily = FontFamily.Serif,
                        fontWeight = FontWeight.Bold,
                        fontSize = 30.sp,
                        color = FInk
                    )
                    Text(
                        text = "家人的近况，以实际留言和提醒反馈为准。",
                        fontSize = 15.sp,
                        color = FInkSoft
                    )
                }

                Spacer(modifier = Modifier.height(20.dp))

                // 2. Mother Peace-of-Mind Hero Card
                Surface(
                    shape = RoundedCornerShape(32.dp),
                    color = FHeroBg,
                    shadowElevation = 4.dp,
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(horizontal = 16.dp)
                ) {
                    Box(modifier = Modifier.fillMaxWidth()) {
                        Canvas(modifier = Modifier.matchParentSize()) {
                            drawCircle(
                                brush = Brush.radialGradient(
                                    colors = listOf(FHeroGlow.copy(alpha = 0.85f), Color.Transparent),
                                    center = Offset(size.width * 0.88f, size.height * 0.14f),
                                    radius = size.width * 0.55f
                                ),
                                radius = size.width * 0.55f,
                                center = Offset(size.width * 0.88f, size.height * 0.14f)
                            )
                        }

                        Column(
                            modifier = Modifier
                                .fillMaxWidth()
                                .padding(20.dp)
                        ) {
                            Row(
                                modifier = Modifier.fillMaxWidth(),
                                horizontalArrangement = Arrangement.SpaceBetween,
                                verticalAlignment = Alignment.Top
                            ) {
                                Column(modifier = Modifier.weight(1f)) {
                                    Surface(shape = CircleShape, color = FSage700) {
                                        Text(
                                            text = homeConnectionLabel(state),
                                            fontSize = 12.sp,
                                            fontWeight = FontWeight.Medium,
                                            color = Color.White,
                                            modifier = Modifier.padding(horizontal = 11.dp, vertical = 4.dp)
                                        )
                                    }
                                    Spacer(modifier = Modifier.height(10.dp))
                                    Text(
                                        text = subjectName,
                                        fontFamily = FontFamily.Serif,
                                        fontWeight = FontWeight.Bold,
                                        fontSize = 25.sp,
                                        color = FInk
                                    )
                                    Text(
                                        text = "小念是 AI 助手 · 家人通知需单独查看",
                                        fontSize = 14.sp,
                                        color = FInkSoft
                                    )
                                }

                                Box(modifier = Modifier.offset(x = 6.dp, y = (-6).dp)) {
                                    PersimmonCompanionOrb(size = 94.dp)
                                }
                            }

                            Spacer(modifier = Modifier.height(12.dp))

                            // 3-Column Metrics
                            Row(
                                modifier = Modifier.fillMaxWidth(),
                                horizontalArrangement = Arrangement.spacedBy(8.dp)
                            ) {
                                listOf(
                                    Triple("今日提醒", "${momReminders.count { it.done }} / ${momReminders.size}",
                                        if (state.offline || remindersState.offline) "离线隐藏" else "反馈为准"),
                                    Triple("家庭记忆", "${backendMemories.count { it.status == "CONFIRMED" }} 条", "已人工确认"),
                                    Triple("下次提醒", momReminders.firstOrNull { it.isNext }?.time ?: "--:--",
                                        momReminders.firstOrNull { it.isNext }?.title?.take(5) ?: "暂无提醒")
                                ).forEach { (label, main, sub) ->
                                    Surface(
                                        shape = RoundedCornerShape(18.dp),
                                        color = FPaperCard.copy(alpha = 0.88f),
                                        modifier = Modifier.weight(1f)
                                    ) {
                                        Column(modifier = Modifier.padding(horizontal = 11.dp, vertical = 10.dp)) {
                                            Text(text = label, fontSize = 12.sp, color = FInkMute)
                                            Text(
                                                text = main,
                                                fontFamily = FontFamily.Serif,
                                                fontWeight = FontWeight.Bold,
                                                fontSize = 18.sp,
                                                color = FInk
                                            )
                                            Text(text = sub, fontSize = 12.sp, color = FSage700, fontWeight = FontWeight.Medium)
                                        }
                                    }
                                }
                            }

                            Spacer(modifier = Modifier.height(12.dp))

                            // Desensitized AI Recap
                            Surface(
                                shape = RoundedCornerShape(topStart = 6.dp, topEnd = 20.dp, bottomEnd = 20.dp, bottomStart = 20.dp),
                                color = FPaperCard.copy(alpha = 0.94f),
                                modifier = Modifier.fillMaxWidth()
                            ) {
                                Column(modifier = Modifier.padding(14.dp)) {
                                    Row(
                                        modifier = Modifier.fillMaxWidth(),
                                        horizontalArrangement = Arrangement.SpaceBetween,
                                        verticalAlignment = Alignment.CenterVertically
                                    ) {
                                        Text(
                                            text = "✦ 交流回顾（脱敏·无逐字稿）",
                                            fontSize = 12.sp,
                                            fontWeight = FontWeight.SemiBold,
                                            color = FPersimmon700,
                                            maxLines = 1
                                        )
                                        Text(
                                            text = "按本人授权读取",
                                            fontSize = 11.5.sp,
                                            color = FInkMute,
                                            maxLines = 1,
                                            softWrap = false
                                        )
                                    }
                                    Spacer(modifier = Modifier.height(6.dp))
                                    Text(
                                        text = if (!state.offline && state.error.isBlank() && family.isNotBlank() &&
                                            toolsState.family == family && toolsState.owner == subjectId && toolsState.summary.isNotBlank())
                                            toolsState.summary else "尚未读取获准的会话摘要。打开交流回顾后，可按会话查看；暂无数据不代表没有异常。",
                                        fontFamily = FontFamily.Serif,
                                        fontSize = 16.5.sp,
                                        lineHeight = 25.sp,
                                        color = FInk
                                    )
                                }
                            }

                            Spacer(modifier = Modifier.height(14.dp))

                            // Dual CTA Buttons
                            Row(
                                modifier = Modifier.fillMaxWidth(),
                                horizontalArrangement = Arrangement.spacedBy(10.dp)
                            ) {
                                Button(
                                    onClick = { feature = HomeFeature.MESSAGES },
                                    colors = ButtonDefaults.buttonColors(
                                        containerColor = FPersimmon600,
                                        contentColor = Color.White
                                    ),
                                    contentPadding = PaddingValues(horizontal = 14.dp, vertical = 0.dp),
                                    shape = CircleShape,
                                    modifier = Modifier
                                        .weight(1.18f)
                                        .height(56.dp)
                                ) {
                                    Text(text = "发文字留言", fontSize = 15.5.sp, fontWeight = FontWeight.Bold, maxLines = 1, softWrap = false)
                                }

                                Button(
                                    onClick = {},
                                    enabled = false,
                                    colors = ButtonDefaults.buttonColors(
                                        containerColor = FInk,
                                        contentColor = FPaper
                                    ),
                                    contentPadding = PaddingValues(horizontal = 14.dp, vertical = 0.dp),
                                    shape = CircleShape,
                                    modifier = Modifier
                                        .weight(1f)
                                        .height(56.dp)
                                ) {
                                    Icon(imageVector = NianNianIcons.Video, contentDescription = null, modifier = Modifier.size(18.dp))
                                    Spacer(modifier = Modifier.width(6.dp))
                                    Text(text = "视频未接入", fontSize = 15.5.sp, fontWeight = FontWeight.Medium, maxLines = 1, softWrap = false)
                                }
                            }
                        }
                    }
                }

                Spacer(modifier = Modifier.height(30.dp))

                Column(Modifier.padding(horizontal = 16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                    Text("视频通话尚未接入，当前可发送文字留言。", color = FInkMute, fontSize = 14.sp)
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        TextButton(onClick = { feature = HomeFeature.CONVERSATION }) { Text("交流回顾") }
                        TextButton(onClick = { feature = HomeFeature.NOTIFICATIONS }) { Text("家人通知") }
                    }
                    HomeMessagesSection(state, models.messages,
                        onOpen = { feature = HomeFeature.MESSAGES },
                        onPhotos = { feature = HomeFeature.MEMORIES })
                }

                Spacer(modifier = Modifier.height(30.dp))

                // 4. Shared Reminders for Mom
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(horizontal = 24.dp),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Column {
                        Text(
                            text = "长辈的今日提醒",
                            fontFamily = FontFamily.Serif,
                            fontWeight = FontWeight.Bold,
                            fontSize = 22.sp,
                            color = FInk
                        )
                        Text(
                            text = "远程协同备忘 · 反馈实时同步",
                            fontSize = 14.sp,
                            color = FInkSoft
                        )
                    }

                    Surface(
                        shape = CircleShape,
                        color = FPersimmon50,
                        modifier = Modifier
                            .clip(CircleShape)
                            .clickable { addReminderSheetOpen = true }
                    ) {
                        Text(
                            text = "+ 添个提醒",
                            fontSize = 14.sp,
                            fontWeight = FontWeight.SemiBold,
                            color = FPersimmon700,
                            modifier = Modifier.padding(horizontal = 14.dp, vertical = 8.dp)
                        )
                    }
                }

                Spacer(modifier = Modifier.height(10.dp))

                Column(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(horizontal = 16.dp),
                    verticalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    momReminders.forEach { r ->
                        Surface(
                            shape = RoundedCornerShape(22.dp),
                            color = if (r.isNext) FPaperCard else FPaperCard.copy(alpha = 0.72f),
                            shadowElevation = if (r.isNext) 2.dp else 0.dp,
                            border = if (r.isNext) BorderStroke(1.dp, FPersimmon100) else null,
                            modifier = Modifier.fillMaxWidth()
                        ) {
                            Row(
                                modifier = Modifier
                                    .fillMaxWidth()
                                    .padding(horizontal = 14.dp, vertical = 12.dp),
                                verticalAlignment = Alignment.CenterVertically
                            ) {
                                Box(
                                    modifier = Modifier
                                        .size(40.dp)
                                        .clip(RoundedCornerShape(14.dp))
                                        .background(
                                            when {
                                                r.done -> FSage50
                                                r.isNext -> FPersimmon50
                                                else -> FPaperDeep
                                            }
                                        ),
                                    contentAlignment = Alignment.Center
                                ) {
                                    Icon(
                                        imageVector = if (r.done) NianNianIcons.Check else if (r.isMedication) NianNianIcons.Pill else NianNianIcons.Droplet,
                                        contentDescription = null,
                                        tint = if (r.done) FSage700 else if (r.isNext) FPersimmon600 else FInkSoft,
                                        modifier = Modifier.size(20.dp)
                                    )
                                }

                                Spacer(modifier = Modifier.width(12.dp))

                                Column(modifier = Modifier.weight(1f)) {
                                    Row(verticalAlignment = Alignment.CenterVertically) {
                                        Text(
                                            text = r.time,
                                            fontFamily = FontFamily.Serif,
                                            fontWeight = FontWeight.Bold,
                                            fontSize = 15.5.sp,
                                            color = FInk
                                        )
                                        Spacer(modifier = Modifier.width(8.dp))
                                        Text(
                                            text = r.title,
                                            fontWeight = FontWeight.SemiBold,
                                            fontSize = 15.5.sp,
                                            color = FInk
                                        )
                                    }
                                    Text(
                                        text = r.detail,
                                        fontSize = 13.sp,
                                        color = FInkMute
                                    )
                                }

                                Surface(
                                    shape = CircleShape,
                                    color = if (r.done) FSage50 else if (r.isNext) FPersimmon50 else FPaperDeep
                                ) {
                                    Text(
                                        text = if (r.done) "已完成 ✓" else if (r.isNext) "接下来" else "待执行",
                                        fontSize = 12.sp,
                                        fontWeight = FontWeight.Medium,
                                        color = if (r.done) FSage700 else if (r.isNext) FPersimmon700 else FInkMute,
                                        modifier = Modifier.padding(horizontal = 9.dp, vertical = 4.dp)
                                    )
                                }
                            }
                        }
                    }
                }

                Spacer(modifier = Modifier.height(30.dp))

                // 5. Family Memory Verification Section
                Column(modifier = Modifier.padding(horizontal = 24.dp)) {
                    Text(
                        text = "家庭记忆库",
                        fontFamily = FontFamily.Serif,
                        fontWeight = FontWeight.Bold,
                        fontSize = 22.sp,
                        color = FInk
                    )
                    Text(
                        text = "候选经家人核对确认后，小念才作为事实引用",
                        fontSize = 14.sp,
                        color = FInkSoft
                    )
                }

                Spacer(modifier = Modifier.height(10.dp))

                Column(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(horizontal = 16.dp),
                    verticalArrangement = Arrangement.spacedBy(10.dp)
                ) {
                    memoryCandidates.forEach { c ->
                        Surface(
                            shape = RoundedCornerShape(26.dp),
                            color = FPaperCard,
                            shadowElevation = 2.dp,
                            modifier = Modifier.fillMaxWidth()
                        ) {
                            Column(modifier = Modifier.padding(18.dp)) {
                                Row(
                                    modifier = Modifier.fillMaxWidth(),
                                    horizontalArrangement = Arrangement.SpaceBetween
                                ) {
                                    Surface(
                                        shape = CircleShape,
                                        color = if (c.confirmed) FSage50 else FPersimmon50
                                    ) {
                                        Text(
                                            text = if (c.confirmed) "✓ 已确认家庭事实" else "✦ 待核对记忆候选",
                                            fontSize = 12.sp,
                                            fontWeight = FontWeight.SemiBold,
                                            color = if (c.confirmed) FSage700 else FPersimmon700,
                                            modifier = Modifier.padding(horizontal = 10.dp, vertical = 3.dp)
                                        )
                                    }
                                    Text(text = c.source, fontSize = 12.sp, color = FInkMute)
                                }

                                Spacer(modifier = Modifier.height(8.dp))
                                Text(
                                    text = c.title,
                                    fontFamily = FontFamily.Serif,
                                    fontWeight = FontWeight.Bold,
                                    fontSize = 18.sp,
                                    color = FInk
                                )
                                Spacer(modifier = Modifier.height(4.dp))
                                Text(
                                    text = c.content,
                                    fontSize = 14.5.sp,
                                    lineHeight = 22.sp,
                                    color = FInkSoft
                                )

                                if (!c.confirmed) {
                                    Spacer(modifier = Modifier.height(12.dp))
                                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                                        Button(
                                            onClick = {
                                                backendMemories.find { it.id == c.id }?.let { item ->
                                                    models.memories.transition(item.id, "confirm")
                                                }
                                            },
                                            colors = ButtonDefaults.buttonColors(
                                                containerColor = FSage700,
                                                contentColor = Color.White
                                            ),
                                            shape = CircleShape,
                                            modifier = Modifier
                                                .weight(1f)
                                                .height(44.dp)
                                        ) {
                                            Text(text = "✓ 核对无误，确认为家庭事实", fontSize = 13.5.sp, fontWeight = FontWeight.Bold)
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }

            // Bottom Navigation Bar
            Surface(
                color = FPaperCard.copy(alpha = 0.96f),
                shadowElevation = 8.dp,
                modifier = Modifier.fillMaxWidth()
            ) {
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(top = 8.dp, bottom = 12.dp),
                    horizontalArrangement = Arrangement.SpaceAround
                ) {
                    listOf(
                        Triple(FamilyNavTab.CARE, "守护", NianNianIcons.Sun),
                        Triple(FamilyNavTab.POST, "留言", NianNianIcons.MessageCircle),
                        Triple(FamilyNavTab.MEMORIES, "记忆库", NianNianIcons.HeartHandshake),
                        Triple(FamilyNavTab.SETTINGS, "家庭设置", NianNianIcons.Settings)
                    ).forEach { (tab, label, icon) ->
                        val selected = activeTab == tab
                        Column(
                            horizontalAlignment = Alignment.CenterHorizontally,
                            modifier = Modifier
                                .weight(1f)
                                .clickable {
                                    when (tab) {
                                        FamilyNavTab.POST -> feature = HomeFeature.MESSAGES
                                        FamilyNavTab.SETTINGS -> familySettingSheetOpen = true
                                        FamilyNavTab.CARE -> {
                                            activeTab = tab
                                            scope.launch { scrollState.animateScrollTo(0) }
                                        }
                                        FamilyNavTab.MEMORIES -> {
                                            feature = HomeFeature.MEMORIES
                                        }
                                    }
                                }
                                .padding(vertical = 4.dp)
                        ) {
                            Box(
                                modifier = Modifier
                                    .width(64.dp)
                                    .height(36.dp)
                                    .clip(CircleShape)
                                    .background(if (selected) FSage100 else Color.Transparent),
                                contentAlignment = Alignment.Center
                            ) {
                                Icon(
                                    imageVector = icon,
                                    contentDescription = label,
                                    tint = if (selected) FSage700 else FInkSoft,
                                    modifier = Modifier.size(23.dp)
                                )
                            }
                            Spacer(modifier = Modifier.height(4.dp))
                            Text(
                                text = label,
                                fontSize = 13.sp,
                                fontWeight = if (selected) FontWeight.Bold else FontWeight.Normal,
                                color = if (selected) FInk else FInkSoft
                            )
                        }
                    }
                }
            }
        }

        // Toast Snackbar
        AnimatedVisibility(
            visible = toast != null,
            enter = fadeIn() + slideInVertically { it / 2 },
            exit = fadeOut() + slideOutVertically { it / 2 },
            modifier = Modifier
                .align(Alignment.BottomCenter)
                .padding(horizontal = 20.dp, vertical = 96.dp)
        ) {
            Surface(shape = RoundedCornerShape(18.dp), color = FInk, shadowElevation = 10.dp) {
                Text(
                    text = toast.orEmpty(),
                    color = FPaper,
                    fontSize = 15.sp,
                    modifier = Modifier.padding(horizontal = 18.dp, vertical = 13.dp)
                )
            }
        }

        // Add Reminder Sheet
        if (addReminderSheetOpen) {
            Box(
                modifier = Modifier
                    .fillMaxSize()
                    .background(FInk.copy(alpha = 0.4f))
                    .clickable { addReminderSheetOpen = false },
                contentAlignment = Alignment.BottomCenter
            ) {
                Surface(
                    shape = RoundedCornerShape(topStart = 32.dp, topEnd = 32.dp),
                    color = FPaperCard,
                    modifier = Modifier
                        .fillMaxWidth()
                        .clickable(enabled = false) {}
                ) {
                    Column(modifier = Modifier.padding(24.dp)) {
                        Text(
                            text = "为$subjectName 添加生活提醒",
                            fontFamily = FontFamily.Serif,
                            fontWeight = FontWeight.Bold,
                            fontSize = 22.sp,
                            color = FInk
                        )
                        Spacer(modifier = Modifier.height(12.dp))
                        OutlinedTextField(
                            value = newRemTime,
                            onValueChange = { newRemTime = it },
                            label = { Text("提醒时间 HH:mm") },
                            modifier = Modifier.fillMaxWidth()
                        )
                        Spacer(modifier = Modifier.height(8.dp))
                        OutlinedTextField(
                            value = newRemTitle,
                            onValueChange = { newRemTitle = it },
                            label = { Text("提醒事项（例如：傍晚阳台收衣服）") },
                            modifier = Modifier.fillMaxWidth()
                        )
                        Spacer(modifier = Modifier.height(14.dp))
                        Button(
                            onClick = {
                                val t = newRemTitle.trim()
                                when {
                                    t.isBlank() -> toast = "请填写提醒事项。"
                                    family.isBlank() || subjectId.isBlank() -> toast = "请先登录并选择已加入家庭的长辈。"
                                    state.offline || state.error.isNotBlank() || state.pendingWrite -> toast = "请恢复连接并核对授权后重试。"
                                    runCatching { LocalTime.parse(newRemTime) }.isFailure -> toast = "请按 HH:mm 填写有效时间。"
                                    else -> scope.launch {
                                        var saved = false
                                        models.reminders.save(subjectId, t, "${state.userName}添加的生活提醒", LocalDate.now().toString(),
                                            newRemTime, "Asia/Shanghai", "CALENDAR", true, false,
                                            onSaved = { saved = true })?.join()
                                        val result = models.reminders.state.value
                                        if (result.family == family && result.user == state.userId) {
                                            if (saved) {
                                                newRemTitle = ""
                                                addReminderSheetOpen = false
                                            }
                                            toast = result.error.ifBlank { result.message.ifBlank { "提醒尚未保存，请稍后重试。" } }
                                        }
                                    }
                                }
                            },
                            enabled = !state.busy && !remindersState.busy,
                            colors = ButtonDefaults.buttonColors(containerColor = FInk, contentColor = FPaper),
                            shape = CircleShape,
                            contentPadding = PaddingValues(vertical = 14.dp),
                            modifier = Modifier.fillMaxWidth()
                        ) {
                            Text(text = "保存并同步至长辈提醒", fontSize = 16.sp, fontWeight = FontWeight.Bold)
                        }
                    }
                }
            }
        }

        // Family Settings & Backend Console Sheet
        if (familySettingSheetOpen) {
            Box(
                modifier = Modifier
                    .fillMaxSize()
                    .background(FInk.copy(alpha = 0.4f))
                    .clickable { familySettingSheetOpen = false },
                contentAlignment = Alignment.BottomCenter
            ) {
                Surface(
                    shape = RoundedCornerShape(topStart = 32.dp, topEnd = 32.dp),
                    color = FPaperCard,
                    modifier = Modifier
                        .fillMaxWidth()
                        .clickable(enabled = false) {}
                ) {
                    Column(modifier = Modifier.padding(24.dp)) {
                        Text(
                            text = "家庭设置与长辈授权边界",
                            fontFamily = FontFamily.Serif,
                            fontWeight = FontWeight.Bold,
                            fontSize = 22.sp,
                            color = FInk
                        )
                        Spacer(modifier = Modifier.height(12.dp))
                        Surface(shape = RoundedCornerShape(20.dp), color = FSage50, modifier = Modifier.fillMaxWidth()) {
                            Text(
                                text = "记忆、提醒、交流摘要与家人通知均以长辈本人的当前授权为准，可在完整家庭设置中查看或撤回。系统不提供陪伴对话的原始录音或逐字稿。",
                                fontSize = 14.sp,
                                lineHeight = 22.sp,
                                color = FInkSoft,
                                modifier = Modifier.padding(16.dp)
                            )
                        }
                        Spacer(modifier = Modifier.height(12.dp))
                        if (!state.loggedIn) {
                            Button(
                                onClick = {
                                    model.login("http://127.0.0.1:8000")
                                    toast = "正在通过 USB 隧道连接本机后端 (127.0.0.1:8000)…"
                                },
                                colors = ButtonDefaults.buttonColors(containerColor = FSage700, contentColor = Color.White),
                                shape = CircleShape,
                                modifier = Modifier
                                    .fillMaxWidth()
                                    .height(50.dp)
                            ) {
                                Text(text = "⚡ 一键连接本机后端 (demo-child)", fontSize = 15.sp, fontWeight = FontWeight.Bold)
                            }
                            Spacer(modifier = Modifier.height(10.dp))
                        } else if (state.loggedIn) {
                            Surface(shape = RoundedCornerShape(16.dp), color = FPaperDeep, modifier = Modifier.fillMaxWidth()) {
                                Column(modifier = Modifier.padding(14.dp)) {
                                    Text(
                                        text = homeConnectionStatus(state),
                                        fontSize = 14.sp,
                                        fontWeight = FontWeight.Bold,
                                        color = FSage700
                                    )
                                    Text(
                                        text = "收到长辈有效授权：${state.permissions.count { homeConsentGranted(it) }} 项 · 家庭成员：${state.members.size} 人",
                                        fontSize = 13.sp,
                                        color = FInkSoft
                                    )
                                    Spacer(modifier = Modifier.height(8.dp))
                                    Row(
                                        modifier = Modifier.fillMaxWidth(),
                                        horizontalArrangement = Arrangement.spacedBy(6.dp)
                                    ) {
                                        listOf(
                                            HomeFeature.REMINDERS to "提醒管理",
                                            HomeFeature.MEMORIES to "记忆与照片",
                                            HomeFeature.MESSAGES to "家人留言",
                                            HomeFeature.NOTIFICATIONS to "家人通知",
                                            HomeFeature.CONVERSATION to "交流回顾"
                                        ).forEach { (feat, label) ->
                                            Surface(
                                                shape = CircleShape,
                                                color = FPaperCard,
                                                modifier = Modifier
                                                    .weight(1f)
                                                    .height(34.dp)
                                                    .clip(CircleShape)
                                                    .clickable {
                                                        familySettingSheetOpen = false
                                                        feature = feat
                                                    }
                                            ) {
                                                Box(contentAlignment = Alignment.Center) {
                                                    Text(text = label, fontSize = 12.sp, fontWeight = FontWeight.Medium, color = FInk)
                                                }
                                            }
                                        }
                                    }
                                }
                            }
                            Spacer(modifier = Modifier.height(10.dp))
                        }
                        Surface(
                            shape = CircleShape,
                            color = FPaperDeep,
                            modifier = Modifier
                                .fillMaxWidth()
                                .height(48.dp)
                                .clip(CircleShape)
                                .clickable {
                                    familySettingSheetOpen = false
                                    onOpenFamilySettings()
                                }
                        ) {
                            Box(contentAlignment = Alignment.Center) {
                                Text(text = "打开联机与原功能全量控制台（提醒/记忆/摘要/通知）", fontSize = 14.sp, fontWeight = FontWeight.Medium, color = FInk)
                            }
                        }
                        Spacer(modifier = Modifier.height(10.dp))
                        Button(
                            onClick = { familySettingSheetOpen = false },
                            colors = ButtonDefaults.buttonColors(containerColor = FInk, contentColor = FPaper),
                            shape = CircleShape,
                            modifier = Modifier
                                .fillMaxWidth()
                                .height(52.dp)
                        ) {
                            Text(text = "好的", fontSize = 16.sp, fontWeight = FontWeight.Bold)
                        }
                    }
                }
            }
        }

        feature?.let { target ->
            HomeFeatureSheet(target, state, models, subjects.filter { it.first == subjectId }.ifEmpty { subjects }, false) {
                feature = null
            }
        }
    }
}
