package org.example.niannian.feature.conversation

import kotlinx.coroutines.*
import org.example.niannian.data.ApiFailure
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

class AvatarGenerationModelTest {
    private val id = "0192f1e4-6ed8-7c21-a4c1-5d58db7c3001"
    private inner class Gateway : AvatarGenerationGateway {
        val pack = avatarFixture()
        var status: String? = null
        var corrupt = false
        var revoked = false
        var creates = 0; var uploads = 0; var confirms = 0; var grants = 0
        var createStarted: CompletableDeferred<Unit>? = null
        var createRelease: CompletableDeferred<Unit>? = null
        fun job() = JSONObject().put("id", id).put("family_id", "family").put("owner_user_id", "elder")
            .put("consent_id", "grant-1").put("status", status).put("pack_checksum", avatarChecksum(pack))
        override suspend fun call(path: String, method: String, body: JSONObject?, key: String?): JSONObject {
            if (path == "/v1/avatar-generation") return JSONObject().put("available", true).put("provider_id", "provider")
                .put("provider_label", "fictional editor").put("notice", "fictional notice")
            if (path.contains("/latest")) {
                if (revoked) throw ApiFailure(403, "CONSENT_REQUIRED", "revoked")
                return JSONObject().put("job", if (status != null && path.endsWith("=family")) job() else JSONObject.NULL)
            }
            if (path.endsWith("/confirm")) { confirms++; status = "ACTIVE"; return job() }
            if (path.endsWith("/complete-upload")) { status = "QUEUED"; return job() }
            if (method == "DELETE") { status = null; return JSONObject().put("status", "CANCELLED") }
            creates++; status = "UPLOADING"; createStarted?.complete(Unit)
            createRelease?.let { withContext(NonCancellable) { it.await() } }
            return job().put("upload_url", "https://mock.invalid/upload").put("required_headers", JSONObject())
        }
        override suspend fun grant(family: String, user: String): String { grants++; return "grant-1" }
        override suspend fun upload(url: String, headers: JSONObject, bytes: ByteArray) { uploads++ }
        override suspend fun download(id: String) = if (corrupt) byteArrayOf(1) else pack
    }
    private suspend fun until(condition: () -> Boolean) = withTimeout(5000) { while (!condition()) delay(10) }

    @Test fun choosingPhotoDoesNotUploadAndReadyResultNeedsExplicitConfirmation() = runBlocking {
        val gateway = Gateway(); var activations = 0
        val model = AvatarGenerationModel(gateway, { _, _ -> activations++; true }, {}, this)
        try {
            model.bind("family", "elder"); until { model.state.value.available }
            model.selectedPhoto(byteArrayOf(1, 2, 3))
            assertEquals(0, gateway.creates); assertEquals(0, gateway.grants)
            model.create(); until { !model.state.value.busy }
            assertEquals(1, gateway.creates); assertEquals(1, gateway.uploads)
            assertEquals("QUEUED", model.state.value.job!!.status)
            model.confirm(); assertEquals(0, gateway.confirms)
            gateway.status = "READY"
            model.hide(); model.bind("family", "elder"); until { model.state.value.preview != null }
            assertEquals(0, activations)
            model.confirm(); until { !model.state.value.busy }
            assertEquals(1, activations); assertEquals("ACTIVE", model.state.value.job!!.status)
        } finally { model.hide() }
    }

    @Test fun familySwitchRejectsLateCreateResponseAndDoesNotUploadPhoto() = runBlocking {
        val gateway = Gateway()
        gateway.createStarted = CompletableDeferred(); gateway.createRelease = CompletableDeferred()
        val model = AvatarGenerationModel(gateway, { _, _ -> error("Must not activate") }, {}, this)
        try {
            model.bind("family", "elder"); until { model.state.value.available }
            model.selectedPhoto(byteArrayOf(1)); model.create(); gateway.createStarted!!.await()
            model.hide(); model.bind("other", "elder")
            gateway.createRelease!!.complete(Unit); yield()
            assertEquals(0, gateway.uploads)
            assertNull(model.state.value.photo); assertNull(model.state.value.preview)
            assertEquals("other", model.state.value.family)
        } finally { gateway.createRelease!!.complete(Unit); model.hide() }
    }

    @Test fun corruptDownloadAndRevokedConsentNeverActivatePreview() = runBlocking {
        val gateway = Gateway(); gateway.status = "READY"; gateway.corrupt = true
        var activated = false
        val model = AvatarGenerationModel(gateway, { _, _ -> activated = true; true }, {}, this)
        try {
            model.bind("family", "elder"); yield()
            until { model.state.value.message.isNotBlank() }
            assertNull(model.state.value.preview); model.confirm(); assertFalse(activated)
            model.hide(); gateway.corrupt = false
            model.bind("family", "elder"); until { model.state.value.preview != null }
            model.hide(); gateway.revoked = true
            model.bind("family", "elder"); yield()
            assertNull(model.state.value.preview); model.confirm(); assertFalse(activated)
        } finally { model.hide() }
    }
}
