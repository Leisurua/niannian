package org.example.niannian.feature.reminder

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import androidx.room.Room
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

interface ReminderStore {
    suspend fun load(): JSONObject
    suspend fun save(value: JSONObject)
    suspend fun clear()
}

class ReminderStorage private constructor(context: Context) : ReminderStore {
    private val database = Room.databaseBuilder(context.applicationContext, ReminderDatabase::class.java, "reminders.db").build()
    private val aad = (context.packageName + ":reminders:v1").toByteArray()
    private val alias = "niannian-reminder-key"
    private val lock = Any()
    private var epoch = 0L
    private fun key(): SecretKey {
        val keys = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        (keys.getKey(alias, null) as? SecretKey)?.let { return it }
        return KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore").apply {
            init(KeyGenParameterSpec.Builder(alias, KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT)
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM).setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .setKeySize(256).build())
        }.generateKey()
    }
    fun revokeEncryptionKey() = synchronized(lock) {
        epoch++
        KeyStore.getInstance("AndroidKeyStore").apply { load(null); deleteEntry(alias) }
    }
    fun whenCurrent(snapshot: JSONObject, action: () -> Unit): Boolean = synchronized(lock) {
        if (snapshot.optLong("_storage_epoch", -1) != epoch) false else { action(); true }
    }
    override suspend fun load(): JSONObject = withContext(Dispatchers.IO) { synchronized(lock) {
        val row = database.snapshots().load() ?: return@synchronized JSONObject().put("_storage_epoch", epoch)
        try {
            require(row.encrypted.size > 28)
            val cipher = Cipher.getInstance("AES/GCM/NoPadding")
            cipher.init(Cipher.DECRYPT_MODE, key(), GCMParameterSpec(128, row.encrypted.copyOfRange(0, 12)))
            cipher.updateAAD(aad)
            JSONObject(String(cipher.doFinal(row.encrypted.copyOfRange(12, row.encrypted.size)), Charsets.UTF_8)).put("_storage_epoch", epoch)
        } catch (_: Exception) {
            database.snapshots().clear()
            JSONObject().put("_storage_epoch", epoch)
        }
    } }
    override suspend fun save(value: JSONObject) = withContext(Dispatchers.IO) { synchronized(lock) {
        check(value.getLong("_storage_epoch") == epoch) { "Cache invalidated" }
        val cipher = Cipher.getInstance("AES/GCM/NoPadding")
        cipher.init(Cipher.ENCRYPT_MODE, key()); cipher.updateAAD(aad)
        val row = ReminderDatabase.Snapshot()
        row.encrypted = cipher.iv + cipher.doFinal(value.toString().toByteArray(Charsets.UTF_8))
        database.runInTransaction { database.snapshots().save(row) }
    } }
    override suspend fun clear() = withContext(Dispatchers.IO) { synchronized(lock) {
        revokeEncryptionKey(); database.snapshots().clear()
    } }
    companion object {
        @Volatile private var instance: ReminderStorage? = null
        fun get(context: Context): ReminderStorage = instance ?: synchronized(this) {
            instance ?: ReminderStorage(context).also { instance = it }
        }
    }
}
