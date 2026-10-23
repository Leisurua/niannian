package org.example.niannian.feature.family

import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import org.example.niannian.core.common.parseApiInstant
import org.example.niannian.feature.message.*
import java.time.ZoneId
import java.time.format.DateTimeFormatter

internal fun homeMessageItems(account: CompanionState, messages: MessageState): List<FamilyLetter> =
    if (homeFamily(account).isNotBlank() && !account.offline && account.error.isBlank() &&
        messages.family == homeFamily(account) && messages.user == account.userId && messages.error.isBlank())
        messages.items else emptyList()

internal fun homeReceiptLabel(item: FamilyLetter): String {
    if (item.receipts.isEmpty()) return "暂无回执"
    val read = item.receipts.count { it.second == "READ" }
    val received = item.receipts.count { it.second == "RECEIVED" }
    return if (item.outgoing) "已读 $read · 已接收未读 $received · 等待接收 ${item.receipts.size - read - received}"
        else if (read == item.receipts.size) "已确认读过" else "已收到 · 等待您确认已读"
}

@Composable
internal fun HomeMessagesSection(account: CompanionState, model: MessageModel?, scale: Float = 1f,
    onOpen: () -> Unit, onPhotos: () -> Unit) {
    val messages = model?.state?.collectAsState()?.value ?: MessageState()
    val items = homeMessageItems(account, messages)
    val matched = messages.family == homeFamily(account) && messages.user == account.userId
    val connected = homeFamily(account).isNotBlank() && !account.offline && account.error.isBlank()
    HomeCard {
        Text("家人动态", fontSize = (22 * scale).sp)
        Text("真人文字留言 · 前台自动同步，已读由本人确认", fontSize = (14 * scale).sp)
        when {
            !connected -> Text("连接家庭后查看真实留言。")
            model == null -> Text("当前客户端未提供留言功能。")
            matched && messages.error.isNotBlank() -> Text(messages.error, color = MaterialTheme.colorScheme.error)
            !matched || !messages.loaded -> Text("正在同步家人留言…")
            items.isEmpty() -> Text("还没有留言，给家人说句话吧。")
        }
        items.take(3).forEach { item ->
            HorizontalDivider()
            val time = runCatching { parseApiInstant(item.time).atZone(ZoneId.systemDefault())
                .format(DateTimeFormatter.ofPattern("M月d日 HH:mm")) }.getOrDefault("时间未知")
            Text("${if (item.outgoing) "我发出的留言" else "家人发来的留言"} · $time", fontSize = (14 * scale).sp)
            Text(item.text, fontSize = (20 * scale).sp)
            Text(homeReceiptLabel(item), fontSize = (14 * scale).sp)
            if (!item.outgoing && item.receipts.any { it.second != "READ" }) {
                OutlinedButton(onClick = { model?.read(item) },
                    enabled = connected && !account.busy && !messages.busy,
                    modifier = Modifier.heightIn(min = 52.dp)) { Text("看到啦 · 确认已读") }
            }
        }
        HomeButton("写留言 / 查看全部", connected && model != null && !account.busy, onOpen)
        OutlinedButton(onClick = onPhotos, enabled = connected && !account.busy) { Text("分享照片到家庭记忆") }
        Text("当前支持文字留言；原声留言和视频通话尚未接入。照片在家庭记忆中上传与查看。",
            fontSize = (14 * scale).sp)
    }
}
