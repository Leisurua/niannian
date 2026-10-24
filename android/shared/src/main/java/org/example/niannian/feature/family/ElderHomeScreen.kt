package org.example.niannian.feature.family

import android.icu.util.ChineseCalendar
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.core.FastOutSlowInEasing
import androidx.compose.animation.core.LinearEasing
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.slideInVertically
import androidx.compose.animation.slideOutVertically
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.IntrinsicSize
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
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
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.rotate
import androidx.compose.ui.draw.scale
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.DrawScope
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.drawscope.rotate
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextDecoration
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.TextUnit
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import org.example.niannian.feature.conversation.PersimmonCompanionOrb
import java.time.LocalDateTime
import java.time.format.DateTimeFormatter
import java.util.Locale
import kotlin.math.abs
import kotlin.math.ceil

// ============================================================================
// Brand Color Palette — "念念 · 柿柿如意" (Warm Paper, Persimmon & Sage)
// ============================================================================
private val Paper = Color(0xFFF6F1EA)
private val PaperDeep = Color(0xFFEFE7DC)
private val PaperCard = Color(0xFFFFFDF9)
private val Ink = Color(0xFF2A2420)
private val InkSoft = Color(0xFF5C524A)
private val InkMute = Color(0xFF857A70)
private val LineColor = Color(0xFFE6DDD1)

private val Persimmon50 = Color(0xFFFBEDE5)
private val Persimmon100 = Color(0xFFF6D9C8)
private val Persimmon300 = Color(0xFFE79B72)
private val Persimmon500 = Color(0xFFC8643B)
private val Persimmon600 = Color(0xFFB0532D)
private val Persimmon700 = Color(0xFF8F4224)

private val Sage50 = Color(0xFFEEF1EA)
private val Sage100 = Color(0xFFDCE3D4)
private val Sage500 = Color(0xFF6F7F62)
private val Sage700 = Color(0xFF4C5A42)

private val CompanionCardBg = Color(0xFFF9E3D3)
private val CompanionGlowBg = Color(0xFFFCD2B4)
private val SunWarmBg = Color(0xFFFCEBC9)
private val SunWarmIcon = Color(0xFFD9902A)

private enum class HomeNavTab { TODAY, CHAT, FAMILY, SETTINGS }
private enum class ReminderKind { PILL, WALK, WATER, CALL }

private data class HomeReminderItem(
    val id: String,
    val time: String,
    val title: String,
    val detail: String,
    val kind: ReminderKind,
    val done: Boolean
)

private val CN_MONTHS = arrayOf("正", "二", "三", "四", "五", "六", "七", "八", "九", "十", "冬", "腊")
private val CN_DAYS = arrayOf(
    "初一", "初二", "初三", "初四", "初五", "初六", "初七", "初八", "初九", "初十",
    "十一", "十二", "十三", "十四", "十五", "十六", "十七", "十八", "十九", "二十",
    "廿一", "廿二", "廿三", "廿四", "廿五", "廿六", "廿七", "廿八", "廿九", "三十"
)

private fun currentLunarString(): String = runCatching {
    val cal = ChineseCalendar()
    val m = cal.get(ChineseCalendar.MONTH).coerceIn(0, 11)
    val d = (cal.get(ChineseCalendar.DAY_OF_MONTH) - 1).coerceIn(0, 29)
    "农历${CN_MONTHS[m]}月${CN_DAYS[d]}"
}.getOrDefault("农历暂不可用")

private fun greetingForHour(hour: Int): String = when {
    hour < 5 -> "夜深了"
    hour < 11 -> "早上好"
    hour < 13 -> "中午好"
    hour < 18 -> "下午好"
    else -> "晚上好"
}

private fun Float.spScaled(scale: Float): TextUnit = (this * scale).sp

// ============================================================================
// Main Elder Home Composable
// ============================================================================
@Composable
internal fun ElderDesignHome(
    state: CompanionState,
    model: CompanionModel,
    models: HomeModels,
    offlineContent: @Composable () -> Unit = {},
    onOpenFamilySettings: () -> Unit
) {
    val scrollState = rememberScrollState()
    val coroutineScope = rememberCoroutineScope()

    var activeTab by remember { mutableStateOf(HomeNavTab.TODAY) }
    var textScale by remember { mutableFloatStateOf(1.0f) }
    var feature by remember(state.userId, state.selected?.id) { mutableStateOf<HomeFeature?>(null) }
    var recapId by remember(state.userId, state.selected?.id) { mutableStateOf("") }
    val remindersState by models.reminders.state.collectAsState()
    val subjects = homeSubjects(state, true)
    BindHomeModels(state, model, models, state.userId, feature)
    val backendCards = homeCurrentReminderCards(state, remindersState)
    val reminders = backendCards.map { card ->
        val shortTime = java.time.ZonedDateTime.parse(card.time).format(DateTimeFormatter.ofPattern("HH:mm"))
        val kind = when {
            card.medication -> ReminderKind.PILL
            "水" in card.title -> ReminderKind.WATER
            "散步" in card.title -> ReminderKind.WALK
            else -> ReminderKind.CALL
        }
        HomeReminderItem(card.key, shortTime, card.title, card.content, kind, card.status == "DONE")
    }

    var startWithVoice by remember { mutableStateOf(false) }
    var chatTopic by remember { mutableStateOf<String?>(null) }
    var settingsOpen by remember { mutableStateOf(false) }

    var toastMessage by remember { mutableStateOf<String?>(null) }
    var now by remember { mutableStateOf(LocalDateTime.now()) }

    LaunchedEffect(Unit) {
        while (true) {
            delay(15_000)
            now = LocalDateTime.now()
        }
    }

    LaunchedEffect(toastMessage) {
        if (toastMessage != null) {
            delay(2600)
            toastMessage = null
        }
    }

    val elderDisplayName = state.userName.ifBlank { "您好" }

    Box(
        modifier = Modifier
            .fillMaxSize()
            .background(Paper)
    ) {
        Column(modifier = Modifier.fillMaxSize()) {
            // Scrollable Home Content
            Column(
                modifier = Modifier
                    .weight(1f)
                    .verticalScroll(scrollState)
                    .padding(bottom = 36.dp)
            ) {
                // 1. Welcome Header
                ElderWelcomeHeader(
                    now = now,
                    elderName = elderDisplayName,
                    scale = textScale,
                    onToggleScale = {
                        textScale = if (textScale > 1.0f) 1.0f else 1.15f
                    }
                )

                Column(Modifier.padding(horizontal = 24.dp, vertical = 12.dp)) {
                    HomeWeatherCard("${state.userId}:${homeFamily(state)}:${state.userId}", textScale)
                }

                Spacer(modifier = Modifier.height(26.dp))

                // 2. AI Companion Hero Card
                ElderCompanionCard(
                    scale = textScale,
                    onStartChat = { topic ->
                        chatTopic = topic
                        startWithVoice = topic == null
                        feature = HomeFeature.CHAT
                    },
                    onOpenIdentityInfo = {
                        settingsOpen = true
                    }
                )

                Spacer(modifier = Modifier.height(36.dp))

                // 3. Today's Reminders ("The Day's Thread")
                ElderRemindersTimeline(
                    items = reminders,
                    scale = textScale,
                    onToggle = { id ->
                        val card = backendCards.find { it.key == id }
                        when {
                            card == null || card.status == "DONE" -> Unit
                            !card.due -> toastMessage = "这条提醒还未到时间。"
                            else -> coroutineScope.launch {
                                models.reminders.feedback(card.key, "DONE")?.join()
                                val result = models.reminders.state.value
                                if (result.family == homeFamily(state) && result.user == state.userId) {
                                    toastMessage = result.error.ifBlank { result.message }
                                }
                            }
                        }
                    }
                )

                Spacer(modifier = Modifier.height(36.dp))

                Column(Modifier.padding(horizontal = 16.dp)) {
                    HomeMessagesSection(state, models.messages, textScale,
                        onOpen = { feature = HomeFeature.MESSAGES },
                        onPhotos = { feature = HomeFeature.MEMORIES })
                }

                // Editorial Footer
                Spacer(modifier = Modifier.height(42.dp))
                Column(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalAlignment = Alignment.CenterHorizontally
                ) {
                    Box(
                        modifier = Modifier
                            .width(40.dp)
                            .height(1.dp)
                            .background(LineColor)
                    )
                    Spacer(modifier = Modifier.height(10.dp))
                    Text(
                        text = "念念不忘 · 必有回响",
                        fontFamily = FontFamily.Serif,
                        fontSize = 15f.spScaled(textScale),
                        letterSpacing = 4.sp,
                        color = InkMute
                    )
                }
            }

            // 5. Material 3 Bottom Navigation Bar
            ElderBottomNavBar(
                activeTab = activeTab,
                scale = textScale,
                onSelectTab = { tab ->
                    when (tab) {
                        HomeNavTab.CHAT -> {
                            chatTopic = null
                            startWithVoice = false
                            feature = HomeFeature.CHAT
                        }
                        HomeNavTab.SETTINGS -> {
                            settingsOpen = true
                        }
                        HomeNavTab.TODAY -> {
                            activeTab = HomeNavTab.TODAY
                            coroutineScope.launch {
                                scrollState.animateScrollTo(0)
                            }
                        }
                        HomeNavTab.FAMILY -> {
                            activeTab = HomeNavTab.FAMILY
                            feature = HomeFeature.MESSAGES
                        }
                    }
                }
            )
        }

        // Snackbar Toast Overlay
        AnimatedVisibility(
            visible = toastMessage != null,
            enter = fadeIn() + slideInVertically { it / 2 },
            exit = fadeOut() + slideOutVertically { it / 2 },
            modifier = Modifier
                .align(Alignment.BottomCenter)
                .padding(horizontal = 20.dp, vertical = 96.dp)
        ) {
            Surface(
                shape = RoundedCornerShape(18.dp),
                color = Ink,
                shadowElevation = 10.dp
            ) {
                Text(
                    text = toastMessage.orEmpty(),
                    color = Paper,
                    fontSize = 16f.spScaled(textScale),
                    fontWeight = FontWeight.Medium,
                    modifier = Modifier.padding(horizontal = 20.dp, vertical = 14.dp)
                )
            }
        }

        // Bottom Settings & AI Transparency Sheet
        if (settingsOpen) {
            ElderSettingsSheet(
                scale = textScale,
                state = state,
                onQuickUsbLogin = {
                    model.login("http://127.0.0.1:8000")
                    toastMessage = "正在通过 USB 隧道连接本机后端 (127.0.0.1:8000)…"
                },
                onSelectScale = { textScale = it },
                onOpenFeature = { target ->
                    settingsOpen = false
                    feature = target
                },
                onOpenBackendConsole = {
                    settingsOpen = false
                    onOpenFamilySettings()
                },
                onClose = { settingsOpen = false }
            )
        }

        feature?.let { target ->
            HomeFeatureSheet(target, state, models, subjects, true, chatTopic, recapId, startWithVoice) {
                if (target == HomeFeature.CHAT) recapId = models.conversation?.state?.value?.recapId.orEmpty()
                feature = null
            }
        }

    }
}

// ============================================================================
// 1. Welcome Header Component
// ============================================================================
@Composable
private fun ElderWelcomeHeader(
    now: LocalDateTime,
    elderName: String,
    scale: Float,
    onToggleScale: () -> Unit
) {
    val dateStr = remember(now) {
        now.format(DateTimeFormatter.ofPattern("M月d日 EEEE", Locale.CHINA))
    }
    val timeStr = remember(now) {
        now.format(DateTimeFormatter.ofPattern("HH:mm", Locale.CHINA))
    }
    val lunarStr = remember(now.toLocalDate()) { currentLunarString() }
    val isLarge = scale > 1.0f

    Column(
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = 24.dp)
            .padding(top = 14.dp)
    ) {
        // Brand Logo & Large-Font Switch Pill
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
                        .background(Persimmon500),
                    contentAlignment = Alignment.Center
                ) {
                    Text(
                        text = "念",
                        fontFamily = FontFamily.Serif,
                        fontWeight = FontWeight.Bold,
                        fontSize = 16f.spScaled(scale),
                        color = Color.White
                    )
                }
                Spacer(modifier = Modifier.width(9.dp))
                Text(
                    text = "念念",
                    fontFamily = FontFamily.Serif,
                    fontWeight = FontWeight.Bold,
                    fontSize = 19f.spScaled(scale),
                    letterSpacing = 3.sp,
                    color = Ink
                )
            }

            Surface(
                shape = CircleShape,
                color = if (isLarge) Ink else PaperDeep,
                modifier = Modifier
                    .height(46.dp)
                    .clip(CircleShape)
                    .clickable { onToggleScale() }
            ) {
                Row(
                    modifier = Modifier.padding(horizontal = 16.dp),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Icon(
                        imageVector = NianNianIcons.Type,
                        contentDescription = null,
                        tint = if (isLarge) Paper else Ink,
                        modifier = Modifier.size(18.dp)
                    )
                    Spacer(modifier = Modifier.width(6.dp))
                    Text(
                        text = if (isLarge) "标准字" else "大字",
                        fontSize = 15f.spScaled(scale),
                        fontWeight = FontWeight.Medium,
                        color = if (isLarge) Paper else Ink
                    )
                }
            }
        }

        Spacer(modifier = Modifier.height(22.dp))

        // Date | Time | Lunar
        Text(
            text = "$dateStr  |  $timeStr  |  $lunarStr",
            fontSize = 15f.spScaled(scale),
            color = InkMute
        )

        Spacer(modifier = Modifier.height(8.dp))

        // Two-line Serif Greeting
        Text(
            text = "${greetingForHour(now.hour)}，\n$elderName",
            fontFamily = FontFamily.Serif,
            fontWeight = FontWeight.Bold,
            fontSize = 34f.spScaled(scale),
            lineHeight = 43f.spScaled(scale),
            color = Ink
        )

        Spacer(modifier = Modifier.height(18.dp))

    }
}

// ============================================================================
// 2. AI Companion Hero Card & Persimmon CompanionOrb Canvas
// ============================================================================
@Composable
private fun ElderCompanionCard(
    scale: Float,
    onStartChat: (String?) -> Unit,
    onOpenIdentityInfo: () -> Unit
) {
    val suggestions = remember { listOf("讲讲桂花糕", "今天听什么戏", "陪我说说话") }

    Surface(
        shape = RoundedCornerShape(32.dp),
        color = CompanionCardBg,
        shadowElevation = 4.dp,
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = 16.dp)
    ) {
        Box(modifier = Modifier.fillMaxWidth()) {
            // Soft sunrise radial glow in top-right corner
            Canvas(modifier = Modifier.matchParentSize()) {
                drawCircle(
                    brush = Brush.radialGradient(
                        colors = listOf(CompanionGlowBg.copy(alpha = 0.85f), Color.Transparent),
                        center = Offset(size.width * 0.88f, size.height * 0.12f),
                        radius = size.width * 0.55f
                    ),
                    radius = size.width * 0.55f,
                    center = Offset(size.width * 0.88f, size.height * 0.12f)
                )
            }

            Column(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(start = 20.dp, end = 20.dp, top = 22.dp, bottom = 20.dp)
            ) {
                // Top Row: Badge + Name on left, Persimmon Orb on right
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.Top
                ) {
                    Column(
                        modifier = Modifier
                            .weight(1f)
                            .padding(top = 4.dp)
                    ) {
                        // Explicit AI Pill Badge
                        Surface(
                            shape = CircleShape,
                            color = Ink
                        ) {
                            Row(
                                modifier = Modifier.padding(horizontal = 10.dp, vertical = 5.dp),
                                verticalAlignment = Alignment.CenterVertically
                            ) {
                                Box(
                                    modifier = Modifier
                                        .clip(RoundedCornerShape(5.dp))
                                        .background(Persimmon300)
                                        .padding(horizontal = 5.dp, vertical = 1.dp)
                                ) {
                                    Text(
                                        text = "AI",
                                        fontSize = 11f.spScaled(scale),
                                        fontWeight = FontWeight.Bold,
                                        color = Ink
                                    )
                                }
                                Spacer(modifier = Modifier.width(6.dp))
                                Text(
                                    text = "念念 AI 陪伴",
                                    fontSize = 13f.spScaled(scale),
                                    fontWeight = FontWeight.Medium,
                                    color = Paper
                                )
                            }
                        }

                        Spacer(modifier = Modifier.height(12.dp))
                        Text(
                            text = "小念",
                            fontFamily = FontFamily.Serif,
                            fontWeight = FontWeight.Bold,
                            fontSize = 28f.spScaled(scale),
                            color = Ink
                        )
                        Spacer(modifier = Modifier.height(2.dp))
                        Text(
                            text = "在呢，随时陪您说说话",
                            fontSize = 15f.spScaled(scale),
                            color = InkSoft
                        )
                    }

                    Box(
                        modifier = Modifier
                            .offset(x = 8.dp, y = (-10).dp)
                    ) {
                        PersimmonCompanionOrb(size = 148.dp, modifier = Modifier.clickable(
                            onClickLabel = "和念念说话", role = androidx.compose.ui.semantics.Role.Button
                        ) { onStartChat(null) })
                    }
                }

                // Speech Bubble — What 小念 remembers
                Surface(
                    shape = RoundedCornerShape(
                        topStart = 6.dp,
                        topEnd = 22.dp,
                        bottomEnd = 22.dp,
                        bottomStart = 22.dp
                    ),
                    color = PaperCard.copy(alpha = 0.92f),
                    modifier = Modifier.fillMaxWidth()
                ) {
                    Text(
                        text = "我是念念 AI 陪伴。点我的形象或开始聊天，可以说话，也可以打字。",
                        fontFamily = FontFamily.Serif,
                        fontSize = 19f.spScaled(scale),
                        lineHeight = 30f.spScaled(scale),
                        color = Ink,
                        modifier = Modifier.padding(horizontal = 16.dp, vertical = 14.dp)
                    )
                }

                Spacer(modifier = Modifier.height(16.dp))

                // Prominent "开始聊天" CTA Button
                val micPulseTransition = rememberInfiniteTransition(label = "micPulse")
                val micRippleScale by micPulseTransition.animateFloat(
                    initialValue = 0.85f,
                    targetValue = 1.65f,
                    animationSpec = infiniteRepeatable(
                        animation = tween(2400, easing = FastOutSlowInEasing),
                        repeatMode = RepeatMode.Restart
                    ),
                    label = "micRippleScale"
                )
                val micRippleAlpha by micPulseTransition.animateFloat(
                    initialValue = 0.5f,
                    targetValue = 0f,
                    animationSpec = infiniteRepeatable(
                        animation = tween(2400, easing = FastOutSlowInEasing),
                        repeatMode = RepeatMode.Restart
                    ),
                    label = "micRippleAlpha"
                )

                Button(
                    onClick = { onStartChat(null) },
                    colors = ButtonDefaults.buttonColors(
                        containerColor = Persimmon600,
                        contentColor = Color.White
                    ),
                    shape = CircleShape,
                    contentPadding = PaddingValues(horizontal = 24.dp),
                    modifier = Modifier
                        .fillMaxWidth()
                        .height(68.dp)
                        .shadow(12.dp, CircleShape, spotColor = Persimmon700)
                ) {
                    Box(
                        contentAlignment = Alignment.Center,
                        modifier = Modifier.size(40.dp)
                    ) {
                        Box(
                            modifier = Modifier
                                .size(40.dp)
                                .scale(micRippleScale)
                                .clip(CircleShape)
                                .background(Color.White.copy(alpha = micRippleAlpha))
                        )
                        Box(
                            modifier = Modifier
                                .size(40.dp)
                                .clip(CircleShape)
                                .background(Color.White.copy(alpha = 0.22f)),
                            contentAlignment = Alignment.Center
                        ) {
                            Icon(
                                imageVector = NianNianIcons.Mic,
                                contentDescription = null,
                                tint = Color.White,
                                modifier = Modifier.size(22.dp)
                            )
                        }
                    }
                    Spacer(modifier = Modifier.width(12.dp))
                    Text(
                        text = "开始聊天",
                        fontSize = 21f.spScaled(scale),
                        fontWeight = FontWeight.Bold,
                        letterSpacing = 2.sp
                    )
                }

                Spacer(modifier = Modifier.height(12.dp))

                // Suggestion Chips
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .horizontalScroll(rememberScrollState()),
                    horizontalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    suggestions.forEach { topic ->
                        Surface(
                            shape = CircleShape,
                            color = Color.White.copy(alpha = 0.55f),
                            border = BorderStroke(1.dp, Persimmon300.copy(alpha = 0.75f)),
                            modifier = Modifier
                                .height(44.dp)
                                .clip(CircleShape)
                                .clickable { onStartChat(topic) }
                        ) {
                            Box(
                                contentAlignment = Alignment.Center,
                                modifier = Modifier.padding(horizontal = 16.dp)
                            ) {
                                Text(
                                    text = topic,
                                    fontSize = 15f.spScaled(scale),
                                    color = Persimmon700,
                                    fontWeight = FontWeight.Medium
                                )
                            }
                        }
                    }
                }

                Spacer(modifier = Modifier.height(14.dp))

                // Mandatory AI Identity Footnote
                Row(
                    verticalAlignment = Alignment.CenterVertically,
                    modifier = Modifier
                        .fillMaxWidth()
                        .clickable { onOpenIdentityInfo() }
                        .padding(vertical = 2.dp)
                ) {
                    Icon(
                        imageVector = NianNianIcons.ShieldCheck,
                        contentDescription = null,
                        tint = Sage700,
                        modifier = Modifier.size(16.dp)
                    )
                    Spacer(modifier = Modifier.width(6.dp))
                    Text(
                        text = "小念是 AI 助手，不是您的家人",
                        fontSize = 13.5f.spScaled(scale),
                        color = InkSoft
                    )
                }
            }
        }
    }
}

// ============================================================================
// 3. Today's Reminders — "The Day's Thread" Timeline
// ============================================================================
@Composable
private fun ElderRemindersTimeline(
    items: List<HomeReminderItem>,
    scale: Float,
    onToggle: (String) -> Unit
) {
    val doneCount = items.count { it.done }
    val nextId = items.firstOrNull { !it.done }?.id

    val pulseTransition = rememberInfiniteTransition(label = "nextPulse")
    val nextRippleScale by pulseTransition.animateFloat(
        initialValue = 1f,
        targetValue = 2.2f,
        animationSpec = infiniteRepeatable(
            animation = tween(2200, easing = FastOutSlowInEasing),
            repeatMode = RepeatMode.Restart
        ),
        label = "nextRippleScale"
    )
    val nextRippleAlpha by pulseTransition.animateFloat(
        initialValue = 0.65f,
        targetValue = 0f,
        animationSpec = infiniteRepeatable(
            animation = tween(2200, easing = FastOutSlowInEasing),
            repeatMode = RepeatMode.Restart
        ),
        label = "nextRippleAlpha"
    )

    Column(modifier = Modifier.fillMaxWidth()) {
        // Section Header
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 24.dp),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.Bottom
        ) {
            Text(
                text = "今日提醒",
                fontFamily = FontFamily.Serif,
                fontWeight = FontWeight.Bold,
                fontSize = 24f.spScaled(scale),
                color = Ink
            )
            Row(verticalAlignment = Alignment.Bottom) {
                Text(
                    text = "已完成 ",
                    fontSize = 15f.spScaled(scale),
                    color = InkMute
                )
                Text(
                    text = "$doneCount",
                    fontFamily = FontFamily.Serif,
                    fontWeight = FontWeight.Bold,
                    fontSize = 16f.spScaled(scale),
                    color = Ink
                )
                Text(
                    text = " / ${items.size}",
                    fontSize = 15f.spScaled(scale),
                    color = InkMute
                )
            }
        }

        Spacer(modifier = Modifier.height(4.dp))
        Text(
            text = "不着急，按自己的节奏来就好。",
            fontSize = 15f.spScaled(scale),
            color = InkSoft,
            modifier = Modifier.padding(horizontal = 24.dp)
        )

        Spacer(modifier = Modifier.height(16.dp))

        // Timeline List
        Box(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 12.dp)
        ) {
            Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                items.forEachIndexed { index, item ->
                    val isNext = item.id == nextId
                    val icon = when (item.kind) {
                        ReminderKind.PILL -> NianNianIcons.Pill
                        ReminderKind.WALK -> NianNianIcons.Footprints
                        ReminderKind.WATER -> NianNianIcons.Droplet
                        ReminderKind.CALL -> NianNianIcons.Video
                    }

                    Row(
                        modifier = Modifier
                            .fillMaxWidth()
                            .height(IntrinsicSize.Min),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        // Time Column
                        Text(
                            text = item.time,
                            fontFamily = FontFamily.Serif,
                            fontWeight = if (item.done) FontWeight.Normal else FontWeight.Bold,
                            fontSize = 16f.spScaled(scale),
                            color = if (item.done) InkMute else Ink,
                            modifier = Modifier.width(48.dp)
                        )

                        // Thread & Node Column
                        Box(
                            modifier = Modifier
                                .width(22.dp)
                                .fillMaxHeight(),
                            contentAlignment = Alignment.Center
                        ) {
                            Canvas(modifier = Modifier.fillMaxSize()) {
                                val cx = size.width / 2f
                                val startY = if (index == 0) size.height / 2f else 0f
                                val endY = if (index == items.lastIndex) size.height / 2f else size.height
                                drawLine(
                                    color = Color(0xFFD9CCBD),
                                    start = Offset(cx, startY),
                                    end = Offset(cx, endY),
                                    strokeWidth = 1.5.dp.toPx(),
                                    pathEffect = PathEffect.dashPathEffect(floatArrayOf(10f, 10f), 0f)
                                )
                            }

                            if (isNext) {
                                Box(
                                    modifier = Modifier
                                        .size(14.dp)
                                        .scale(nextRippleScale)
                                        .clip(CircleShape)
                                        .background(Persimmon300.copy(alpha = nextRippleAlpha))
                                )
                            }

                            Box(
                                modifier = Modifier
                                    .size(14.dp)
                                    .clip(CircleShape)
                                    .background(if (item.done) Sage500 else Paper)
                                    .border(
                                        width = 2.dp,
                                        color = when {
                                            item.done -> Sage500
                                            isNext -> Persimmon500
                                            else -> Color(0xFFCDBFAF)
                                        },
                                        shape = CircleShape
                                    )
                            )
                        }

                        Spacer(modifier = Modifier.width(6.dp))

                        // Reminder Content Card/Row
                        Surface(
                            shape = RoundedCornerShape(22.dp),
                            color = if (isNext) PaperCard else Color.Transparent,
                            shadowElevation = if (isNext) 3.dp else 0.dp,
                            modifier = Modifier
                                .weight(1f)
                                .heightIn(min = 66.dp)
                        ) {
                            Row(
                                modifier = Modifier
                                    .fillMaxWidth()
                                    .padding(start = 10.dp, end = 8.dp, top = 10.dp, bottom = 10.dp),
                                verticalAlignment = Alignment.CenterVertically
                            ) {
                                Box(
                                    modifier = Modifier
                                        .size(40.dp)
                                        .clip(RoundedCornerShape(14.dp))
                                        .background(
                                            when {
                                                item.done -> Sage50
                                                isNext -> Persimmon50
                                                else -> PaperDeep
                                            }
                                        ),
                                    contentAlignment = Alignment.Center
                                ) {
                                    Icon(
                                        imageVector = icon,
                                        contentDescription = null,
                                        tint = when {
                                            item.done -> Sage500
                                            isNext -> Persimmon600
                                            else -> InkSoft
                                        },
                                        modifier = Modifier.size(20.dp)
                                    )
                                }

                                Spacer(modifier = Modifier.width(10.dp))

                                Column(modifier = Modifier.weight(1f)) {
                                    Row(verticalAlignment = Alignment.CenterVertically) {
                                        Text(
                                            text = item.title,
                                            fontSize = 16.5f.spScaled(scale),
                                            fontWeight = FontWeight.Medium,
                                            color = if (item.done) InkMute else Ink,
                                            textDecoration = if (item.done) TextDecoration.LineThrough else TextDecoration.None,
                                            maxLines = 1,
                                            softWrap = false
                                        )
                                        if (isNext) {
                                            Spacer(modifier = Modifier.width(6.dp))
                                            Surface(
                                                shape = CircleShape,
                                                color = Persimmon50
                                            ) {
                                                Text(
                                                    text = "接下来",
                                                    fontSize = 11f.spScaled(scale),
                                                    fontWeight = FontWeight.Medium,
                                                    color = Persimmon700,
                                                    maxLines = 1,
                                                    softWrap = false,
                                                    modifier = Modifier.padding(horizontal = 7.dp, vertical = 2.dp)
                                                )
                                            }
                                        }
                                    }
                                    Text(
                                        text = item.detail,
                                        fontSize = 14f.spScaled(scale),
                                        color = InkMute,
                                        maxLines = 1,
                                        overflow = TextOverflow.Ellipsis
                                    )
                                }

                                Spacer(modifier = Modifier.width(6.dp))

                                // Completion Check Button
                                Box(
                                    modifier = Modifier
                                        .size(44.dp)
                                        .clip(CircleShape)
                                        .background(if (item.done) Sage500 else Color.Transparent)
                                        .border(
                                            width = if (item.done) 0.dp else 2.dp,
                                            color = if (item.done) Color.Transparent else Color(0xFFD9CCBD),
                                            shape = CircleShape
                                        )
                                        .clickable { onToggle(item.id) },
                                    contentAlignment = Alignment.Center
                                ) {
                                    if (item.done) {
                                        Icon(
                                            imageVector = NianNianIcons.Check,
                                            contentDescription = "已完成",
                                            tint = Color.White,
                                            modifier = Modifier.size(22.dp)
                                        )
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}

// ============================================================================
// ============================================================================
@Composable
private fun ElderBottomNavBar(
    activeTab: HomeNavTab,
    scale: Float,
    onSelectTab: (HomeNavTab) -> Unit
) {
    val tabs = listOf(
        Triple(HomeNavTab.TODAY, "今日", NianNianIcons.Sun),
        Triple(HomeNavTab.CHAT, "聊聊", NianNianIcons.MessageCircle),
        Triple(HomeNavTab.FAMILY, "家人记忆", NianNianIcons.HeartHandshake),
        Triple(HomeNavTab.SETTINGS, "设置", NianNianIcons.Settings)
    )

    Surface(
        color = PaperCard.copy(alpha = 0.96f),
        shadowElevation = 8.dp,
        modifier = Modifier.fillMaxWidth()
    ) {
        Column(modifier = Modifier.fillMaxWidth()) {
            Box(
                modifier = Modifier
                    .fillMaxWidth()
                    .height(1.dp)
                    .background(LineColor)
            )
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(top = 8.dp, bottom = 12.dp),
                horizontalArrangement = Arrangement.SpaceAround
            ) {
                tabs.forEach { (tab, label, icon) ->
                    val selected = tab == activeTab
                    Column(
                        horizontalAlignment = Alignment.CenterHorizontally,
                        modifier = Modifier
                            .weight(1f)
                            .clickable { onSelectTab(tab) }
                            .padding(vertical = 4.dp)
                    ) {
                        Box(
                            modifier = Modifier
                                .width(64.dp)
                                .height(36.dp)
                                .clip(CircleShape)
                                .background(if (selected) Persimmon100 else Color.Transparent),
                            contentAlignment = Alignment.Center
                        ) {
                            Icon(
                                imageVector = icon,
                                contentDescription = label,
                                tint = if (selected) Persimmon700 else InkSoft,
                                modifier = Modifier.size(24.dp)
                            )
                        }
                        Spacer(modifier = Modifier.height(4.dp))
                        Text(
                            text = label,
                            fontSize = 14f.spScaled(scale),
                            fontWeight = if (selected) FontWeight.Bold else FontWeight.Normal,
                            color = if (selected) Ink else InkSoft
                        )
                    }
                }
            }
        }
    }
}

// ============================================================================
// 7. Quick Settings & AI Transparency Sheet
// ============================================================================
@Composable
private fun ElderSettingsSheet(
    scale: Float,
    state: CompanionState,
    onQuickUsbLogin: () -> Unit,
    onSelectScale: (Float) -> Unit,
    onOpenFeature: (HomeFeature) -> Unit = {},
    onOpenBackendConsole: () -> Unit,
    onClose: () -> Unit
) {
    val loggedIn = state.loggedIn
    val sizes = listOf(
        1.0f to "标准",
        1.15f to "大",
        1.3f to "特大"
    )

    Box(
        modifier = Modifier
            .fillMaxSize()
            .background(Ink.copy(alpha = 0.38f))
            .clickable { onClose() },
        contentAlignment = Alignment.BottomCenter
    ) {
        Surface(
            shape = RoundedCornerShape(topStart = 32.dp, topEnd = 32.dp),
            color = PaperCard,
            modifier = Modifier
                .fillMaxWidth()
                .clickable(enabled = false) {}
        ) {
            Column(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 24.dp, vertical = 16.dp)
            ) {
                Box(
                    modifier = Modifier
                        .width(40.dp)
                        .height(6.dp)
                        .clip(CircleShape)
                        .background(LineColor)
                        .align(Alignment.CenterHorizontally)
                )

                Spacer(modifier = Modifier.height(20.dp))
                Text(
                    text = "快捷设置",
                    fontFamily = FontFamily.Serif,
                    fontWeight = FontWeight.Bold,
                    fontSize = 24f.spScaled(scale),
                    color = Ink
                )

                Spacer(modifier = Modifier.height(18.dp))
                Text(
                    text = "文字大小",
                    fontSize = 15f.spScaled(scale),
                    color = InkSoft
                )
                Spacer(modifier = Modifier.height(8.dp))

                Surface(
                    shape = CircleShape,
                    color = PaperDeep,
                    modifier = Modifier.fillMaxWidth()
                ) {
                    Row(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(6.dp),
                        horizontalArrangement = Arrangement.spacedBy(8.dp)
                    ) {
                        sizes.forEach { (value, label) ->
                            val selected = abs(scale - value) < 0.03f
                            Surface(
                                shape = CircleShape,
                                color = if (selected) PaperCard else Color.Transparent,
                                shadowElevation = if (selected) 2.dp else 0.dp,
                                modifier = Modifier
                                    .weight(1f)
                                    .height(48.dp)
                                    .clip(CircleShape)
                                    .clickable { onSelectScale(value) }
                            ) {
                                Row(
                                    modifier = Modifier.fillMaxSize(),
                                    horizontalArrangement = Arrangement.Center,
                                    verticalAlignment = Alignment.CenterVertically
                                ) {
                                    if (selected) {
                                        Icon(
                                            imageVector = NianNianIcons.Check,
                                            contentDescription = null,
                                            tint = Ink,
                                            modifier = Modifier.size(16.dp)
                                        )
                                        Spacer(modifier = Modifier.width(4.dp))
                                    }
                                    Text(
                                        text = label,
                                        fontSize = (14f + (value - 1f) * 20f).sp,
                                        fontWeight = FontWeight.Medium,
                                        color = if (selected) Ink else InkSoft
                                    )
                                }
                            }
                        }
                    }
                }

                Spacer(modifier = Modifier.height(20.dp))

                // AI Transparency Notice Card
                Surface(
                    shape = RoundedCornerShape(22.dp),
                    color = Sage50,
                    modifier = Modifier.fillMaxWidth()
                ) {
                    Row(
                        modifier = Modifier.padding(16.dp),
                        verticalAlignment = Alignment.Top
                    ) {
                        Icon(
                            imageVector = NianNianIcons.Bot,
                            contentDescription = null,
                            tint = Sage700,
                            modifier = Modifier.size(24.dp)
                        )
                        Spacer(modifier = Modifier.width(12.dp))
                        Text(
                            text = "关于小念：小念是人工智能陪伴助手，不会冒充任何家人。家人发来的留言都会标注“真人留言”。",
                            fontSize = 15f.spScaled(scale),
                            lineHeight = 23f.spScaled(scale),
                            color = InkSoft
                        )
                    }
                }

                Spacer(modifier = Modifier.height(14.dp))

                if (!loggedIn) {
                    Button(
                        onClick = onQuickUsbLogin,
                        colors = ButtonDefaults.buttonColors(
                            containerColor = Sage700,
                            contentColor = Color.White
                        ),
                        shape = CircleShape,
                        modifier = Modifier
                            .fillMaxWidth()
                            .height(50.dp)
                    ) {
                        Text(
                            text = "⚡ 一键连接本机后端 (demo-elder)",
                            fontSize = 15f.spScaled(scale),
                            fontWeight = FontWeight.Bold
                        )
                    }
                    Spacer(modifier = Modifier.height(10.dp))
                } else {
                    Surface(
                        shape = RoundedCornerShape(16.dp),
                        color = PaperDeep,
                        modifier = Modifier.fillMaxWidth()
                    ) {
                        Column(modifier = Modifier.padding(14.dp)) {
                            Text(
                                text = homeConnectionStatus(state),
                                fontSize = 14f.spScaled(scale),
                                fontWeight = FontWeight.Bold,
                                color = Sage700
                            )
                            Text(
                                text = "已生效家人授权：${state.permissions.count { homeConsentGranted(it) }} 项 · 自用授权：${state.selfPermissions.count { homeConsentGranted(it) }} 项",
                                fontSize = 13f.spScaled(scale),
                                color = InkSoft
                            )
                            Spacer(modifier = Modifier.height(8.dp))
                            Row(
                                modifier = Modifier.fillMaxWidth(),
                                horizontalArrangement = Arrangement.spacedBy(8.dp)
                            ) {
                                listOf(
                                    HomeFeature.REMINDERS to "生活提醒",
                                    HomeFeature.MEMORIES to "家庭记忆",
                                    HomeFeature.MESSAGES to "家人留言",
                                    HomeFeature.CONVERSATION to "陪伴设置",
                                    HomeFeature.REPORTS to "我的周报"
                                ).forEach { (feat, label) ->
                                    Surface(
                                        shape = CircleShape,
                                        color = PaperCard,
                                        modifier = Modifier
                                            .weight(1f)
                                            .height(36.dp)
                                            .clip(CircleShape)
                                            .clickable { onOpenFeature(feat) }
                                    ) {
                                        Box(contentAlignment = Alignment.Center) {
                                            Text(
                                                text = label,
                                                fontSize = 12.5f.spScaled(scale),
                                                fontWeight = FontWeight.Medium,
                                                color = Ink
                                            )
                                        }
                                    }
                                }
                            }
                        }
                    }
                    Spacer(modifier = Modifier.height(10.dp))
                }

                // Switch to Backend Connection & Consent Management Console
                Surface(
                    shape = CircleShape,
                    color = PaperDeep,
                    modifier = Modifier
                        .fillMaxWidth()
                        .height(48.dp)
                        .clip(CircleShape)
                        .clickable { onOpenBackendConsole() }
                ) {
                    Box(contentAlignment = Alignment.Center) {
                        Text(
                            text = if (loggedIn) "打开完整原功能控制台（提醒/记忆/对话/授权）" else "打开联机与原功能控制台（服务配置 / 登录）",
                            fontSize = 14f.spScaled(scale),
                            fontWeight = FontWeight.Medium,
                            color = Ink
                        )
                    }
                }

                Spacer(modifier = Modifier.height(12.dp))

                Button(
                    onClick = onClose,
                    colors = ButtonDefaults.buttonColors(
                        containerColor = Ink,
                        contentColor = Paper
                    ),
                    shape = CircleShape,
                    modifier = Modifier
                        .fillMaxWidth()
                        .height(56.dp)
                ) {
                    Text(
                        text = "好的",
                        fontSize = 17f.spScaled(scale),
                        fontWeight = FontWeight.Bold
                    )
                }

                Spacer(modifier = Modifier.height(12.dp))
            }
        }
    }
}
