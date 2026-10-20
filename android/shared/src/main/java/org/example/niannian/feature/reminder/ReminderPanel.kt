package org.example.niannian.feature.reminder

import android.Manifest
import android.os.Build
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.compose.LocalLifecycleOwner
import kotlinx.coroutines.delay
import org.json.JSONObject
import java.time.LocalDate

@Composable
fun CachedReminderEntry(model: ReminderModel, store: ReminderStore, savedUser: String, onNotifications: () -> Unit = {}) {
    var binding by remember(savedUser) { mutableStateOf<Pair<String, String>?>(null) }
    LaunchedEffect(savedUser) {
        binding = null
        if (savedUser.isNotBlank()) runCatching { ReminderLedger(store).snapshot() }.getOrNull()?.let {
            if (it.optString("owner") == savedUser && it.optString("family").isNotBlank() && (it.optJSONArray("rules")?.length() ?: 0) > 0)
                binding = it.getString("family") to savedUser
        }
    }
    binding?.let { (family, owner) ->
        Text("网络不可用 · 本人离线提醒（有效期内）", fontSize = 22.sp)
        ReminderPanel(model, family, owner, listOf(owner to "本人"), true, onNotifications)
    }
}

@Composable
fun ReminderPanel(model: ReminderModel, family: String, user: String, subjects: List<Pair<String, String>>, unavailable: Boolean, onNotifications: () -> Unit = {}) {
    val state by model.state.collectAsState()
    val permission = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { onNotifications() }
    val owner = LocalLifecycleOwner.current
    var target by remember(family, user, subjects) { mutableStateOf(subjects.firstOrNull()?.first ?: user) }
    var title by remember(family, user) { mutableStateOf("") }
    var content by remember(family, user) { mutableStateOf("") }
    var date by remember(family, user) { mutableStateOf(LocalDate.now().toString()) }
    var time by remember(family, user) { mutableStateOf("08:30") }
    var zone by remember(family, user) { mutableStateOf("Asia/Shanghai") }
    var type by remember(family, user) { mutableStateOf("WATER") }
    var daily by remember(family, user) { mutableStateOf(true) }
    var editing by remember(family, user) { mutableStateOf<JSONObject?>(null) }
    var confirmation by remember(family, user) { mutableStateOf<Pair<String, String>?>(null) }
    LaunchedEffect(family, user) { model.bind(family, user) }
    DisposableEffect(owner, family, user) {
        val listener = LifecycleEventObserver { _, event ->
            if (event == Lifecycle.Event.ON_STOP) { model.hide(); title = ""; content = ""; editing = null; confirmation = null }
            if (event == Lifecycle.Event.ON_START) model.bind(family, user)
        }
        owner.lifecycle.addObserver(listener)
        onDispose { owner.lifecycle.removeObserver(listener); model.hide() }
    }
    LaunchedEffect(family, user) {
        var ticks = 0
        while (true) {
            delay(15000)
            if (owner.lifecycle.currentState.isAtLeast(Lifecycle.State.STARTED)) {
                if (++ticks % 4 == 0) model.refresh() else model.tick()
            }
        }
    }
    fun save(confirmed: Boolean) { model.save(target, title, content, date, time, zone, type, daily, confirmed, editing) }
    confirmation?.let { (kind, id) ->
        AlertDialog(onDismissRequest = { confirmation = null }, title = { Text("请再次核对") },
            text = { Text(when (kind) {
                "medication" -> "请核对长辈、提醒时间与您录入的原始用药信息。念念不核验医嘱，也不会调整剂量。\n$title\n$content\n$date $time $zone"
                "skip" -> "记录跳过这次提醒，不代表没有服药。"
                else -> "停止并删除这条提醒？"
            }) }, confirmButton = { Button(enabled = !state.busy, onClick = {
                when (kind) { "medication" -> save(true); "skip" -> model.feedback(id, "SKIPPED", true); else -> model.delete(id) }
                confirmation = null
            }) { Text("我已核对，确认") } }, dismissButton = { OutlinedButton(onClick = { confirmation = null }) { Text("取消") } })
    }
    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Text(if (model.elder) "我的提醒" else "家人提醒", fontSize = 24.sp)
            Text("Demo / Mock · 记录反馈不代表已经服药；此版本不播报真实语音。", fontSize = 18.sp)
            if (state.offline) Text(if (model.elder) "当前离线 · 仅显示有效本人缓存，反馈先保存在本机。" else "当前离线，家人提醒内容已隐藏。", fontSize = 20.sp)
            Text("提醒按设置的时区执行；后台时间可能延迟，请保持页面打开并核对系统通知权限。")
            if (model.elder) Action("开启本机提醒通知", state.busy) {
                if (Build.VERSION.SDK_INT >= 33) permission.launch(Manifest.permission.POST_NOTIFICATIONS) else onNotifications()
            }
            if (state.error.isNotBlank()) Text(state.error)
            if (state.message.isNotBlank()) Text(state.message)
            Action("联网更新并同步反馈", state.busy) { model.refresh() }
            state.cards.forEach { card ->
                Text(card.title, fontSize = 22.sp); Text(card.content, fontSize = 20.sp); Text(card.time)
                Text(feedbackLabel(card.status) + if (card.pending) " · 仅本机记录，等待同步" else "")
                if (card.failed) Text("同步已暂停，请联网核对。原记录不会被自动覆盖。")
                if (card.failed) Action("联网核对并重试", state.busy || state.offline) { model.retry(card.key) }
                if (card.due && card.status !in setOf("DONE", "SKIPPED") && (!card.pending || card.status == "LATER")) {
                    Action("我已完成", state.busy) { model.feedback(card.key, "DONE") }
                    if (!card.pending) Action("十分钟后提醒", state.busy) { model.feedback(card.key, "LATER") }
                    Action("跳过这次", state.busy) {
                        if (card.medication) confirmation = "skip" to card.key else model.feedback(card.key, "SKIPPED")
                    }
                }
            }
            if (state.cards.isEmpty() && state.rules.isEmpty() && !state.busy) Text("暂无可显示的提醒；可联网读取或请家人添加。")
            state.rules.forEach { r ->
                Text(r.getString("title") + " · " + r.getString("schedule_time_local") + " " + r.getString("timezone"), fontSize = 20.sp)
                if (!model.elder) Action("查看反馈记录", unavailable || state.busy || state.offline) { model.executions(r.getString("id")) }
                if (r.getString("recurrence_kind") in setOf("ONCE", "DAILY") && !r.has("quiet_hours") && !r.has("end_date") && r.getInt("recurrence_interval") == 1) {
                    Action("编辑此提醒", unavailable || state.busy || state.offline || model.elder && r.getString("type") == "MEDICATION") {
                        editing = r; target = r.getString("owner_user_id"); title = r.getString("title"); content = r.getString("content")
                        date = r.getString("start_date"); time = r.getString("schedule_time_local"); zone = r.getString("timezone")
                        type = r.getString("type"); daily = r.getString("recurrence_kind") == "DAILY"
                    }
                }
                Action("删除此提醒", unavailable || state.busy || state.offline) { confirmation = "delete" to r.getString("id") }
            }
            Text(if (editing == null) "添加提醒" else "编辑提醒", fontSize = 22.sp)
            if (!model.elder) subjects.forEach { (id, label) -> Action((if (id == target) "已选择：" else "选择长辈：") + label, state.busy) { target = id } }
            Action(if (type == "MEDICATION") "用药提醒（点击改为喝水）" else "喝水提醒" , state.busy) { type = "WATER" }
            Action("日程提醒", state.busy) { type = "CALENDAR" }
            if (!model.elder) Action("用药提醒（需二次核对）", state.busy) { type = "MEDICATION" }
            val disabled = unavailable || state.offline || state.busy
            OutlinedTextField(title, { title = it }, label = { Text("提醒名称") }, enabled = !disabled)
            OutlinedTextField(content, { content = it }, label = { Text("提醒内容（不自动修改医嘱）") }, enabled = !disabled)
            OutlinedTextField(date, { date = it }, label = { Text("开始日期 YYYY-MM-DD") }, enabled = !disabled)
            OutlinedTextField(time, { time = it }, label = { Text("当地时间 HH:MM") }, enabled = !disabled)
            OutlinedTextField(zone, { zone = it }, label = { Text("时区，例如 Asia/Shanghai") }, enabled = !disabled)
            Action(if (daily) "每天（点击改为一次）" else "仅一次（点击改为每天）", disabled) { daily = !daily }
            Action("保存提醒", disabled || title.isBlank() || target.isBlank()) {
                if (type == "MEDICATION") confirmation = "medication" to "" else save(false)
            }
            if (editing != null) Action("取消编辑", state.busy) { editing = null; title = ""; content = "" }
        }
    }
}
@Composable private fun Action(label: String, disabled: Boolean, action: () -> Unit) {
    OutlinedButton(onClick = action, enabled = !disabled, modifier = Modifier.fillMaxWidth().heightIn(min = 56.dp)) { Text(label, fontSize = 18.sp) }
}
