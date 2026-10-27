package org.example.niannian.feature.conversation

import org.json.JSONObject
import java.io.ByteArrayInputStream
import java.io.ByteArrayOutputStream
import java.io.InputStream
import java.nio.ByteBuffer
import java.util.zip.ZipInputStream

data class AvatarClip(val png: ByteArray, val frames: Int, val fps: Int) {
    val width get() = 4 * 256
    val height get() = ((frames + 3) / 4) * 256
    fun frameAt(elapsedMillis: Long) = ((elapsedMillis.coerceAtLeast(0) / (1000L / fps)) % frames).toInt()
}

data class AvatarPack(val clips: Map<CompanionPhase, AvatarClip>, val credits: String) {
    companion object {
        const val MAX_BYTES = 24 * 1024 * 1024
        fun readLimited(input: InputStream, limit: Int = MAX_BYTES): ByteArray {
            val out = ByteArrayOutputStream()
            val buffer = ByteArray(8192)
            while (true) {
                val count = input.read(buffer)
                if (count < 0) break
                require(out.size().toLong() + count <= limit) { "角色包过大，请重新制作。" }
                out.write(buffer, 0, count)
            }
            return out.toByteArray()
        }

        fun parse(bytes: ByteArray): AvatarPack {
            require(bytes.size <= MAX_BYTES)
            val names = CompanionPhase.entries.associateWith { it.name.lowercase() + ".png" }
            val allowed = names.values.toSet() + "manifest.json"
            val files = mutableMapOf<String, ByteArray>()
            var total = 0L
            ZipInputStream(ByteArrayInputStream(bytes)).use { zip ->
                while (true) {
                    val entry = zip.nextEntry ?: break
                    require(!entry.isDirectory && entry.name in allowed && entry.name !in files) { "角色包包含无效或重复文件。" }
                    val data = readLimited(zip, if (entry.name == "manifest.json") 8192 else 6 * 1024 * 1024)
                    total += data.size
                    require(total <= MAX_BYTES)
                    files[entry.name] = data
                }
            }
            require(files.keys == allowed) { "角色包缺少四种状态，请使用念念制作脚本导出。" }
            val manifest = JSONObject(String(files.getValue("manifest.json"), Charsets.UTF_8))
            require(manifest.getString("format") == "niannian-tha3-v1" && manifest.getInt("frame_size") == 256 && manifest.getInt("columns") == 4)
            val credits = manifest.getString("credits")
            require(credits.isNotBlank() && credits.length <= 2048)
            val states = manifest.getJSONObject("states")
            require(states.keys().asSequence().toSet() == CompanionPhase.entries.map { it.name }.toSet())
            val clips = names.mapValues { (phase, file) ->
                val value = states.getJSONObject(phase.name)
                require(value.getString("file") == file)
                val frames = value.getInt("frames"); val fps = value.getInt("fps")
                require(frames in 1..16 && fps in 1..15)
                val png = files.getValue(file)
                val clip = AvatarClip(png, frames, fps)
                require(png.size >= 33 && png.copyOfRange(0, 8).contentEquals(byteArrayOf(-119, 80, 78, 71, 13, 10, 26, 10)))
                val header = ByteBuffer.wrap(png)
                require(header.getInt(8) == 13 && header.getInt(12) == 0x49484452)
                require(header.getInt(16) == clip.width && header.getInt(20) == clip.height && png[24].toInt() == 8 && png[25].toInt() == 6) {
                    "角色图片尺寸或格式不支持。"
                }
                clip
            }
            return AvatarPack(clips, credits)
        }
    }
}
