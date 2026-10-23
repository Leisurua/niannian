package org.example.niannian.feature.message

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import org.example.niannian.data.ApiFailure
import org.json.JSONObject

interface MessageGateway {
    suspend fun register(family: String)
    suspend fun list(family: String, box: String): List<JSONObject>
    suspend fun acknowledge(id: String, read: Boolean): JSONObject
    suspend fun send(family: String, role: String, text: String): JSONObject
}

data class FamilyLetter(val id: String, val text: String, val time: String, val outgoing: Boolean,
    val receipts: List<Pair<String, String>>)
data class MessageState(val family: String = "", val user: String = "", val busy: Boolean = false,
    val items: List<FamilyLetter> = emptyList(), val notice: String = "", val sentVersion: Int = 0,
    val error: String = "", val loaded: Boolean = false)

class MessageModel(private val gateway: MessageGateway, private val elder: Boolean,
    private val scope: CoroutineScope? = null) : ViewModel() {
    private val current = MutableStateFlow(MessageState())
    val state = current.asStateFlow()
    private val tasks get() = scope ?: viewModelScope
    private var generation = 0
    private var registered = false
    private var operation: Job? = null
    private var polling: Job? = null

    fun clear() {
        generation++; operation?.cancel(); polling?.cancel()
        registered = false; current.value = MessageState()
    }

    fun bind(family: String, user: String) {
        if (current.value.family == family && current.value.user == user && polling?.isActive == true) return
        clear(); current.value = MessageState(family = family, user = user)
        polling = tasks.launch { while (isActive) { refresh(); delay(3000) } }
    }

    private fun action(work: suspend (Int, String) -> Unit) {
        if (current.value.busy || current.value.family.isBlank()) return
        val stamp = generation; val family = current.value.family
        current.value = current.value.copy(busy = true)
        operation = tasks.launch {
            try {
                if (!registered) { gateway.register(family); if (stamp != generation) return@launch; registered = true }
                work(stamp, family)
            } catch (cancelled: CancellationException) { throw cancelled }
            catch (error: Exception) {
                if (stamp == generation) {
                    registered = false
                    if (error is ApiFailure && error.status == 401) polling?.cancel()
                    current.value = current.value.copy(items = emptyList(), loaded = false, error =
                        if (error is ApiFailure || error is IllegalArgumentException) error.message.orEmpty()
                        else "连接未完成，恢复后会自动补收。发送结果未确认时，请保留原内容重试。")
                }
            } finally { if (stamp == generation) current.value = current.value.copy(busy = false) }
        }
    }

    private suspend fun load(stamp: Int, family: String) {
        val items = mutableListOf<FamilyLetter>()
        for (box in listOf("INBOX", "OUTBOX")) {
            for (row in gateway.list(family, box)) {
                if (stamp != generation) return
                require(row.getString("family_id") == family)
                val receipts = row.getJSONArray("deliveries")
                val statuses = (0 until receipts.length()).map { index ->
                    var receipt = receipts.getJSONObject(index)
                    if (box == "INBOX" && receipt.getString("status") == "QUEUED") {
                        receipt = gateway.acknowledge(receipt.getString("id"), false)
                    }
                    receipt.getString("id") to receipt.getString("status")
                }
                items.add(FamilyLetter(row.getString("id"), row.getJSONObject("payload").getString("text"),
                    row.getString("created_at"), box == "OUTBOX", statuses))
            }
        }
        if (stamp == generation) current.value = current.value.copy(items = items.sortedByDescending { it.time },
            loaded = true, error = "")
    }

    fun refresh() = action { stamp, family -> load(stamp, family) }

    fun send(text: String) = action { stamp, family ->
        val clean = text.trim()
        require(clean.isNotEmpty() && clean.length <= 2000) { "请输入 1 到 2000 个字符。" }
        gateway.send(family, if (elder) "CHILD" else "ELDER", clean)
        if (stamp != generation) return@action
        current.value = current.value.copy(notice = "留言已保存，等待家人接收。", sentVersion = current.value.sentVersion + 1)
        load(stamp, family)
    }

    fun read(item: FamilyLetter) = action { stamp, family ->
        require(!item.outgoing && current.value.items.any { it.id == item.id })
        for ((id, status) in item.receipts) if (status != "READ") gateway.acknowledge(id, true)
        if (stamp == generation) { current.value = current.value.copy(notice = "已告诉家人：这条留言您已读过。"); load(stamp, family) }
    }

    override fun onCleared() { clear(); super.onCleared() }
}
