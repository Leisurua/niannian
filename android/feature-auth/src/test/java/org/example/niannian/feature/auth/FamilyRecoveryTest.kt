package org.example.niannian.feature.auth

import kotlinx.coroutines.delay
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withTimeout
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import java.io.ByteArrayInputStream
import java.io.ByteArrayOutputStream
import java.io.IOException
import java.net.HttpURLConnection
import java.net.URL
import java.util.concurrent.CopyOnWriteArrayList

private class MemorySession : SessionStore {
    private var data = JSONObject().put("origin", "https://example.com")
        .put("access_token", "fictional-access").put("refresh_token", "fictional-refresh")
    @Synchronized override fun load() = JSONObject(data.toString())
    @Synchronized override fun save(value: JSONObject) { data = JSONObject(value.toString()) }
    @Synchronized override fun clear() { data = JSONObject() }
}

private data class Reply(val status: Int = 200, val body: JSONObject = JSONObject())
private fun error(status: Int, code: String) = Reply(status, JSONObject().put("error",
    JSONObject().put("code", code).put("message", "演示错误")))
private fun page(items: List<JSONObject>, cursor: String? = null) = Reply(body = JSONObject()
    .put("items", JSONArray(items)).put("page", JSONObject().put("has_more", cursor != null)
        .put("next_cursor", cursor ?: JSONObject.NULL)))

private class Connection(url: URL, handler: (Connection) -> Reply) : HttpURLConnection(url) {
    val sentBody = ByteArrayOutputStream()
    private val reply by lazy { handler(this) }
    override fun connect() {}
    override fun disconnect() {}
    override fun usingProxy() = false
    override fun getResponseCode() = reply.status
    override fun getOutputStream() = sentBody
    override fun getInputStream() = ByteArrayInputStream(reply.body.toString().toByteArray(Charsets.UTF_8))
    override fun getErrorStream() = inputStream
}

private class FakeApi {
    val requests = CopyOnWriteArrayList<Connection>()
    val store = MemorySession()
    var admin = true
    var offline = false
    var failWrite = false
    var secondConsentPage = false
    var handler: ((Connection) -> Reply)? = null
    val repository = FamilyRepository(store, false) { url ->
        Connection(url) { request ->
            requests.add(request)
            if (offline) throw IOException("fictional offline")
            handler?.invoke(request) ?: respond(request)
        }
    }

    fun respond(request: Connection): Reply {
        val path = request.url.path
        if (request.requestMethod == "POST") {
            if (failWrite) { failWrite = false; throw IOException("fictional response lost") }
            return Reply(201, JSONObject().put("family_id", "family-a").put("token", "fictional-invitation"))
        }
        return when {
            path == "/v1/me" -> Reply(body = JSONObject().put("user", JSONObject().put("id", "self").put("display_name", "演示家人"))
                .put("family_memberships", JSONArray(listOf("family-a", "family-b").map {
                    JSONObject().put("family_id", it).put("status", "ACTIVE").put("permission_codes", JSONArray())
                })))
            path == "/v1/families" -> page(listOf("family-a", "family-b").map {
                JSONObject().put("id", it).put("name", it).put("role", "CHILD").put("member_status", "ACTIVE")
            })
            path.endsWith("/members") -> { check(admin) { "Ordinary members must not request the member list" }; page(emptyList()) }
            path.startsWith("/v1/families/") -> Reply(body = JSONObject().put("created_by_user_id", if (admin) "self" else "creator"))
            path == "/v1/consents" -> if (secondConsentPage && !request.url.query.contains("cursor=")) page(emptyList(), "page.2")
                else page(if (secondConsentPage) listOf(JSONObject().put("id", "consent-a").put("subject_user_id", "elder")
                    .put("grantee_user_id", "self").put("scope", "FAMILY_MEMORY").put("status", "GRANTED").put("version", 1)) else emptyList())
            else -> error(404, "NOT_FOUND")
        }
    }
}

private suspend fun CompanionModel.idle() = withTimeout(5000) {
    while (state.value.busy) delay(1)
}

class FamilyRecoveryTest {
    @Test fun lostRefreshResponseRequiresLoginInsteadOfReusingARotatedToken() = runBlocking {
        val api = FakeApi()
        api.handler = { request ->
            if (request.url.path == "/v1/auth/refresh") throw IOException("fictional refresh response lost")
            error(401, "AUTH_TOKEN_EXPIRED")
        }
        try { api.repository.call("/v1/me"); fail("Expected login requirement") }
        catch (error: ApiFailure) { assertEquals("AUTH_REFRESH_UNCONFIRMED", error.code) }
        assertFalse(api.repository.hasSession())
        assertEquals(2, api.requests.size)
    }

    @Test fun terminalReplayRejectionAfterRefreshUsesTheSameCleanupRules() = runBlocking {
        for (status in listOf(401, 403, 409)) {
            val api = FakeApi()
            var calls = 0
            api.handler = { request ->
                when (calls++) {
                    0 -> error(401, "AUTH_TOKEN_EXPIRED")
                    1 -> { assertEquals("/v1/auth/refresh", request.url.path)
                        Reply(body = JSONObject().put("access_token", "refreshed-access").put("refresh_token", "refreshed-refresh")) }
                    else -> error(status, "REJECTED")
                }
            }
            try { api.repository.call("/v1/families", "POST", JSONObject().put("name", "演示家庭"), true); fail("Expected denial") }
            catch (error: ApiFailure) { assertEquals(status, error.status) }
            assertEquals(3, calls)
            assertFalse(api.repository.hasPending())
            assertEquals(status != 401, api.repository.hasSession())
            assertEquals(api.requests[0].getRequestProperty("Idempotency-Key"), api.requests[2].getRequestProperty("Idempotency-Key"))
        }
    }

    @Test fun temporaryReplayFailureKeepsTheOriginalKeyForAnExplicitRetry() = runBlocking {
        val api = FakeApi()
        var calls = 0
        api.handler = { _ -> when (calls++) {
            0 -> error(401, "AUTH_TOKEN_EXPIRED")
            1 -> Reply(body = JSONObject().put("access_token", "refreshed-access").put("refresh_token", "refreshed-refresh"))
            2 -> error(503, "UNAVAILABLE")
            else -> Reply(201, JSONObject().put("id", "family-a"))
        } }
        try { api.repository.call("/v1/families", "POST", JSONObject().put("name", "演示家庭"), true); fail("Expected temporary failure") }
        catch (error: ApiFailure) { assertEquals(503, error.status) }
        assertTrue(api.repository.hasPending())
        api.repository.retryPending()
        assertEquals(api.requests[0].getRequestProperty("Idempotency-Key"), api.requests[3].getRequestProperty("Idempotency-Key"))
        assertFalse(api.repository.hasPending())
    }

    @Test fun restoredAndReloadedPendingWriteRemainsRecoverableWithoutAnError() = runBlocking {
        val api = FakeApi()
        api.failWrite = true
        try { api.repository.call("/v1/families/family-a/invitations", "POST", JSONObject(), true) }
        catch (_: IOException) { }
        val model = CompanionModel(api.repository, false, "fictional-device", this)
        model.idle()
        assertTrue(model.state.value.pendingWrite)
        assertEquals("", model.state.value.error)
        model.reload(); model.idle()
        assertTrue(model.state.value.pendingWrite)
        model.retry(); model.idle()
        assertFalse(model.state.value.pendingWrite)
        assertEquals("fictional-invitation", model.state.value.invite)
    }

    @Test fun retryingAnInvitationAfterSwitchingFamilyReturnsToItsOwnFamily() = runBlocking {
        val api = FakeApi()
        api.failWrite = true
        try { api.repository.call("/v1/families/family-a/invitations", "POST", JSONObject(), true) }
        catch (_: IOException) { }
        val model = CompanionModel(api.repository, false, "fictional-device", this)
        model.idle(); model.choose("family-b"); model.idle()
        model.retry(); model.idle()
        assertEquals("family-a", model.state.value.selected?.id)
        assertEquals("fictional-invitation", model.state.value.invite)
        model.choose("family-b"); model.idle()
        assertEquals("", model.state.value.invite)
    }

    @Test fun ordinaryActiveMemberCanLoadTheirFamilyWithoutMemberReadPermission() = runBlocking {
        val api = FakeApi().apply { admin = false }
        val model = CompanionModel(api.repository, false, "fictional-device", this)
        model.idle()
        assertEquals("family-a", model.state.value.selected?.id)
        assertEquals("", model.state.value.error)
        assertFalse(model.state.value.canManageMembers)
        assertTrue(api.requests.none { it.url.path.endsWith("/members") })
    }

    @Test fun consentOnLaterPageIsNotShownAsMissing() = runBlocking {
        val api = FakeApi().apply { secondConsentPage = true }
        val model = CompanionModel(api.repository, false, "fictional-device", this)
        model.idle()
        assertEquals("GRANTED", model.state.value.permissions.single().status)
        assertTrue(api.requests.any { it.url.query?.contains("cursor=page.2") == true })
    }

    @Test fun repeatedPaginationCursorFailsInsteadOfLoopingOrShowingPartialData() = runBlocking {
        val api = FakeApi()
        api.handler = { page(emptyList(), "same-cursor") }
        try { api.repository.readAll("/v1/families?limit=100"); fail("Expected invalid page") }
        catch (error: ApiFailure) { assertEquals("INVALID_PAGE", error.code) }
        assertEquals(2, api.requests.size)
    }

    @Test fun offlineStartupPreservesTheExistingSessionAndPendingWrite() = runBlocking {
        val api = FakeApi()
        api.failWrite = true
        try { api.repository.call("/v1/families/family-a/invitations", "POST", JSONObject(), true) }
        catch (_: IOException) { }
        api.offline = true
        val model = CompanionModel(api.repository, false, "fictional-device", this)
        model.idle()
        assertTrue(model.state.value.loggedIn)
        assertTrue(model.state.value.offline)
        assertTrue(model.state.value.pendingWrite)
    }
}
