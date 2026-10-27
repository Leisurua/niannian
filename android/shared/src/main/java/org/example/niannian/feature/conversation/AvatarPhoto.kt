package org.example.niannian.feature.conversation

import android.content.Context
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Matrix
import android.media.ExifInterface
import android.net.Uri
import java.io.ByteArrayInputStream
import java.io.ByteArrayOutputStream

fun prepareAvatarPhoto(context: Context, uri: Uri): ByteArray {
    val raw = context.contentResolver.openInputStream(uri)?.use { AvatarPack.readLimited(it, 15 * 1024 * 1024) }
        ?: throw IllegalArgumentException("Cannot read photo")
    val bounds = BitmapFactory.Options().apply { inJustDecodeBounds = true }
    BitmapFactory.decodeByteArray(raw, 0, raw.size, bounds)
    require(bounds.outWidth > 0 && bounds.outHeight > 0 && bounds.outWidth.toLong() * bounds.outHeight <= 24000000)
    var sample = 1
    while (maxOf(bounds.outWidth, bounds.outHeight) / sample > 2048) sample *= 2
    val bitmap = BitmapFactory.decodeByteArray(raw, 0, raw.size, BitmapFactory.Options().apply { inSampleSize = sample })
        ?: throw IllegalArgumentException("Cannot decode photo")
    try {
        val orientation = runCatching { ExifInterface(ByteArrayInputStream(raw)).getAttributeInt(ExifInterface.TAG_ORIENTATION, 1) }.getOrDefault(1)
        val matrix = Matrix().apply {
            when (orientation) {
                2 -> setScale(-1f, 1f)
                3 -> setRotate(180f)
                4 -> { setRotate(180f); postScale(-1f, 1f) }
                5 -> { setRotate(90f); postScale(-1f, 1f) }
                6 -> setRotate(90f)
                7 -> { setRotate(-90f); postScale(-1f, 1f) }
                8 -> setRotate(-90f)
            }
            val scale = minOf(1f, 1024f / maxOf(bitmap.width, bitmap.height))
            postScale(scale, scale)
        }
        val prepared = Bitmap.createBitmap(bitmap, 0, 0, bitmap.width, bitmap.height, matrix, true)
        try {
            val out = ByteArrayOutputStream()
            check(prepared.compress(Bitmap.CompressFormat.JPEG, 90, out))
            return out.toByteArray().also { require(it.size <= 5 * 1024 * 1024) }
        } finally { if (prepared !== bitmap) prepared.recycle() }
    } finally { bitmap.recycle() }
}
