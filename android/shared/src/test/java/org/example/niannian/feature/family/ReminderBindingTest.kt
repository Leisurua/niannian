package org.example.niannian.feature.family

import org.example.niannian.data.FamilyRepository
import org.example.niannian.data.SessionStore

import kotlinx.coroutines.runBlocking
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

class ReminderBindingTest {
    @Test fun processRestartPreservesSameFamilyQueueAndSwitchInvalidates() = runBlocking {
        var saved = JSONObject().put("access_token", "fictional-access").put("refresh_token", "fictional-refresh")
        val store = object : SessionStore {
            override fun load() = JSONObject(saved.toString())
            override fun save(value: JSONObject) { saved = JSONObject(value.toString()) }
            override fun clear() { saved = JSONObject() }
        }
        var invalidations = 0
        val first = FamilyRepository(store, false, onCacheInvalidated = { invalidations++ })
        first.noteFamily("family-a")
        assertEquals(1, invalidations)
        val afterRestart = FamilyRepository(store, false, onCacheInvalidated = { invalidations++ })
        assertEquals("family-a", afterRestart.savedFamilyId())
        afterRestart.noteFamily("family-a")
        assertEquals(1, invalidations)
        afterRestart.noteFamily("family-b")
        assertEquals(2, invalidations)
        assertEquals("family-b", store.load().getString("active_family"))
        assertEquals("fictional-access", store.load().getString("access_token"))
        assertEquals("fictional-refresh", store.load().getString("refresh_token"))
    }
}
