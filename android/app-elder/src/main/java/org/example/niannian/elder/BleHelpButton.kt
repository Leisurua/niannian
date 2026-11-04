package org.example.niannian.elder

import android.Manifest
import android.annotation.SuppressLint
import android.bluetooth.BluetoothDevice
import android.bluetooth.BluetoothGatt
import android.bluetooth.BluetoothGattCallback
import android.bluetooth.BluetoothGattCharacteristic
import android.bluetooth.BluetoothGattDescriptor
import android.bluetooth.BluetoothManager
import android.bluetooth.BluetoothProfile
import android.bluetooth.BluetoothStatusCodes
import android.bluetooth.le.BluetoothLeScanner
import android.bluetooth.le.ScanCallback
import android.bluetooth.le.ScanFilter
import android.bluetooth.le.ScanResult
import android.bluetooth.le.ScanSettings
import android.content.Context
import android.content.pm.PackageManager
import android.os.Build
import android.os.Handler
import android.os.Looper
import android.os.ParcelUuid
import android.os.SystemClock
import java.nio.ByteBuffer
import java.util.UUID
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asSharedFlow
import kotlinx.coroutines.flow.asStateFlow

internal val blePermissions = arrayOf(Manifest.permission.BLUETOOTH_SCAN, Manifest.permission.BLUETOOTH_CONNECT)
private val serviceId = UUID.fromString("a969ba54-806f-4d1b-b763-640c13563949")
private val eventId = UUID.fromString("a969ba55-806f-4d1b-b763-640c13563949")
private val descriptorId = UUID.fromString("00002902-0000-1000-8000-00805f9b34fb")

internal fun decodeHelpPress(frame: ByteArray): String? {
    if (frame.size != 17 || frame[0] != 1.toByte()) return null
    val data = ByteBuffer.wrap(frame, 1, 16)
    val key = UUID(data.long, data.long)
    return key.takeIf { it.version() == 4 && it.variant() == 2 }?.toString()
}

internal data class HelpButtonTarget(val user: String, val family: String)
internal data class HelpButtonState(val message: String = "", val bound: Boolean = false,
    val scanning: Boolean = false, val pairing: Boolean = false, val candidates: List<String> = emptyList())

/** GATT is active only while the elder app is visible and has a matching family binding. */
@SuppressLint("MissingPermission")
internal class BleHelpButton(context: Context) {
    private val app = context.applicationContext
    private val bluetooth = app.getSystemService(BluetoothManager::class.java)?.adapter
    private val preferences = app.getSharedPreferences("paired-help-button", Context.MODE_PRIVATE)
    private val main = Handler(Looper.getMainLooper())
    private val current = MutableStateFlow(HelpButtonState())
    val state = current.asStateFlow()
    private val received = MutableSharedFlow<String>(extraBufferCapacity = 8)
    val presses = received.asSharedFlow()
    private val seen = linkedSetOf<String>()
    private var target: HelpButtonTarget? = null
    private var visible = false
    private var scanner: BluetoothLeScanner? = null
    private val found = linkedMapOf<String, BluetoothDevice>()
    private var pairing: BluetoothDevice? = null
    private var pairingUntil = 0L
    private var gatt: BluetoothGatt? = null
    private var subscribed = false

    private val reconnect = Runnable { connect() }
    private val timeout = Runnable { if (gatt != null && !subscribed) disconnected("连接超时") }
    private val endScan = Runnable {
        stopScan()
        if (found.isEmpty()) message("未找到按钮。请让按钮进入配对模式并靠近平板。")
        else message("请选择要绑定的按钮。")
    }
    private val checkBond = Runnable { finishPairing() }

    fun availablePermissions() = Build.VERSION.SDK_INT >= 31 && blePermissions.all {
        app.checkSelfPermission(it) == PackageManager.PERMISSION_GRANTED
    }

    fun activate(value: HelpButtonTarget?) {
        if (value == target) return
        main.removeCallbacks(checkBond)
        stopScan()
        closeGatt()
        pairing = null
        found.clear()
        target = value
        current.value = HelpButtonState()
        connect()
    }

    fun setVisible(value: Boolean) {
        if (visible == value) return
        visible = value
        if (value) {
            if (pairing != null) finishPairing() else connect()
        } else {
            main.removeCallbacks(checkBond)
            stopScan()
            closeGatt()
        }
    }

    fun forgetOnSessionInvalidated() { main.post { clearBinding() } }
    fun reconnectNow() { main.removeCallbacks(reconnect); connect() }

    fun clearBinding() {
        preferences.edit().clear().apply()
        main.removeCallbacks(checkBond)
        stopScan()
        closeGatt()
        pairing = null
        found.clear()
        current.value = HelpButtonState(message = "已解除本应用的按钮绑定。")
    }

    private fun address(): String? = target?.let { binding ->
        if (preferences.getString("user", "") == binding.user && preferences.getString("family", "") == binding.family)
            preferences.getString("address", null) else null
    }

    private fun message(text: String) { current.value = current.value.copy(message = text) }

    private fun usable(): Boolean {
        if (!visible) return false
        if (target == null) {
            message("请先登录并选择当前家庭。")
            return false
        }
        if (Build.VERSION.SDK_INT < 31 || bluetooth == null || !app.packageManager.hasSystemFeature(PackageManager.FEATURE_BLUETOOTH_LE)) {
            message("此功能需要 Android 12 或更新版本及 BLE 支持。请使用屏幕求助按钮。")
            return false
        }
        if (!availablePermissions()) {
            message("附近设备权限未开启。请使用屏幕求助按钮。")
            return false
        }
        if (!bluetooth.isEnabled) {
            message("蓝牙已关闭。请开启蓝牙，或使用屏幕求助按钮。")
            return false
        }
        return true
    }

    fun scan() {
        if (pairing != null || scanner != null || !usable()) return
        found.clear()
        current.value = HelpButtonState(message = "正在寻找念念求助按钮…", scanning = true)
        try {
            val adapterScanner = bluetooth?.bluetoothLeScanner ?: error("No scanner")
            scanner = adapterScanner
            adapterScanner.startScan(listOf(ScanFilter.Builder().setServiceUuid(ParcelUuid(serviceId)).build()),
                ScanSettings.Builder().setScanMode(ScanSettings.SCAN_MODE_LOW_LATENCY).build(), scanCallback)
            main.postDelayed(endScan, 12_000)
        } catch (_: Exception) {
            stopScan()
            message("无法搜索蓝牙按钮。请检查权限和蓝牙状态。")
        }
    }

    private val scanCallback = object : ScanCallback() {
        override fun onScanResult(callbackType: Int, result: ScanResult) {
            main.post {
                if (scanner == null || found.size >= 8) return@post
                val device = result.device
                found[device.address] = device
                current.value = current.value.copy(candidates = found.keys.toList())
            }
        }
        override fun onScanFailed(errorCode: Int) {
            main.post {
                if (scanner != null) {
                    stopScan()
                    message("搜索失败，请重新开启蓝牙后重试。")
                }
            }
        }
    }

    private fun stopScan() {
        main.removeCallbacks(endScan)
        scanner?.let { runCatching { it.stopScan(scanCallback) } }
        scanner = null
        current.value = current.value.copy(scanning = false)
    }

    fun select(address: String) {
        if (!usable() || pairing != null) return
        val device = found[address] ?: return
        stopScan()
        current.value = HelpButtonState(message = "请按系统提示完成配对。", pairing = true)
        try {
            pairing = device
            pairingUntil = SystemClock.elapsedRealtime() + 45_000
            if (device.bondState == BluetoothDevice.BOND_NONE && !device.createBond()) error("Bond failed")
            finishPairing()
        } catch (_: Exception) { pairingFailed() }
    }

    private fun finishPairing() {
        val device = pairing ?: return
        val binding = target ?: return
        try {
            when {
                !availablePermissions() || SystemClock.elapsedRealtime() >= pairingUntil -> pairingFailed()
                device.bondState == BluetoothDevice.BOND_BONDED -> {
                    preferences.edit().putString("user", binding.user).putString("family", binding.family)
                        .putString("address", device.address).apply()
                    pairing = null
                    found.clear()
                    current.value = HelpButtonState(bound = true, message = "已配对，正在连接按钮…")
                    connect()
                }
                else -> main.postDelayed(checkBond, 700)
            }
        } catch (_: Exception) { pairingFailed() }
    }

    private fun pairingFailed() {
        pairing = null
        current.value = HelpButtonState(message = "配对未完成。请检查串口配对码并重新搜索。")
    }

    private fun connect() {
        if (!visible || gatt != null || pairing != null) return
        val address = address()
        current.value = current.value.copy(bound = address != null)
        if (!usable()) {
            if (address != null && availablePermissions()) main.postDelayed(reconnect, 6_000)
            return
        }
        if (address == null) {
            message("蓝牙求助按钮未绑定。")
            return
        }
        try {
            val device = bluetooth?.getRemoteDevice(address) ?: error("Missing device")
            if (device.bondState != BluetoothDevice.BOND_BONDED) {
                clearBinding()
                message("系统配对已失效，请重新绑定。")
                return
            }
            message("正在连接求助按钮…")
            gatt = device.connectGatt(app, false, callback, BluetoothDevice.TRANSPORT_LE) ?: error("Connection failed")
            main.postDelayed(timeout, 15_000)
        } catch (_: Exception) { disconnected("连接失败") }
    }

    private fun disconnected(reason: String) {
        closeGatt()
        message(reason + "。正在尝试重连，必要时请使用屏幕求助按钮。")
        if (address() != null) main.postDelayed(reconnect, 5_000)
    }

    private fun closeGatt() {
        main.removeCallbacks(timeout)
        main.removeCallbacks(reconnect)
        val connection = gatt
        gatt = null
        subscribed = false
        if (connection != null) runCatching { connection.close() }
    }

    private val callback = object : BluetoothGattCallback() {
        override fun onConnectionStateChange(connection: BluetoothGatt, status: Int, newState: Int) {
            main.post {
                if (connection !== gatt) return@post
                if (status != BluetoothGatt.GATT_SUCCESS || newState == BluetoothProfile.STATE_DISCONNECTED) {
                    disconnected("求助按钮已断开")
                } else if (newState == BluetoothProfile.STATE_CONNECTED &&
                    !runCatching { connection.discoverServices() }.getOrDefault(false)) {
                    disconnected("无法读取按钮服务")
                }
            }
        }

        override fun onServicesDiscovered(connection: BluetoothGatt, status: Int) {
            main.post {
                if (connection !== gatt) return@post
                val characteristic = connection.getService(serviceId)?.getCharacteristic(eventId)
                val descriptor = characteristic?.getDescriptor(descriptorId)
                if (status != BluetoothGatt.GATT_SUCCESS || characteristic == null || descriptor == null ||
                    (characteristic.properties and BluetoothGattCharacteristic.PROPERTY_INDICATE) == 0) {
                    disconnected("按钮协议不匹配")
                    return@post
                }
                if (!runCatching {
                    connection.setCharacteristicNotification(characteristic, true) && subscribe(connection, descriptor)
                }.getOrDefault(false)) disconnected("无法订阅按钮事件")
            }
        }

        override fun onDescriptorWrite(connection: BluetoothGatt, descriptor: BluetoothGattDescriptor, status: Int) {
            main.post {
                if (connection !== gatt || descriptor.uuid != descriptorId || descriptor.characteristic.uuid != eventId) return@post
                if (status == BluetoothGatt.GATT_SUCCESS) {
                    main.removeCallbacks(timeout)
                    subscribed = true
                    message("蓝牙求助按钮已连接。")
                } else disconnected("按钮订阅未成功")
            }
        }

        override fun onCharacteristicChanged(connection: BluetoothGatt, characteristic: BluetoothGattCharacteristic, value: ByteArray) {
            accept(connection, characteristic, value.copyOf())
        }

        @Deprecated("Android callback before API 33")
        override fun onCharacteristicChanged(connection: BluetoothGatt, characteristic: BluetoothGattCharacteristic) {
            characteristic.value?.let { accept(connection, characteristic, it.copyOf()) }
        }
    }

    @Suppress("DEPRECATION")
    private fun subscribe(connection: BluetoothGatt, descriptor: BluetoothGattDescriptor): Boolean {
        val value = BluetoothGattDescriptor.ENABLE_INDICATION_VALUE
        if (Build.VERSION.SDK_INT >= 33) return connection.writeDescriptor(descriptor, value) == BluetoothStatusCodes.SUCCESS
        descriptor.value = value
        return connection.writeDescriptor(descriptor)
    }

    private fun accept(connection: BluetoothGatt, characteristic: BluetoothGattCharacteristic, value: ByteArray) {
        if (characteristic.uuid != eventId || characteristic.service.uuid != serviceId) return
        val id = decodeHelpPress(value) ?: return
        main.post {
            if (connection !== gatt || !subscribed || !availablePermissions() || address() != connection.device.address ||
                !runCatching { connection.device.bondState == BluetoothDevice.BOND_BONDED }.getOrDefault(false) || id in seen) return@post
            if (received.tryEmit(id)) {
                seen.add(id)
                if (seen.size > 64) seen.remove(seen.first())
            }
        }
    }
}
