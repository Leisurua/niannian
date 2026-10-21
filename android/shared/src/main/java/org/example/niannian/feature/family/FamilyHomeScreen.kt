package org.example.niannian.feature.family

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.slideInVertically
import androidx.compose.animation.slideOutVertically
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.aspectRatio
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
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import org.example.niannian.shared.R
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
    val subject = subjects.firstOrNull()
    val subjectId = subject?.first.orEmpty()
    var feature by remember(state.userId, family) { mutableStateOf<HomeFeature?>(null) }
    val remindersState by models.reminders.state.collectAsState()
    val memoriesState by models.memories.state.collectAsState()
    val toolsState by models.tools.state.collectAsState()
    BindHomeModels(state, model, models, subjectId, feature)

    var activeTab by remember { mutableStateOf(FamilyNavTab.CARE) }
    var toast by remember { mutableStateOf<String?>(null) }

    var postSheetOpen by remember { mutableStateOf(false) }
    var postDraft by remember { mutableStateOf("") }

    var addReminderSheetOpen by remember { mutableStateOf(false) }
    var newRemTime by remember { mutableStateOf("17:30") }
    var newRemTitle by remember { mutableStateOf("") }

    var familySettingSheetOpen by remember { mutableStateOf(false) }

    val momReminders = homeFamilyReminderRows(state, remindersState, subjectId)
    val backendMemories = homeMemoryItems(state, memoriesState).filter { it.subject == subjectId }
    val memoryCandidates = backendMemories.map { item ->
        val confirmed = item.status == "CONFIRMED"
        FamilyMemoryCandidateRow(item.id, item.title, item.content,
            if (confirmed) "已人工核对 · 存入家庭记忆库" else "由小念对话提炼 · 待家属核对", confirmed)
    }

    LaunchedEffect(toast) {
        if (toast != null) {
            delay(2600)
            toast = null
        }
    }

    val childName = state.userName.takeIf { it.isNotBlank() && it != "演示子女" } ?: "小雨"

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
                                } else "王阿姨家 · 3人",
                                fontSize = 13.sp,
                                fontWeight = FontWeight.Medium,
                                color = if (state.loggedIn) FSage700 else FInk,
                                modifier = Modifier.padding(horizontal = 13.dp, vertical = 8.dp)
                            )
                        }
                    }

                    Spacer(modifier = Modifier.height(18.dp))
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween
                    ) {
                        Text(
                            text = "妈妈在 杭州·西湖区",
                            fontSize = 14.sp,
                            color = FInkMute
                        )
                        Text(
                            text = "☀ 22° 晴转多云 · 宜散步",
                            fontSize = 14.sp,
                            color = FInkSoft
                        )
                    }

                    Spacer(modifier = Modifier.height(6.dp))
                    Text(
                        text = "下午好，$childName",
                        fontFamily = FontFamily.Serif,
                        fontWeight = FontWeight.Bold,
                        fontSize = 30.sp,
                        color = FInk
                    )
                    Text(
                        text = "妈妈今天上午散了步，精神头很不错。",
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
                                            text = when {
                                                state.offline -> "● 当前离线 · 等待重新连接"
                                                state.error.isNotBlank() || family.isBlank() -> "● 连接或授权待确认"
                                                else -> "● 已联机 · 正在守护家人"
                                            },
                                            fontSize = 12.sp,
                                            fontWeight = FontWeight.Medium,
                                            color = Color.White,
                                            modifier = Modifier.padding(horizontal = 11.dp, vertical = 4.dp)
                                        )
                                    }
                                    Spacer(modifier = Modifier.height(10.dp))
                                    Text(
                                        text = "妈妈 · 王阿姨",
                                        fontFamily = FontFamily.Serif,
                                        fontWeight = FontWeight.Bold,
                                        fontSize = 25.sp,
                                        color = FInk
                                    )
                                    Text(
                                        text = "小念 AI 温和陪伴中 · 今日无异常关注信号",
                                        fontSize = 14.sp,
                                        color = FInkSoft
                                    )
                                }

                                Box(modifier = Modifier.offset(x = 6.dp, y = (-6).dp)) {
                                    PersimmonCompanionOrb(size = 94.dp, listening = false)
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
                                    Triple("小念陪伴", "18 分钟", "聊了桂花糕"),
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
                                            text = "✦ 小念今日交流摘要（脱敏·无逐字稿）",
                                            fontSize = 12.sp,
                                            fontWeight = FontWeight.SemiBold,
                                            color = FPersimmon700,
                                            maxLines = 1
                                        )
                                        Text(
                                            text = "妈妈已授权",
                                            fontSize = 11.5.sp,
                                            color = FInkMute,
                                            maxLines = 1,
                                            softWrap = false
                                        )
                                    }
                                    Spacer(modifier = Modifier.height(6.dp))
                                    Text(
                                        text = if (toolsState.family == family && toolsState.summary.isNotBlank()) toolsState.summary else "“上午妈妈主动和小念聊起周末想给朵朵蒸桂花糕，询问了糯米粉配比；上午散步回来后精神饱满。”",
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
                                    onClick = { postSheetOpen = true },
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
                                    Text(text = "发照片 / 留言", fontSize = 15.5.sp, fontWeight = FontWeight.Bold, maxLines = 1, softWrap = false)
                                }

                                Button(
                                    onClick = { toast = "正在为您发起与「妈妈 · 王阿姨」的视频通话…" },
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
                                    Text(text = "视频通话", fontSize = 15.5.sp, fontWeight = FontWeight.Medium, maxLines = 1, softWrap = false)
                                }
                            }
                        }
                    }
                }

                Spacer(modifier = Modifier.height(30.dp))

                // 3. Mom's Voice Reply Section
                Column(modifier = Modifier.padding(horizontal = 24.dp)) {
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.Bottom
                    ) {
                        Column(modifier = Modifier.weight(1f)) {
                            Text(
                                text = "妈妈的回音",
                                fontFamily = FontFamily.Serif,
                                fontWeight = FontWeight.Bold,
                                fontSize = 22.sp,
                                color = FInk
                            )
                            Text(
                                text = "您寄出的照片，妈妈刚看过了",
                                fontSize = 13.5.sp,
                                color = FInkSoft,
                                maxLines = 1
                            )
                        }
                        Surface(shape = CircleShape, color = FPersimmon50) {
                            Text(
                                text = "♥ 妈妈已点「看到啦」",
                                fontSize = 12.sp,
                                fontWeight = FontWeight.SemiBold,
                                color = FPersimmon700,
                                maxLines = 1,
                                softWrap = false,
                                modifier = Modifier.padding(horizontal = 10.dp, vertical = 4.dp)
                            )
                        }
                    }
                }

                Spacer(modifier = Modifier.height(10.dp))

                Surface(
                    shape = RoundedCornerShape(28.dp),
                    color = FPaperCard,
                    shadowElevation = 2.dp,
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(horizontal = 16.dp)
                ) {
                    Column(modifier = Modifier.padding(16.dp)) {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Image(
                                painter = painterResource(id = R.drawable.family_photo),
                                contentDescription = "小雨分享的照片",
                                contentScale = ContentScale.Crop,
                                modifier = Modifier
                                    .width(88.dp)
                                    .height(66.dp)
                                    .clip(RoundedCornerShape(16.dp))
                            )
                            Spacer(modifier = Modifier.width(12.dp))
                            Column(modifier = Modifier.weight(1f)) {
                                Text(text = "您 1 小时前寄出的明信片", fontSize = 12.5.sp, color = FInkMute)
                                Text(
                                    text = "“妈，带朵朵去公园了，她非要摘柿子给外婆看…”",
                                    fontFamily = FontFamily.Serif,
                                    fontWeight = FontWeight.Bold,
                                    fontSize = 15.sp,
                                    maxLines = 1,
                                    overflow = TextOverflow.Ellipsis,
                                    color = FInk
                                )
                                Text(
                                    text = "♥ 妈妈在 15 分钟前点了「看到啦」并回了语音",
                                    fontSize = 12.5.sp,
                                    color = FSage700,
                                    fontWeight = FontWeight.Medium
                                )
                            }
                        }

                        Spacer(modifier = Modifier.height(12.dp))

                        Surface(
                            shape = RoundedCornerShape(20.dp),
                            color = FSage50,
                            modifier = Modifier.fillMaxWidth()
                        ) {
                            Column(modifier = Modifier.padding(14.dp)) {
                                Row(
                                    modifier = Modifier.fillMaxWidth(),
                                    horizontalArrangement = Arrangement.SpaceBetween
                                ) {
                                    Text(
                                        text = "🎙️ 妈妈通过小念发来的原声回复",
                                        fontSize = 13.sp,
                                        fontWeight = FontWeight.Bold,
                                        color = FSage700
                                    )
                                    Text(text = "0:11", fontFamily = FontFamily.Serif, fontSize = 13.sp, color = FSage700)
                                }
                                Spacer(modifier = Modifier.height(6.dp))
                                Text(
                                    text = "“小雨呀，照片我看到啦，朵朵举着大柿子真精神！周六早点回来，妈给你们炖排骨玉米汤！”",
                                    fontFamily = FontFamily.Serif,
                                    fontSize = 16.5.sp,
                                    lineHeight = 25.sp,
                                    color = FInk
                                )
                                Spacer(modifier = Modifier.height(10.dp))
                                Button(
                                    onClick = { toast = "正在播放妈妈的原声语音回复…" },
                                    colors = ButtonDefaults.buttonColors(
                                        containerColor = FSage700,
                                        contentColor = Color.White
                                    ),
                                    shape = CircleShape,
                                    modifier = Modifier
                                        .fillMaxWidth()
                                        .height(44.dp)
                                ) {
                                    Icon(imageVector = NianNianIcons.Play, contentDescription = null, modifier = Modifier.size(16.dp))
                                    Spacer(modifier = Modifier.width(6.dp))
                                    Text(text = "播放妈妈的原声语音 (11秒)", fontSize = 14.5.sp, fontWeight = FontWeight.Medium)
                                }
                            }
                        }
                    }
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
                            text = "妈妈的今日提醒",
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
                        Triple(FamilyNavTab.POST, "寄动态", NianNianIcons.MessageCircle),
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
                                        FamilyNavTab.POST -> postSheetOpen = true
                                        FamilyNavTab.SETTINGS -> familySettingSheetOpen = true
                                        FamilyNavTab.CARE -> {
                                            activeTab = tab
                                            scope.launch { scrollState.animateScrollTo(0) }
                                        }
                                        FamilyNavTab.MEMORIES -> {
                                            activeTab = tab
                                            scope.launch { scrollState.animateScrollTo(scrollState.maxValue) }
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

        // Send Postcard Sheet
        if (postSheetOpen) {
            Box(
                modifier = Modifier
                    .fillMaxSize()
                    .background(FInk.copy(alpha = 0.4f))
                    .clickable { postSheetOpen = false },
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
                            text = "寄张动态明信片给妈妈",
                            fontFamily = FontFamily.Serif,
                            fontWeight = FontWeight.Bold,
                            fontSize = 22.sp,
                            color = FInk
                        )
                        Spacer(modifier = Modifier.height(12.dp))
                        OutlinedTextField(
                            value = postDraft,
                            onValueChange = { postDraft = it },
                            label = { Text("写下想对妈妈说的话…") },
                            modifier = Modifier.fillMaxWidth()
                        )
                        Spacer(modifier = Modifier.height(14.dp))
                        Button(
                            onClick = {
                                postSheetOpen = false
                                postDraft = ""
                                toast = "已将照片与留言发送至妈妈首页"
                            },
                            colors = ButtonDefaults.buttonColors(containerColor = FPersimmon600, contentColor = Color.White),
                            shape = CircleShape,
                            contentPadding = PaddingValues(vertical = 14.dp),
                            modifier = Modifier.fillMaxWidth()
                        ) {
                            Text(text = "立即寄给妈妈", fontSize = 16.sp, fontWeight = FontWeight.Bold)
                        }
                    }
                }
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
                            text = "帮妈妈添加生活提醒",
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
                                val t = newRemTitle.ifBlank { "傍晚阳台收衣服" }
                                when {
                                    family.isBlank() || subjectId.isBlank() -> toast = "请先登录并选择已加入家庭的长辈。"
                                    state.offline || state.error.isNotBlank() || state.pendingWrite -> toast = "请恢复连接并核对授权后重试。"
                                    runCatching { LocalTime.parse(newRemTime) }.isFailure -> toast = "请按 HH:mm 填写有效时间。"
                                    else -> scope.launch {
                                        var saved = false
                                        models.reminders.save(subjectId, t, "小雨添加的贴心提醒", LocalDate.now().toString(),
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
                            Text(text = "保存并同步至妈妈手机", fontSize = 16.sp, fontWeight = FontWeight.Bold)
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
                                text = "王阿姨已本人授权开启：家庭记忆共创、健康与用药提醒、脱敏交流摘要与异常关注提示。为保护长辈尊严，系统不保存亦不提供原始对话录音或逐字稿。",
                                fontSize = 14.sp,
                                lineHeight = 22.sp,
                                color = FInkSoft,
                                modifier = Modifier.padding(16.dp)
                            )
                        }
                        Spacer(modifier = Modifier.height(12.dp))
                        if (!state.loggedIn && model != null) {
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
