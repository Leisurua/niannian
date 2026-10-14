package org.example.niannian.feature.memory

import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.yield
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

class MemoryModelTest {
    private fun row(id: String = "memory-one") = JSONObject().put("id", id).put("title", "虚构往事")
        .put("content", "虚构内容").put("verification_status", "CONFIRMED").put("version", 1).put("subject_user_id", "elder")

    private inner class Gateway : MemoryGateway {
        var failure = false
        var pending = false
        var items = listOf(row())
        var wait: CompletableDeferred<Unit>? = null
        var writes = mutableListOf<Triple<String, Boolean, JSONObject?>>()
        override suspend fun list(path: String): List<JSONObject> {
            wait?.await()
            if (failure) throw MemoryFailure("授权已撤回")
            return items
        }
        override suspend fun call(path: String, method: String, body: JSONObject?, idempotent: Boolean, version: Long?): JSONObject {
            if (failure) throw MemoryFailure("授权已撤回")
            if (method != "GET") writes.add(Triple(path, idempotent, body))
            return row()
        }
        override suspend fun upload(url: String, headers: JSONObject, bytes: ByteArray) { error("unused") }
        override suspend fun download(url: String): ByteArray = byteArrayOf()
        override suspend fun retry() { pending = false }
        override fun hasPending() = pending
    }

    @Test fun permissionFailureClearsPreviouslyVisibleContent() = runBlocking {
        val gateway = Gateway(); val model = MemoryModel(gateway, this)
        model.bind("family-a", "elder")!!.join()
        model.detail("memory-one")!!.join()
        assertNotNull(model.state.value.selected)
        gateway.failure = true
        model.refresh()!!.join()
        assertTrue(model.state.value.items.isEmpty())
        assertNull(model.state.value.selected)
        assertNull(model.state.value.photo)
        assertEquals("授权已撤回", model.state.value.error)
    }

    @Test fun switchingFamilyCancelsTheOldReadAndCannotRestoreOldRows() = runBlocking {
        val gateway = Gateway(); val model = MemoryModel(gateway, this)
        val gate = CompletableDeferred<Unit>(); gateway.wait = gate
        model.bind("family-a", "elder")
        yield()
        gateway.wait = null; gateway.items = listOf(row("family-b-only"))
        model.bind("family-b", "elder")!!.join()
        gate.complete(Unit); yield()
        assertEquals("family-b", model.state.value.familyId)
        assertEquals("family-b-only", model.state.value.items.single().id)
        model.clear()
        assertTrue(model.state.value.familyId.isBlank())
        assertTrue(model.state.value.items.isEmpty())
    }

    @Test fun candidatesNeverAutoConfirmAndActionsAreIdempotent() = runBlocking {
        val gateway = Gateway(); val model = MemoryModel(gateway, this)
        model.bind("family-a", "elder")!!.join()
        model.create("elder", "虚构候选", "需要本人核对")!!.join()
        assertEquals("PENDING", gateway.writes.single().third!!.getString("verification_status"))
        assertTrue(gateway.writes.single().second)
        model.transition("memory-one", "confirm")!!.join()
        assertEquals("/v1/memories/memory-one/confirm", gateway.writes.last().first)
        assertTrue(gateway.writes.last().second)
    }

    @Test fun oversizePhotoFailsBeforeRequestingAnyUpload() = runBlocking {
        val gateway = Gateway(); val model = MemoryModel(gateway, this)
        model.bind("family-a", "elder")!!.join()
        model.uploadPhoto("memory-one", "image/png") { ByteArray(5 * 1024 * 1024 + 1) }!!.join()
        assertTrue(gateway.writes.isEmpty())
        assertTrue(model.state.value.error.isNotEmpty())
        assertFalse(model.state.value.busy)
    }
}
