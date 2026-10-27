package org.example.niannian.feature.conversation

import kotlinx.coroutines.*
import kotlinx.coroutines.flow.MutableStateFlow
import org.junit.Assert.*
import org.junit.Test
import java.time.Instant

class AvatarModelTest {
    private class Gateway : PortraitGateway {
        var value: PortraitGrant? = PortraitGrant("grant-1", null)
        var fail = false
        override suspend fun grant(family: String, user: String): PortraitGrant? {
            if (fail) error("offline")
            return value
        }
    }
    private class Store : AvatarStore {
        override val revision = MutableStateFlow(0)
        var bytes: ByteArray? = null
        var binding = ""
        var saves = 0
        var loadStarted: CompletableDeferred<Unit>? = null
        var loadRelease: CompletableDeferred<Unit>? = null
        override fun invalidate() { revision.value++; bytes = null; binding = "" }
        override suspend fun load(binding: String): ByteArray? {
            if (bytes == null) return null
            if (binding != this.binding) { invalidate(); return null }
            val captured = bytes
            loadStarted?.complete(Unit)
            loadRelease?.let { withContext(NonCancellable) { it.await() } }
            return captured
        }
        override suspend fun save(binding: String, bytes: ByteArray, expectedRevision: Int) {
            check(revision.value == expectedRevision)
            this.binding = binding; this.bytes = bytes; saves++
        }
    }
    private class Rig(scope: CoroutineScope) {
        val gateway = Gateway()
        val store = Store()
        val model = AvatarModel(gateway, store, scope)
        suspend fun ready() = withTimeout(5000) { while (!model.state.value.allowed) delay(10) }
        suspend fun importAvatar() {
            model.importPack { avatarFixture() }!!.join()
            assertNotNull(model.state.value.pack)
        }
    }
    private fun scenario(work: suspend Rig.() -> Unit) = runBlocking {
        val job = SupervisorJob(coroutineContext[Job])
        val rig = Rig(CoroutineScope(coroutineContext + job))
        try { rig.work() } finally { rig.model.hide(); job.cancelAndJoin() }
    }

    @Test fun explicitConsentIsRequiredAndRevocationErasesBeforeRegrant() = scenario {
        gateway.value = null
        model.bind("family", "elder"); yield()
        assertNull(model.importPack { avatarFixture() })
        assertFalse(model.state.value.allowed)
        gateway.value = PortraitGrant("grant-1", null)
        model.recheck("family", "elder"); ready(); importAvatar()
        assertEquals("family:elder:grant-1", store.binding)
        gateway.value = null
        model.recheck("family", "elder"); yield()
        assertNull(store.bytes); assertNull(model.state.value.pack)
        gateway.value = PortraitGrant("grant-2", null)
        model.recheck("family", "elder"); ready()
        assertNull(model.state.value.pack)
    }

    @Test fun backgroundAndNetworkFailureHideUntilFreshConsent() = scenario {
        model.bind("family", "elder"); ready(); importAvatar()
        model.hide()
        assertNull(model.state.value.pack)
        assertNotNull(store.bytes)
        gateway.fail = true
        model.bind("family", "elder"); yield()
        assertFalse(model.state.value.allowed); assertNull(model.state.value.pack)
        gateway.fail = false
        model.recheck("family", "elder"); ready()
        assertNotNull(model.state.value.pack)
        model.bind("other", "elder"); ready()
        assertNull(model.state.value.pack); assertNull(store.bytes)
    }

    @Test fun removalOrLeavingDuringImportCannotPersistOrRestoreLateImages() = scenario {
        for (leave in listOf("remove", "background", "family")) {
            model.bind("family", "elder"); ready()
            val started = CompletableDeferred<Unit>(); val release = CompletableDeferred<Unit>()
            val before = store.saves
            val importing = model.importPack {
                started.complete(Unit)
                withContext(NonCancellable) { release.await() }
                avatarFixture()
            }!!
            started.await()
            when (leave) {
                "remove" -> model.remove()
                "family" -> model.bind("other", "elder")
                else -> model.hide()
            }
            release.complete(Unit); importing.join()
            assertEquals(before, store.saves)
            assertNull(model.state.value.pack)
            model.hide()
        }
    }

    @Test fun invalidationDuringDiskReadCannotReviveDecryptedPortrait() = scenario {
        store.bytes = avatarFixture(); store.binding = "family:elder:grant-1"
        store.loadStarted = CompletableDeferred(); store.loadRelease = CompletableDeferred()
        model.bind("family", "elder"); store.loadStarted!!.await()
        store.invalidate(); yield()
        store.loadRelease!!.complete(Unit); ready()
        assertNull(model.state.value.pack)
    }

    @Test fun consentExpiryStopsDisplayWithoutWaitingForNextPoll() = scenario {
        gateway.value = PortraitGrant("short-grant", Instant.now().plusMillis(1500))
        model.bind("family", "elder"); ready(); importAvatar()
        withTimeout(4000) { while (model.state.value.pack != null) delay(20) }
        assertFalse(model.state.value.allowed)
        assertNull(model.state.value.pack)
        assertNull(store.bytes)
    }
}
