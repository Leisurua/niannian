package org.example.niannian.feature.game

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.compose.LocalLifecycleOwner
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.delay
import org.example.niannian.feature.memory.MemoryModel

private val generalPrompts = listOf(
    "小时候，您最喜欢玩什么？",
    "有没有一道菜，让您想起一次开心的团聚？",
    "过去常去的地方里，哪一个最让您怀念？",
    "哪首歌会让您想起一段好时光？",
)

@Composable
internal fun RecallPanel(model: MemoryModel, familyId: String, allowed: Boolean, scale: Float, close: () -> Unit) {
    val lifecycle by LocalLifecycleOwner.current.lifecycle.currentStateFlow.collectAsState()
    var useFamily by remember(familyId, allowed) { mutableStateOf(false) }
    var turn by remember { mutableIntStateOf(0) }
    val personal = allowed && useFamily && lifecycle.isAtLeast(Lifecycle.State.RESUMED)
    var titles by remember(familyId, personal, turn) { mutableStateOf<List<String>?>(null) }
    LaunchedEffect(familyId, personal, turn) {
        if (!personal) return@LaunchedEffect
        while (true) {
            titles = try {
                model.recallTitles(familyId)
            } catch (cancelled: CancellationException) {
                throw cancelled
            } catch (_: Exception) {
                emptyList()
            }
            delay(15_000)
        }
    }
    val available = if (personal) titles.orEmpty() else emptyList()
    val prompt = if (available.isEmpty()) generalPrompts[turn % generalPrompts.size]
        else "想想「${available[turn % available.size]}」。当时有没有一件令您印象深刻的小事？"

    AlertDialog(onDismissRequest = close, title = { Text("想起从前", fontSize = (26 * scale).sp) },
        text = {
            Column(Modifier.verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(14.dp)) {
                Text(prompt, fontSize = (22 * scale).sp,
                    modifier = Modifier.semantics { liveRegion = LiveRegionMode.Polite })
                Text(when {
                    available.isNotEmpty() -> "来自本人获准使用、已确认的家庭记忆"
                    personal && titles == null -> "正在核对家庭记忆，您可以先看通用题目。"
                    personal -> "当前没有可用的家庭记忆，已显示通用题目。"
                    else -> "通用题目"
                }, fontSize = (16 * scale).sp)
                Text("随意想一想，也可以略过。回答只留给自己，应用不会记录。", fontSize = (18 * scale).sp)
                if (allowed) {
                    OutlinedButton(onClick = { useFamily = !useFamily }, modifier = Modifier.fillMaxWidth().heightIn(min = 52.dp)) {
                        Text(if (useFamily) "换用通用题目" else "使用我的家庭记忆", fontSize = (18 * scale).sp)
                    }
                }
            }
        },
        confirmButton = { Button(onClick = { turn++ }) { Text("换一题", fontSize = (18 * scale).sp) } },
        dismissButton = { TextButton(onClick = close) { Text("结束", fontSize = (18 * scale).sp) } })
}
