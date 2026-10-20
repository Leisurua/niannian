package org.example.niannian.feature.memory

import android.graphics.BitmapFactory
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.Image
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.ImageBitmap
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.compose.LocalLifecycleOwner
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import kotlinx.coroutines.launch
import java.io.ByteArrayOutputStream

@Composable
fun MemoryPanel(model: MemoryModel, familyId: String, userId: String, subjects: List<Pair<String, String>>, unavailable: Boolean) {
    val state by model.state.collectAsState()
    val context = LocalContext.current
    val owner = LocalLifecycleOwner.current
    val uiScope = rememberCoroutineScope()
    var subject by remember(familyId, userId, subjects) { mutableStateOf(subjects.firstOrNull()?.first ?: userId) }
    var title by remember(familyId, userId) { mutableStateOf("") }
    var content by remember(familyId, userId) { mutableStateOf("") }
    var confirmDelete by remember(familyId, userId) { mutableStateOf<String?>(null) }
    var photoTarget by remember(familyId, userId) { mutableStateOf<String?>(null) }
    var bitmap by remember { mutableStateOf<ImageBitmap?>(null) }
    val disabled = unavailable || state.busy || state.pending
    LaunchedEffect(familyId, userId) { model.bind(familyId, userId) }
    DisposableEffect(owner, familyId, userId) {
        val observer = LifecycleEventObserver { _, event ->
            if (event == Lifecycle.Event.ON_STOP) { model.clear(); bitmap = null; title = ""; content = "" }
            if (event == Lifecycle.Event.ON_START) model.bind(familyId, userId)
        }
        owner.lifecycle.addObserver(observer)
        onDispose { owner.lifecycle.removeObserver(observer); model.clear(); bitmap = null }
    }
    LaunchedEffect(state.photo) {
        bitmap = null
        state.photo?.let { bytes -> bitmap = withContext(Dispatchers.Default) {
            BitmapFactory.decodeByteArray(bytes, 0, bytes.size)?.asImageBitmap()
        } }
    }
    val choosePhoto = rememberLauncherForActivityResult(ActivityResultContracts.GetContent()) { uri ->
        val id = photoTarget
        if (id != null) {
            val mime = uri?.let { context.contentResolver.getType(it).orEmpty() }
            uiScope.launch {
              model.resumePhotoSelection(familyId, userId, id, mime) {
                context.contentResolver.openInputStream(requireNotNull(uri))?.use { input ->
                    val output = ByteArrayOutputStream()
                    val buffer = ByteArray(8192)
                    while (true) {
                        val count = input.read(buffer)
                        if (count < 0) break
                        require(output.size() + count <= 5 * 1024 * 1024) { "照片需小于 5 MB。" }
                        output.write(buffer, 0, count)
                    }
                    output.toByteArray()
                } ?: error("无法读取所选照片。")
              }
            }
        }
        photoTarget = null
    }
    confirmDelete?.let { id ->
        AlertDialog(onDismissRequest = { confirmDelete = null }, title = { Text("删除这条记忆？") },
            text = { Text("记忆和关联照片会立即停止显示，文件清理在后台继续。") },
            confirmButton = { Button(enabled = !disabled, onClick = { model.delete(id); confirmDelete = null }) { Text("确认删除") } },
            dismissButton = { OutlinedButton(onClick = { confirmDelete = null }) { Text("取消") } })
    }
    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Text("家庭记忆", fontSize = 24.sp)
            Text("候选经人工确认后才是可用的家庭事实；访问始终受当前授权控制。", fontSize = 18.sp)
            if (state.busy) Text("正在读取或保存……")
            if (state.error.isNotEmpty()) Text(state.error, color = MaterialTheme.colorScheme.error)
            if (state.message.isNotEmpty()) Text(state.message)
            if (state.pending) MemoryButton("重试上次请求", unavailable || state.busy) { model.retry() }
            MemoryButton(if (state.candidates) "查看已确认记忆" else "查看待确认候选", unavailable || state.busy) { model.showCandidates(!state.candidates) }
            MemoryButton("重新读取记忆", unavailable || state.busy) { model.refresh() }
            if (state.items.isEmpty() && !state.busy && state.error.isEmpty()) Text(if (state.candidates) "暂无可访问的待确认候选。" else "暂无已确认且获准使用的记忆。")
            state.items.forEach { item -> MemoryButton(item.title + if (item.status == "PENDING") " · 待确认" else " · 已确认", disabled) { model.detail(item.id) } }
            state.selected?.let { item ->
                Text(item.title, fontSize = 22.sp)
                Text(item.content, fontSize = 20.sp)
                Text(if (item.status == "PENDING") "待确认，不作为事实使用" else "已人工确认")
                if (item.status == "PENDING") {
                    MemoryButton("我已核对，确认为家庭事实", disabled) { model.transition(item.id, "confirm") }
                    MemoryButton("拒绝这个候选", disabled) { model.transition(item.id, "reject") }
                }
                MemoryButton("报告内容有误", disabled) { model.feedback(item.id) }
                MemoryButton("选择照片并上传", disabled) { photoTarget = item.id; choosePhoto.launch("image/*") }
                item.attachments.forEachIndexed { index, id -> MemoryButton("查看照片 ${index + 1}", disabled) { model.photo(id) } }
                bitmap?.let { Image(it, contentDescription = "家庭记忆照片", modifier = Modifier.fillMaxWidth().heightIn(max = 320.dp)) }
                MemoryButton("编辑这条记忆", disabled) { title = item.title; content = item.content }
                MemoryButton("保存编辑（需重新确认）", disabled || title.isBlank() || content.isBlank()) { model.edit(item.id, item.version, title, content) }
                MemoryButton("撤回这条记忆", disabled) { model.transition(item.id, "revoke") }
                MemoryButton("删除这条记忆", disabled) { confirmDelete = item.id }
            }
            Text("添加或编辑记忆", fontSize = 20.sp)
            subjects.forEach { (id, name) ->
                MemoryButton((if (subject == id) "已选择：" else "选择：") + name, disabled) { subject = id }
            }
            OutlinedTextField(title, { title = it }, label = { Text("标题") }, enabled = !disabled, modifier = Modifier.fillMaxWidth())
            OutlinedTextField(content, { content = it }, label = { Text("由您提供的往事或信息") }, enabled = !disabled, modifier = Modifier.fillMaxWidth())
            MemoryButton("保存为新的待确认候选", disabled) { model.create(subject, title, content) }
        }
    }
}

@Composable private fun MemoryButton(label: String, disabled: Boolean, action: () -> Unit) {
    OutlinedButton(onClick = action, enabled = !disabled, modifier = Modifier.fillMaxWidth().heightIn(min = 56.dp)) { Text(label, fontSize = 18.sp) }
}
