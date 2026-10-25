package org.example.niannian.feature.conversation

import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.compose.LocalLifecycleOwner
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import java.time.DayOfWeek
import java.time.LocalDate
import java.time.ZoneId
import java.time.temporal.TemporalAdjusters

@Composable
fun WeeklyReportPanel(model: ConversationToolsModel, family: String, subjects: List<Pair<String, String>>,
    elder: Boolean, unavailable: Boolean, permissions: String) {
    var selected by remember(family, subjects) { mutableStateOf(subjects.firstOrNull()?.first.orEmpty()) }
    val monday = LocalDate.now(ZoneId.of("Asia/Shanghai")).with(TemporalAdjusters.previousOrSame(DayOfWeek.MONDAY))
    var week by remember(family, selected) { mutableStateOf(monday) }
    var reason by remember(family, selected, week) { mutableStateOf<String?>(null) }
    var requested by remember(family, selected, week) { mutableStateOf(false) }
    var refresh by remember { mutableIntStateOf(0) }
    var content by remember(family, selected, week) { mutableStateOf("") }
    var error by remember(family, selected, week) { mutableStateOf("") }
    var busy by remember { mutableStateOf(false) }
    var deleting by remember { mutableStateOf(false) }
    var confirmDelete by remember { mutableStateOf(false) }
    val scope = rememberCoroutineScope()
    val lifecycle = LocalLifecycleOwner.current.lifecycle
    var foreground by remember { mutableStateOf(lifecycle.currentState.isAtLeast(Lifecycle.State.STARTED)) }
    DisposableEffect(lifecycle) {
        val observer = LifecycleEventObserver { _, event ->
            if (event == Lifecycle.Event.ON_STOP) { foreground = false; content = ""; requested = false; reason = null; confirmDelete = false }
            if (event == Lifecycle.Event.ON_START) foreground = true
        }
        lifecycle.addObserver(observer)
        onDispose { lifecycle.removeObserver(observer) }
    }
    LaunchedEffect(family, selected, week, requested, refresh, foreground, unavailable, permissions, deleting) {
        content = ""; busy = false
        if (!requested || !foreground || unavailable || deleting || selected.isBlank()) return@LaunchedEffect
        error = ""
        while (true) {
            busy = true
            try { content = model.weeklyReport(family, selected, week.toString(), if (elder) null else reason); error = "" }
            catch (cancelled: CancellationException) { throw cancelled }
            catch (_: Exception) { content = ""; error = "周报读取失败，请检查网络、家庭权限及长辈的互动统计授权后重试。" }
            finally { busy = false }
            delay(30_000)
        }
    }
    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Text("每周交流观察", style = MaterialTheme.typography.headlineSmall)
        Text("按北京时间统计；只使用已授权记录。开启前、已删除及过期数据不会补录。")
        if (!elder) subjects.forEach { (id, name) ->
            OutlinedButton(onClick = { selected = id }, enabled = !deleting) { Text(if (selected == id) "✓ $name" else name) }
        }
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            OutlinedButton(onClick = { week = week.minusWeeks(1) }, enabled = week > monday.minusWeeks(3) && !deleting) { Text("上一周") }
            Text(week.toString(), modifier = Modifier.padding(top = 16.dp))
            OutlinedButton(onClick = { week = week.plusWeeks(1) }, enabled = week < monday && !deleting) { Text("下一周") }
        }
        if (!elder) Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            OutlinedButton(onClick = { reason = "FAMILY_CHECK_IN" }) { Text(if (reason == "FAMILY_CHECK_IN") "✓ 关心近况" else "关心近况") }
            OutlinedButton(onClick = { reason = "FOLLOW_UP" }) { Text(if (reason == "FOLLOW_UP") "✓ 跟进交流" else "跟进交流") }
        }
        Button(onClick = { requested = true; refresh++ }, enabled = !unavailable && !busy && !deleting && selected.isNotBlank() && (elder || reason != null)) {
            Text(if (busy) "正在生成…" else "生成 / 刷新周报")
        }
        if (error.isNotBlank()) Text(error, color = MaterialTheme.colorScheme.error)
        if (foreground && !unavailable && content.isNotBlank()) Text(content)
        if (elder) OutlinedButton(onClick = { confirmDelete = true }, enabled = !unavailable && !deleting) { Text("删除我的互动统计记录") }
    }
    if (confirmDelete) AlertDialog(onDismissRequest = { confirmDelete = false }, title = { Text("删除互动统计") },
        text = { Text("删除本家庭中您已保存的互动时间与分类统计，周报随即重新计算。若继续开启本人统计，之后的新交流仍会记录。") },
        confirmButton = { Button(onClick = {
            confirmDelete = false; requested = false; content = ""; deleting = true
            scope.launch {
                try { model.deleteStatistics(family); error = "统计记录已删除。" }
                catch (cancelled: CancellationException) { throw cancelled }
                catch (_: Exception) { error = "删除未完成，请联网后重试。" }
                finally { deleting = false }
            }
        }) { Text("确认删除") } }, dismissButton = { TextButton(onClick = { confirmDelete = false }) { Text("取消") } })
}
