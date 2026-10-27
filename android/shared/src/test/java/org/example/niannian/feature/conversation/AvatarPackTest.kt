package org.example.niannian.feature.conversation

import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import java.io.ByteArrayInputStream
import java.io.ByteArrayOutputStream
import java.nio.ByteBuffer
import java.util.zip.CRC32
import java.util.zip.DeflaterOutputStream
import java.util.zip.ZipEntry
import java.util.zip.ZipOutputStream

internal fun avatarFixture(modify: (JSONObject) -> Unit = {}, extraEntry: String? = null): ByteArray {
    val png = ByteArrayOutputStream()
    png.write(byteArrayOf(-119, 80, 78, 71, 13, 10, 26, 10))
    fun chunk(type: String, bytes: ByteArray) {
        val named = type.toByteArray(Charsets.US_ASCII) + bytes
        png.write(ByteBuffer.allocate(4).putInt(bytes.size).array()); png.write(named)
        png.write(ByteBuffer.allocate(4).putInt(CRC32().apply { update(named) }.value.toInt()).array())
    }
    chunk("IHDR", ByteBuffer.allocate(13).putInt(1024).putInt(256).put(byteArrayOf(8, 6, 0, 0, 0)).array())
    val compressed = ByteArrayOutputStream()
    DeflaterOutputStream(compressed).use { it.write(ByteArray((1024 * 4 + 1) * 256)) }
    chunk("IDAT", compressed.toByteArray()); chunk("IEND", byteArrayOf())
    val states = JSONObject()
    CompanionPhase.entries.forEach { states.put(it.name, JSONObject().put("file", it.name.lowercase() + ".png").put("frames", 1).put("fps", 4)) }
    val manifest = JSONObject().put("format", "niannian-tha3-v1").put("frame_size", 256).put("columns", 4)
        .put("credits", "Synthetic fixture").put("states", states)
    modify(manifest)
    val output = ByteArrayOutputStream()
    ZipOutputStream(output).use { zip ->
        zip.putNextEntry(ZipEntry("manifest.json")); zip.write(manifest.toString().toByteArray()); zip.closeEntry()
        CompanionPhase.entries.forEach {
            zip.putNextEntry(ZipEntry(it.name.lowercase() + ".png")); zip.write(png.toByteArray()); zip.closeEntry()
        }
        extraEntry?.let { zip.putNextEntry(ZipEntry(it)); zip.write(1); zip.closeEntry() }
    }
    return output.toByteArray()
}

class AvatarPackTest {
    @Test fun parsesBoundedPngSheetsForAllFourRealConversationPhases() {
        val pack = AvatarPack.parse(avatarFixture())
        assertEquals(CompanionPhase.entries.toSet(), pack.clips.keys)
        assertEquals("Synthetic fixture", pack.credits)
        assertEquals(1024, pack.clips.getValue(CompanionPhase.IDLE).width)
        val clip = AvatarClip(byteArrayOf(), 8, 10)
        assertEquals(0, clip.frameAt(0)); assertEquals(7, clip.frameAt(700)); assertEquals(0, clip.frameAt(800))
    }

    @Test fun rejectsPathsUnknownFormatsAndExcessivePixelsBeforeBitmapAllocation() {
        val invalid = listOf(avatarFixture(extraEntry = "../private.png"),
            avatarFixture({ it.put("format", "something-else") }),
            avatarFixture({ it.put("frame_size", 8192) }),
            avatarFixture({ it.getJSONObject("states").getJSONObject("SPEAKING").put("frames", 10000) }),
            avatarFixture({ it.getJSONObject("states").getJSONObject("IDLE").put("file", "speaking.png") }),
            avatarFixture({ it.getJSONObject("states").getJSONObject("IDLE").put("frames", 8) }))
        invalid.forEach { bytes ->
            try { AvatarPack.parse(bytes); fail("Expected invalid pack rejection") }
            catch (_: IllegalArgumentException) { }
        }
    }

    @Test fun compressedInputMustRespectReadBudget() {
        try { AvatarPack.readLimited(ByteArrayInputStream(ByteArray(100)), 50); fail("Expected byte limit") }
        catch (_: IllegalArgumentException) { }
    }
}
