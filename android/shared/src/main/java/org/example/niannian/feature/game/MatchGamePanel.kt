package org.example.niannian.feature.game

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.Image
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.compose.LocalLifecycleOwner
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Job
import kotlinx.coroutines.launch
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.coroutines.withTimeoutOrNull
import org.example.niannian.feature.conversation.AndroidConversationVoice
import org.example.niannian.shared.R
import kotlin.coroutines.resume

private const val INSTRUCTION = "看看上面的图，点下面和它一样的那张。"

@Composable
internal fun MatchGamePanel(scale: Float, voiceAllowed: Boolean, onClose: () -> Unit) {
    val context = LocalContext.current
    val lifecycle = LocalLifecycleOwner.current.lifecycle
    val scope = rememberCoroutineScope()
    var round by remember { mutableStateOf<MatchRound?>(null) }
    var confirmExit by remember { mutableStateOf(false) }
    var speechJob by remember { mutableStateOf<Job?>(null) }
    var speaking by remember { mutableStateOf(false) }
    var speechError by remember { mutableStateOf(false) }

    fun stopSpeech() { speechJob?.cancel() }
    fun speak() {
        if (!voiceAllowed || speaking || !lifecycle.currentState.isAtLeast(Lifecycle.State.RESUMED)) return
        speaking = true
        speechError = false
        speechJob = scope.launch {
            try {
                val voice = AndroidConversationVoice(context)
                try {
                    val completed = withTimeoutOrNull(12_000) {
                        suspendCancellableCoroutine { waiting ->
                            voice.speak(INSTRUCTION, slow = true, started = {},
                                finished = { if (waiting.isActive) waiting.resume(true) },
                                failed = { if (waiting.isActive) waiting.resume(false) })
                        }
                    }
                    speechError = completed != true
                } finally {
                    voice.close()
                }
            } catch (cancelled: CancellationException) {
                throw cancelled
            } catch (_: Exception) {
                speechError = true
            } finally {
                speaking = false
            }
        }
    }

    fun start() {
        if (round?.question != null) return
        round = MatchRound.start()
        speechError = false
        speak()
    }

    fun requestExit() {
        stopSpeech()
        if (round?.question != null) confirmExit = true else onClose()
    }

    DisposableEffect(lifecycle) {
        val observer = LifecycleEventObserver { _, event ->
            if (event == Lifecycle.Event.ON_PAUSE) stopSpeech()
        }
        lifecycle.addObserver(observer)
        onDispose {
            lifecycle.removeObserver(observer)
            stopSpeech()
        }
    }
    LaunchedEffect(voiceAllowed) {
        if (!voiceAllowed) stopSpeech()
    }

    Dialog(onDismissRequest = ::requestExit, properties = DialogProperties(
        usePlatformDefaultWidth = false, decorFitsSystemWindows = false,
        dismissOnBackPress = false, dismissOnClickOutside = false)) {
        BackHandler(enabled = !confirmExit, onBack = ::requestExit)
        Surface(Modifier.fillMaxSize()) {
            Column(Modifier.safeDrawingPadding().padding(16.dp)) {
                Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                    Text("找相同", Modifier.weight(1f), fontSize = (26 * scale).sp)
                    TextButton(onClick = ::requestExit, modifier = Modifier.heightIn(min = 48.dp)) {
                        Text(if (round?.question == null) "回首页" else "退出", fontSize = (18 * scale).sp)
                    }
                }
                val current = round
                val question = current?.question
                if (question != null) {
                    Card(Modifier.fillMaxWidth().padding(bottom = 12.dp)) {
                        Row(Modifier.fillMaxWidth().padding(10.dp), verticalAlignment = Alignment.CenterVertically,
                            horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                            Column(Modifier.weight(1f)) {
                                Text("第 ${current.index + 1} / ${current.questions.size} 题", fontSize = (18 * scale).sp)
                                Text("要找的是", fontSize = (20 * scale).sp)
                            }
                            Column(horizontalAlignment = Alignment.CenterHorizontally) { ItemPicture(question.target, scale) }
                        }
                    }
                }
                val scroll = key(current?.index) { rememberScrollState() }
                Column(Modifier.fillMaxWidth().weight(1f).verticalScroll(scroll),
                    verticalArrangement = Arrangement.spacedBy(14.dp)) {
                    when {
                        current == null -> {
                            Text(INSTRUCTION, fontSize = (22 * scale).sp)
                            Text("一局 5 题，慢慢玩。仅用于陪伴和认知活跃，不用于诊断。", fontSize = (18 * scale).sp)
                            GameButton("开始", scale, onClick = ::start)
                        }
                        question == null -> {
                            Text("完成 ${current.questions.size} 题，共点选 ${current.attempts} 次",
                                Modifier.semantics { liveRegion = LiveRegionMode.Polite }, fontSize = (24 * scale).sp)
                            GameButton("再玩一局", scale, onClick = ::start)
                            OutlinedButton(onClick = onClose, modifier = Modifier.fillMaxWidth().heightIn(min = 56.dp)) {
                                Text("回首页", fontSize = (20 * scale).sp)
                            }
                        }
                        else -> {
                            Text(INSTRUCTION, fontSize = (20 * scale).sp)
                            OutlinedButton(onClick = ::speak, enabled = voiceAllowed && !speaking,
                                modifier = Modifier.fillMaxWidth().heightIn(min = 52.dp)) {
                                Text(if (speaking) "正在朗读" else "再听一遍", fontSize = (18 * scale).sp)
                            }
                            if (!voiceAllowed || speechError) {
                                Text("暂时无法朗读，可以看文字继续。", fontSize = (17 * scale).sp)
                            }
                            ChoiceButtons(question, scale, enabled = !current.solved) { item ->
                                if (round?.question == question) round = round?.choose(item)
                            }
                            Text(when (current.feedback) {
                                MatchFeedback.FOUND -> "找到了"
                                MatchFeedback.TRY_AGAIN -> "再看看上面的图"
                                null -> "请选择一张图"
                            }, Modifier.semantics { liveRegion = LiveRegionMode.Polite }, fontSize = (22 * scale).sp)
                            if (current.solved) {
                                GameButton(if (current.index == current.questions.lastIndex) "看结果" else "下一题", scale) {
                                    stopSpeech()
                                    speechError = false
                                    round = round?.advance()
                                }
                            }
                        }
                    }
                }
            }
        }
    }

    if (confirmExit) {
        AlertDialog(onDismissRequest = { confirmExit = false },
            title = { Text("退出这一局？", fontSize = (22 * scale).sp) },
            text = { Text("退出后，本局进度会清空。", fontSize = (18 * scale).sp) },
            confirmButton = { TextButton(onClick = onClose) { Text("退出本局", fontSize = (18 * scale).sp) } },
            dismissButton = { TextButton(onClick = { confirmExit = false }) { Text("继续玩", fontSize = (18 * scale).sp) } })
    }
}

@Composable
private fun GameButton(label: String, scale: Float, onClick: () -> Unit) {
    Button(onClick = onClick, modifier = Modifier.fillMaxWidth().heightIn(min = 56.dp)) {
        Text(label, fontSize = (20 * scale).sp)
    }
}

@Composable
private fun ChoiceButtons(question: MatchQuestion, scale: Float, enabled: Boolean, onChoose: (MatchItem) -> Unit) {
    BoxWithConstraints(Modifier.fillMaxWidth()) {
        val showRow = maxWidth >= 324.dp && LocalDensity.current.fontScale * scale <= 1.3f
        if (showRow) {
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                question.choices.forEach { item -> ChoiceButton(item, scale, enabled, Modifier.weight(1f), onChoose) }
            }
        } else {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                question.choices.forEach { item -> ChoiceButton(item, scale, enabled, Modifier.fillMaxWidth(), onChoose) }
            }
        }
    }
}

@Composable
private fun ChoiceButton(item: MatchItem, scale: Float, enabled: Boolean, modifier: Modifier, onChoose: (MatchItem) -> Unit) {
    OutlinedButton(onClick = { onChoose(item) }, enabled = enabled, modifier = modifier.heightIn(min = 96.dp),
        contentPadding = PaddingValues(8.dp)) {
        Column(horizontalAlignment = Alignment.CenterHorizontally) { ItemPicture(item, scale) }
    }
}

@Composable
private fun ItemPicture(item: MatchItem, scale: Float) {
    val icon = when (item) {
        MatchItem.APPLE -> R.drawable.match_apple
        MatchItem.BANANA -> R.drawable.match_banana
        MatchItem.CUP -> R.drawable.match_cup
        MatchItem.UMBRELLA -> R.drawable.match_umbrella
        MatchItem.FISH -> R.drawable.match_fish
        MatchItem.KEY -> R.drawable.match_key
        MatchItem.LEAF -> R.drawable.match_leaf
        MatchItem.CLOCK -> R.drawable.match_clock
    }
    // The adjacent item label is also the spoken name for the image and its button.
    Image(painterResource(icon), contentDescription = null, modifier = Modifier.size(62.dp))
    Text(item.label, textAlign = TextAlign.Center, fontSize = (18 * scale).sp)
}
