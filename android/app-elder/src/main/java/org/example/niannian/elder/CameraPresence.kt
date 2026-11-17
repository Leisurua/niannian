package org.example.niannian.elder

import android.Manifest
import android.annotation.SuppressLint
import android.content.Context
import android.content.pm.PackageManager
import android.graphics.ImageFormat
import android.graphics.Rect
import android.hardware.camera2.CameraCaptureSession
import android.hardware.camera2.CameraCharacteristics
import android.hardware.camera2.CameraDevice
import android.hardware.camera2.CameraManager
import android.hardware.camera2.CaptureRequest
import android.hardware.camera2.CaptureResult
import android.hardware.camera2.TotalCaptureResult
import android.media.ImageReader
import android.os.Handler
import android.os.Looper
import android.os.SystemClock
import kotlin.math.abs

/** Uses only the front camera's simple face bounds. Image buffers are discarded. */
internal class CameraPresence(private val context: Context, private val ready: () -> Unit,
    private val failed: (String) -> Unit, private val detected: () -> Unit) : AutoCloseable {
    private val manager = context.getSystemService(CameraManager::class.java)
    private val handler = Handler(Looper.getMainLooper())
    private var closed = false
    private var device: CameraDevice? = null
    private var session: CameraCaptureSession? = null
    private var reader: ImageReader? = null

    @SuppressLint("MissingPermission")
    fun open() {
        if (closed) return
        if (context.checkSelfPermission(Manifest.permission.CAMERA) != PackageManager.PERMISSION_GRANTED) {
            fail("摄像头未授权，仍可点击唤醒。")
            return
        }
        try {
            val id = manager.cameraIdList.firstOrNull { cameraId ->
                val camera = manager.getCameraCharacteristics(cameraId)
                camera.get(CameraCharacteristics.LENS_FACING) == CameraCharacteristics.LENS_FACING_FRONT &&
                    CaptureRequest.STATISTICS_FACE_DETECT_MODE_SIMPLE in
                    (camera.get(CameraCharacteristics.STATISTICS_INFO_AVAILABLE_FACE_DETECT_MODES) ?: intArrayOf())
            } ?: run {
                fail("设备没有支持本地存在检测的前置摄像头。")
                return
            }
            val camera = manager.getCameraCharacteristics(id)
            val sensor = camera.get(CameraCharacteristics.SENSOR_INFO_ACTIVE_ARRAY_SIZE) ?: error("Missing sensor size")
            val size = camera.get(CameraCharacteristics.SCALER_STREAM_CONFIGURATION_MAP)
                ?.getOutputSizes(ImageFormat.YUV_420_888)?.minByOrNull { abs(it.width * it.height - 640 * 480) }
                ?: error("Unsupported camera output")
            val output = ImageReader.newInstance(size.width, size.height, ImageFormat.YUV_420_888, 2)
            reader = output
            output.setOnImageAvailableListener({ source ->
                if (!closed) runCatching { source.acquireLatestImage()?.close() }
            }, handler)
            manager.openCamera(id, object : CameraDevice.StateCallback() {
                override fun onOpened(camera: CameraDevice) {
                    if (closed) camera.close()
                    else {
                        device = camera
                        capture(camera, output, sensor)
                    }
                }
                override fun onDisconnected(camera: CameraDevice) {
                    camera.close()
                    fail("摄像头已断开或被其他应用占用。")
                }
                override fun onError(camera: CameraDevice, error: Int) {
                    camera.close()
                    fail("摄像头暂不可用，请点击唤醒。")
                }
            }, handler)
        } catch (_: Exception) {
            fail("无法启用摄像头，请检查权限或占用情况。")
        }
    }

    @Suppress("DEPRECATION")
    private fun capture(camera: CameraDevice, output: ImageReader, sensor: Rect) {
        try {
            camera.createCaptureSession(listOf(output.surface), object : CameraCaptureSession.StateCallback() {
                override fun onConfigured(active: CameraCaptureSession) {
                    if (closed) {
                        active.close()
                        return
                    }
                    session = active
                    try {
                        val request = camera.createCaptureRequest(CameraDevice.TEMPLATE_PREVIEW).apply {
                            addTarget(output.surface)
                            set(CaptureRequest.STATISTICS_FACE_DETECT_MODE, CaptureRequest.STATISTICS_FACE_DETECT_MODE_SIMPLE)
                        }
                        active.setRepeatingRequest(request.build(), object : CameraCaptureSession.CaptureCallback() {
                            private var nearbySince: Long? = null
                            private var sampledAt = 0L
                            override fun onCaptureCompleted(s: CameraCaptureSession, r: CaptureRequest, result: TotalCaptureResult) {
                                val now = SystemClock.elapsedRealtime()
                                if (closed || now - sampledAt < 180) return
                                if (now - sampledAt > 600) nearbySince = null
                                sampledAt = now
                                val nearby = result.get(CaptureResult.STATISTICS_FACES).orEmpty().any { face ->
                                    face.score >= 65 && face.bounds.width() >= sensor.width() * 0.16 &&
                                        face.bounds.height() >= sensor.height() * 0.16
                                }
                                if (!nearby) {
                                    nearbySince = null
                                    return
                                }
                                val first = nearbySince ?: now.also { nearbySince = it }
                                if (now - first >= 1_200) {
                                    close()
                                    detected()
                                }
                            }
                        }, handler)
                        ready()
                    } catch (_: Exception) { fail("无法读取摄像头状态，请点击唤醒。") }
                }
                override fun onConfigureFailed(active: CameraCaptureSession) {
                    active.close()
                    fail("设备无法启动存在检测，请点击唤醒。")
                }
            }, handler)
        } catch (_: Exception) { fail("摄像头暂不可用，请点击唤醒。") }
    }

    private fun fail(message: String) {
        if (closed) return
        close()
        failed(message)
    }

    override fun close() {
        if (closed) return
        closed = true
        runCatching { session?.close() }
        runCatching { device?.close() }
        runCatching { reader?.close() }
    }
}
