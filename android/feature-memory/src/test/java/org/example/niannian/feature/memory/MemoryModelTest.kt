package org.example.niannian.feature.memory

import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.launch
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.yield
import org.json.JSONArray
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
        var fileStatus = "AVAILABLE"
        var uploaded = false
        var attachment = false
        override suspend fun list(path: String): List<JSONObject> {
            wait?.await()
            if (failure) throw MemoryFailure("授权已撤回")
            return items
        }
        override suspend fun call(path: String, method: String, body: JSONObject?, idempotent: Boolean, version: Long?): JSONObject {
            if (failure) throw MemoryFailure("授权已撤回")
            if (method != "GET") writes.add(Triple(path, idempotent, body))
            if (path == "/v1/files/upload-requests") return JSONObject().put("upload_url", "https://mock.invalid/upload")
                .put("required_headers", JSONObject()).put("file", JSONObject().put("id", "mock-file"))
            if (path == "/v1/files/mock-file/confirm") {
                attachment = fileStatus == "AVAILABLE"
                return JSONObject().put("status", fileStatus)
            }
            return row().put("attachments", JSONArray().apply {
                if (attachment) put(JSONObject().put("id", "mock-file"))
            })
        }
        override suspend fun upload(url: String, headers: JSONObject, bytes: ByteArray) { uploaded = true }
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

    @Test fun cancellingPickerAfterStopRestoresAuthorizedDetailWithoutReadingFile() = runBlocking {
        val gateway = Gateway(); val model = MemoryModel(gateway, this)
        model.bind("family-a", "elder")!!.join()
        model.detail("memory-one")!!.join()
        model.clear() // ON_STOP must still clear sensitive content.
        assertNull(model.state.value.selected)
        model.resumePhotoSelection("family-a", "elder", "memory-one", null) { error("Cancelled picker must not read") }
        assertEquals("memory-one", model.state.value.selected?.id)
        assertTrue(gateway.writes.isEmpty())
    }

    @Test fun pickerResultWaitsForRestartReadAndUploadsOnce() = runBlocking {
        val gateway = Gateway(); val model = MemoryModel(gateway, this)
        model.bind("family-a", "elder")!!.join(); model.clear()
        val gate = CompletableDeferred<Unit>(); gateway.wait = gate
        model.bind("family-a", "elder") // ON_START refresh still in flight.
        val result = launch {
            model.resumePhotoSelection("family-a", "elder", "memory-one", "image/png") { byteArrayOf(1, 2, 3) }
        }
        yield(); assertTrue(gateway.writes.isEmpty())
        gate.complete(Unit); result.join()
        assertTrue(gateway.uploaded)
        assertEquals(listOf("/v1/files/upload-requests", "/v1/files/mock-file/confirm"), gateway.writes.map { it.first })
        assertTrue(gateway.writes.last().second)
        assertEquals(listOf("mock-file"), model.state.value.selected?.attachments)
        assertEquals("照片已检查并去除附加元数据。", model.state.value.message)
    }

    @Test fun invalidPickerFilesAfterStopReportErrorsWithoutCreatingFiles() = runBlocking {
        for ((mime, bytes, expected) in listOf(
            Triple("image/png", ByteArray(5 * 1024 * 1024 + 1), "照片需小于 5 MB。"),
            Triple("image/gif", byteArrayOf(1), "请选择 JPG、PNG 或 WebP 照片。"))) {
            val gateway = Gateway(); val model = MemoryModel(gateway, this)
            model.resumePhotoSelection("family-a", "elder", "memory-one", mime) { bytes }
            assertEquals(expected, model.state.value.error)
            assertTrue(gateway.writes.isEmpty()); assertFalse(model.state.value.busy)
        }
    }

    @Test fun quarantinedPickerUploadIsNotAttachedAndNextValidPhotoCanRecover() = runBlocking {
        val gateway = Gateway(); val model = MemoryModel(gateway, this)
        gateway.fileStatus = "QUARANTINED"
        model.resumePhotoSelection("family-a", "elder", "memory-one", "image/png") { byteArrayOf(1) }
        assertEquals("照片未通过内容检查，已隔离；请换一张照片。", model.state.value.error)
        assertFalse(gateway.attachment); assertNull(model.state.value.photo)
        model.clear(); gateway.fileStatus = "AVAILABLE"
        model.resumePhotoSelection("family-a", "elder", "memory-one", "image/png") { byteArrayOf(2) }
        assertTrue(model.state.value.error.isEmpty())
        assertEquals(listOf("mock-file"), model.state.value.selected?.attachments)
    }

    @Test fun stalePickerScopeAndRevokedAccessNeverReadOrUploadFile() = runBlocking {
        for ((family, user) in listOf("family-b" to "elder", "family-a" to "other-user")) {
            val gateway = Gateway(); val model = MemoryModel(gateway, this)
            model.bind(family, user)!!.join()
            model.resumePhotoSelection("family-a", "elder", "memory-one", "image/png") { error("Stale picker") }
            assertEquals(family, model.state.value.familyId); assertEquals(user, model.state.value.userId)
            assertTrue(gateway.writes.isEmpty())
        }
        val gateway = Gateway(); val model = MemoryModel(gateway, this)
        model.bind("family-a", "elder")!!.join(); model.clear(); gateway.failure = true
        model.resumePhotoSelection("family-a", "elder", "memory-one", "image/png") { error("Revoked access") }
        assertEquals("授权已撤回", model.state.value.error)
        assertTrue(gateway.writes.isEmpty()); assertNull(model.state.value.selected)
    }
}
