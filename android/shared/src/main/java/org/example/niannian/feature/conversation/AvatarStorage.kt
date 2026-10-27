package org.example.niannian.feature.conversation

import android.content.Context
import android.graphics.BitmapFactory
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.AtomicFile
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.ensureActive
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.withContext
import java.io.File
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

class AvatarStorage private constructor(context: Context) : AvatarStore {
    private val file = AtomicFile(File(context.noBackupFilesDir, "companion-avatar.enc"))
    private val aad = context.packageName + ":portrait:v1:"
    private val alias = "niannian-portrait-key"
    private val lock = Any()
    private val currentRevision = MutableStateFlow(0)
    override val revision = currentRevision.asStateFlow()

    private fun key(create: Boolean): SecretKey? {
        val keys = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        (keys.getKey(alias, null) as? SecretKey)?.let { return it }
        if (!create) return null
        return KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore").apply {
            init(KeyGenParameterSpec.Builder(alias, KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT)
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM).setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .setKeySize(256).build())
        }.generateKey()
    }

    override fun invalidate() = synchronized(lock) {
        currentRevision.value++
        KeyStore.getInstance("AndroidKeyStore").apply { load(null); deleteEntry(alias) }
        file.delete()
    }

    override suspend fun load(binding: String): ByteArray? = withContext(Dispatchers.IO) { synchronized(lock) {
        if (!file.baseFile.exists()) return@synchronized null
        try {
            val bytes = file.openRead().use { AvatarPack.readLimited(it, AvatarPack.MAX_BYTES + 28) }
            require(bytes.size > 28)
            val cipher = Cipher.getInstance("AES/GCM/NoPadding")
            cipher.init(Cipher.DECRYPT_MODE, checkNotNull(key(false)), GCMParameterSpec(128, bytes.copyOfRange(0, 12)))
            cipher.updateAAD((aad + binding).toByteArray(Charsets.UTF_8))
            cipher.doFinal(bytes.copyOfRange(12, bytes.size))
        } catch (_: Exception) { invalidate(); null }
    } }

    override suspend fun save(binding: String, bytes: ByteArray, expectedRevision: Int) = withContext(Dispatchers.IO) {
        val task = currentCoroutineContext()
        val pack = AvatarPack.parse(bytes)
        pack.clips.values.forEach { clip ->
            val bitmap = BitmapFactory.decodeByteArray(clip.png, 0, clip.png.size)
                ?: throw IllegalArgumentException("Invalid PNG")
            try { require(bitmap.width == clip.width && bitmap.height == clip.height) }
            finally { bitmap.recycle() }
        }
        synchronized(lock) {
            task.ensureActive()
            check(currentRevision.value == expectedRevision) { "Portrait invalidated" }
            val cipher = Cipher.getInstance("AES/GCM/NoPadding")
            cipher.init(Cipher.ENCRYPT_MODE, key(true))
            cipher.updateAAD((aad + binding).toByteArray(Charsets.UTF_8))
            val encrypted = cipher.iv + cipher.doFinal(bytes)
            val output = file.startWrite()
            try { output.write(encrypted); file.finishWrite(output) }
            catch (error: Exception) { file.failWrite(output); throw error }
        }
    }

    companion object {
        @Volatile private var instance: AvatarStorage? = null
        fun get(context: Context): AvatarStorage = instance ?: synchronized(this) {
            instance ?: AvatarStorage(context.applicationContext).also { instance = it }
        }
    }
}
