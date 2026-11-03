package org.example.niannian.feature.family

import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.BackHandler
import androidx.activity.result.contract.ActivityResultContracts
import android.provider.DocumentsContract
import android.content.Context
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.*
import org.json.JSONObject
import org.example.niannian.data.ApiFailure
import java.security.SecureRandom
import java.util.Base64

internal fun deletionProgress(value: JSONObject): String {
    val providers = value.getJSONArray("providers")
    val backup = value.getJSONObject("backup")
    val complete = value.optString("status") == "COMPLETED" && value.optString("local_status") == "ERASED" &&
        backup.optString("status") == "CONFIRMED" && (0 until providers.length()).all { providers.getJSONObject(it).optString("status") == "CONFIRMED" }
    return buildString {
        appendLine(if (complete) "全部删除已核验完成" else "删除尚未全部完成")
        appendLine("服务端本地数据：" + if (value.optString("local_status") == "ERASED") "已清理" else "处理中 / 待重试")
        appendLine("备份：" + if (backup.optString("status") == "CONFIRMED") "已核验" else "未核验，仍未完成")
        if (backup.optBoolean("overdue")) appendLine("备份核验已超期，仍需处理。")
        for (i in 0 until providers.length()) {
            val item = providers.getJSONObject(i)
            appendLine("供应商 " + item.optString("provider") + "：" + if (item.optString("status") == "CONFIRMED") "已核验" else "未核验，仍未完成")
        }
        if (!value.isNull("last_error_code")) appendLine("服务端清理需重试：" + value.optString("last_error_code"))
        appendLine(value.optString("retained")); append(value.optString("device_notice"))
    }
}

@Composable
internal fun AccountPanel(model: CompanionModel, clearPrivateCache: suspend () -> Unit, onBack: () -> Unit) {
    val state by model.state.collectAsState()
    val repo = model.accountRepository
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var busy by remember { mutableStateOf(false) }
    var message by remember { mutableStateOf("导出只包含本人可访问的数据。删除不可撤销，其他人的共享记录可能保留。") }
    var confirmation by remember { mutableStateOf(0) }
    var receipt by remember { mutableStateOf<JSONObject?>(null) }
    var lookup by remember { mutableStateOf<JSONObject?>(null) }
    var activeReceipt by remember { mutableStateOf<JSONObject?>(null) }
    var exportOwner by remember { mutableStateOf("") }
    fun work(label: String, failure: String = "操作未完成，请检查网络、登录或凭证后重试。", block: suspend () -> String) {
        if (busy) return
        busy = true; message = label
        scope.launch {
            try { message = block() }
            catch (cancelled: CancellationException) { throw cancelled }
            catch (_: Exception) { message = failure }
            finally { busy = false }
        }
    }
    BackHandler { if (!busy) onBack() }
    fun query(value: JSONObject) = work("正在查询删除进度…") {
        try { deletionProgress(repo.deletionReceipt(value.getString("server"), value.getString("receipt_token"))) }
        catch (error: ApiFailure) {
            when (error.status) {
                404 -> "未找到删除回执。请核对凭证和服务器。若提交结果未确认，请稍后再查，确认未受理后可重新登录。"
                429 -> "查询过于频繁，请稍后再试。"
                else -> throw error
            }
        }
    }
    val saveExport = rememberLauncherForActivityResult(ActivityResultContracts.CreateDocument("application/zip")) { uri ->
        if (uri != null) work("正在生成并下载本人数据，请稍候…", "导出未完成，请检查连接与保存位置后重试。") {
            var saved = false
            try {
                repo.exportAccount(exportOwner) { checkNotNull(context.contentResolver.openOutputStream(uri, "wt")) }
                saved = true
                "本人数据已下载并保存。导出文件由您保管。"
            } finally {
                if (!saved) withContext(NonCancellable + Dispatchers.IO) {
                    runCatching { DocumentsContract.deleteDocument(context.contentResolver, uri) }
                }
                if (!repo.hasSession()) model.accountDeleted()
            }
        }
    }
    val saveReceipt = rememberLauncherForActivityResult(ActivityResultContracts.CreateDocument("application/json")) { uri ->
        if (uri != null) work("正在保存独立查询凭证…") {
            val saved = checkNotNull(receipt)
            val file = JSONObject().put("server", saved.getString("server")).put("receipt_token", saved.getString("receipt_token"))
            withContext(Dispatchers.IO) { checkNotNull(context.contentResolver.openOutputStream(uri, "wt")).use { it.write(file.toString().toByteArray(Charsets.UTF_8)) } }
            confirmation = 2
            "凭证已保存，请再次确认删除。"
        } else { receipt = null; message = "未保存凭证，未提交删除。" }
    }
    val openReceipt = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocument()) { uri ->
        if (uri != null) work("正在读取独立查询凭证…") {
            val value = withContext(Dispatchers.IO) {
                checkNotNull(context.contentResolver.openInputStream(uri)).use { stream ->
                    val bytes = ByteArray(4097)
                    var size = 0
                    while (size < bytes.size) {
                        val count = stream.read(bytes, size, bytes.size - size)
                        if (count < 0) break
                        size += count
                    }
                    require(size <= 4096)
                    JSONObject(String(bytes, 0, size, Charsets.UTF_8))
                }
            }
            require(value.getString("receipt_token").matches(Regex("[A-Za-z0-9_-]{43,128}")))
            value.put("server", repo.receiptOrigin(value.getString("server")))
            lookup = value
            "请核对查询服务器。"
        }
    }
    Column(Modifier.fillMaxSize().safeDrawingPadding().padding(20.dp).verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(14.dp)) {
        Text("本人数据管理", fontSize = 28.sp)
        Text("当前账户：" + state.userName.ifBlank { if (state.loggedIn) "已登录本人账户" else "未登录，仍可查询删除回执" })
        if (busy) CircularProgressIndicator()
        Text(message, fontSize = 20.sp)
        Button(onClick = { exportOwner = state.userId; saveExport.launch("niannian-account.zip") }, enabled = !busy && state.userId.isNotBlank() && !state.busy) { Text("导出并保存 ZIP") }
        Button(onClick = { confirmation = 1 }, enabled = !busy && state.userId.isNotBlank() && !state.busy) { Text("删除我的账户") }
        activeReceipt?.let { value -> Button(onClick = { query(value) }, enabled = !busy) { Text("刷新删除进度") } }
        Button(onClick = { openReceipt.launch(arrayOf("application/json", "text/plain", "application/octet-stream")) }, enabled = !busy) { Text("打开独立凭证 / 查询删除进度") }
        Text("独立凭证等同查询权限，请妥善保管。供应商与备份未核验时，删除仍未完成。")
        OutlinedButton(onClick = onBack, enabled = !busy) { Text("返回") }
    }
    if (confirmation > 0) AlertDialog(onDismissRequest = { if (!busy) confirmation = 0 },
        title = { Text(if (confirmation == 1) "删除账户的影响" else "再次确认删除本人账户") },
        text = { Text(if (confirmation == 1) "账户删除不可撤销，全部登录将失效，本端私有缓存会清理。先保存独立凭证，以便退出后查询进度。" else "查询凭证已保存。确认立即删除当前本人账户？供应商和备份需要另行核验。") },
        confirmButton = { TextButton(enabled = !busy, onClick = {
            if (confirmation == 1) {
                confirmation = 0
                receipt = JSONObject().put("user_id", state.userId).put("server", repo.savedOrigin()).put("receipt_token",
                    Base64.getUrlEncoder().withoutPadding().encodeToString(ByteArray(32).also { SecureRandom().nextBytes(it) }))
                saveReceipt.launch("niannian-deletion-receipt.json")
            } else {
                confirmation = 0
                val value = checkNotNull(receipt)
                activeReceipt = value
                work("正在提交账户删除…", "删除或本机清理结果未确认。请使用已保存的独立凭证查询进度。") {
                    try { deletionProgress(repo.deleteAccount(value.getString("user_id"), value.getString("server"), value.getString("receipt_token"))) }
                    finally { withContext(NonCancellable + Dispatchers.Main) {
                        if (!repo.hasSession()) {
                            try {
                                clearPrivateCache()
                                withContext(Dispatchers.IO) {
                                    val prefix = value.getString("user_id") + ":"
                                    val prefs = context.getSharedPreferences("home-weather", Context.MODE_PRIVATE)
                                    val edit = prefs.edit()
                                    prefs.all.keys.filter { it.startsWith(prefix) }.forEach { edit.remove(it) }
                                    check(edit.commit())
                                }
                            }
                            finally { model.accountDeleted() }
                        }
                        receipt = null
                    } }
                }
            }
        }) { Text(if (confirmation == 1) "保存凭证" else "确认删除") } },
        dismissButton = { TextButton(onClick = { confirmation = 0; receipt = null }, enabled = !busy) { Text("取消") } })
    lookup?.let { value -> AlertDialog(onDismissRequest = { lookup = null }, title = { Text("核对查询服务器") },
        text = { Text("将独立凭证发送到：" + value.optString("server") + "。仅在确认这是原删除服务器时继续。") },
        confirmButton = { TextButton(onClick = { lookup = null; activeReceipt = value; query(value) }) { Text("确认查询") } },
        dismissButton = { TextButton(onClick = { lookup = null }) { Text("取消") } }) }
}
