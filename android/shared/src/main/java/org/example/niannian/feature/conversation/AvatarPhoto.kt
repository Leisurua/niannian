package org.example.niannian.feature.conversation

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Matrix
import android.media.ExifInterface
import android.net.Uri
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.PickVisualMediaRequest
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.platform.LocalContext
import androidx.core.content.FileProvider
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.ByteArrayInputStream
import java.io.ByteArrayOutputStream
import java.io.File

class AvatarPhotoProvider : FileProvider()

internal class AvatarPhotoActions(val takePhoto: () -> Unit, val pickPhoto: () -> Unit, val error: String?)

@Composable
internal fun rememberAvatarPhotoActions(
    model: AvatarGenerationModel,
    family: String,
    user: String,
    foreground: Boolean,
): AvatarPhotoActions {
    val context = LocalContext.current
    val state by model.state.collectAsState()
    val captureDirectory = remember(context) { File(context.cacheDir, "avatar-capture") }
    var captureFile by remember { mutableStateOf<File?>(null) }
    var captureUri by remember { mutableStateOf<Uri?>(null) }
    var pendingPhoto by remember { mutableStateOf<Uri?>(null) }
    var error by remember { mutableStateOf<String?>(null) }

    fun deleteCapture() {
        captureFile?.delete()
        captureFile = null
        captureUri = null
    }

    DisposableEffect(captureDirectory) {
        // Clear any private camera file left after the process was stopped.
        captureDirectory.listFiles()?.forEach { it.delete() }
        onDispose { deleteCapture() }
    }

    val gallery = rememberLauncherForActivityResult(ActivityResultContracts.PickVisualMedia()) { uri ->
        pendingPhoto = uri
    }
    val camera = rememberLauncherForActivityResult(ActivityResultContracts.TakePicture()) { saved ->
        if (saved) pendingPhoto = captureUri else deleteCapture()
    }

    fun launchCamera() {
        if (captureFile != null || pendingPhoto != null) return
        try {
            captureDirectory.mkdirs()
            val file = File.createTempFile("photo-", ".jpg", captureDirectory)
            captureFile = file
            val uri = FileProvider.getUriForFile(context, "${context.packageName}.avatar-photo", file)
            captureUri = uri
            camera.launch(uri)
        } catch (_: Exception) {
            deleteCapture()
            error = "无法打开相机，请从相册里选取照片。"
        }
    }

    val cameraPermission = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
        if (granted) launchCamera()
        else error = "未开启相机权限，请在系统设置中开启，或从相册里选取照片。"
    }

    LaunchedEffect(pendingPhoto, foreground, state.available, state.family, state.user) {
        val uri = pendingPhoto ?: return@LaunchedEffect
        if (!foreground || !state.available || state.family != family || state.user != user) return@LaunchedEffect
        try {
            val bytes = withContext(Dispatchers.IO) { prepareAvatarPhoto(context, uri) }
            val current = model.state.value
            if (current.family == family && current.user == user) model.selectedPhoto(bytes)
        } catch (cancelled: CancellationException) {
            throw cancelled
        } catch (_: Exception) {
            model.photoFailed()
        }
        if (uri == captureUri) deleteCapture()
        pendingPhoto = null
    }

    return AvatarPhotoActions(
        takePhoto = {
            error = null
            if (context.checkSelfPermission(Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED) {
                launchCamera()
            } else {
                cameraPermission.launch(Manifest.permission.CAMERA)
            }
        },
        pickPhoto = {
            error = null
            try {
                gallery.launch(PickVisualMediaRequest(ActivityResultContracts.PickVisualMedia.ImageOnly))
            } catch (_: Exception) {
                error = "无法打开相册，请拍摄照片。"
            }
        },
        error = error,
    )
}

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
