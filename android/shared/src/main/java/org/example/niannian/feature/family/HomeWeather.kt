package org.example.niannian.feature.family

import android.content.Context
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalUriHandler
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.compose.LocalLifecycleOwner
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import okhttp3.*
import okhttp3.HttpUrl.Companion.toHttpUrl
import org.json.JSONObject
import java.io.IOException
import java.time.Instant
import java.time.ZoneOffset
import java.time.format.DateTimeFormatter
import java.util.concurrent.TimeUnit
import kotlin.coroutines.resume
import kotlin.coroutines.resumeWithException
import kotlin.math.roundToInt

internal data class WeatherCity(val label: String, val latitude: Double, val longitude: Double, val id: Int? = null) {
    fun json(): String = JSONObject().put("label", label).put("latitude", latitude).put("longitude", longitude)
        .apply { id?.let { put("id", it) } }.toString()
    companion object {
        fun parse(value: JSONObject): WeatherCity {
            val city = WeatherCity(value.getString("label"), value.getDouble("latitude"), value.getDouble("longitude"),
                if (value.has("id")) value.getInt("id").also { require(it > 0) } else null)
            require(city.label.isNotBlank() && city.latitude in -90.0..90.0 && city.longitude in -180.0..180.0)
            return city
        }
    }
}

internal data class HomeWeather(val temperature: Double, val code: Int, val time: Instant, val offset: Int)
internal data class WeatherState(val city: WeatherCity? = null, val weather: HomeWeather? = null,
    val matches: List<WeatherCity> = emptyList(), val busy: Boolean = false, val error: String = "")

internal fun weatherDescription(code: Int): String = when (code) {
    0 -> "晴"; 1 -> "大部晴朗"; 2 -> "多云"; 3 -> "阴"; 45, 48 -> "雾"
    51, 53, 55 -> "毛毛雨"; 56, 57, 66, 67 -> "冻雨"; 61, 63, 65 -> "雨"
    71, 73, 75, 77 -> "雪"; 80, 81, 82 -> "阵雨"; 85, 86 -> "阵雪"
    95 -> "雷雨"; 96, 99 -> "雷雨伴冰雹"; else -> "天气状态未知"
}

internal fun parseHomeWeather(json: JSONObject, now: Instant = Instant.now()): HomeWeather {
    val current = json.getJSONObject("current")
    require(json.getJSONObject("current_units").getString("temperature_2m") == "°C")
    val result = HomeWeather(current.getDouble("temperature_2m"), current.getInt("weather_code"),
        Instant.ofEpochSecond(current.getLong("time")), json.getInt("utc_offset_seconds"))
    require(result.temperature.isFinite() && result.time.isAfter(now.minusSeconds(10800)) &&
        !result.time.isAfter(now.plusSeconds(1800)))
    ZoneOffset.ofTotalSeconds(result.offset)
    return result
}

internal interface WeatherGateway {
    suspend fun search(name: String): List<WeatherCity>
    suspend fun forecast(city: WeatherCity): HomeWeather
}

internal class OpenMeteoWeather : WeatherGateway {
    private val client = OkHttpClient.Builder().callTimeout(15, TimeUnit.SECONDS).build()
    private suspend fun get(url: HttpUrl): JSONObject = suspendCancellableCoroutine { continuation ->
        val call = client.newCall(Request.Builder().url(url).build())
        continuation.invokeOnCancellation { call.cancel() }
        call.enqueue(object : Callback {
            override fun onFailure(call: Call, e: IOException) { continuation.resumeWithException(e) }
            override fun onResponse(call: Call, response: Response) {
                try {
                    val value = response.use { check(it.isSuccessful); JSONObject(it.body!!.string()) }
                    continuation.resume(value)
                } catch (error: Exception) { continuation.resumeWithException(error) }
            }
        })
    }
    override suspend fun search(name: String): List<WeatherCity> {
        val json = get("https://geocoding-api.open-meteo.com/v1/search".toHttpUrl().newBuilder()
            .addQueryParameter("name", name).addQueryParameter("language", "zh")
            .addQueryParameter("count", "5").build())
        val rows = json.optJSONArray("results") ?: return emptyList()
        return (0 until rows.length()).map { index ->
            val row = rows.getJSONObject(index)
            WeatherCity.parse(JSONObject().put("label", listOf(row.getString("name"), row.optString("admin1"),
                row.optString("country")).filter { it.isNotBlank() }.distinct().joinToString(" · "))
                .put("latitude", row.getDouble("latitude")).put("longitude", row.getDouble("longitude")).put("id", row.getInt("id")))
        }
    }
    override suspend fun forecast(city: WeatherCity): HomeWeather = parseHomeWeather(get(
        "https://api.open-meteo.com/v1/forecast".toHttpUrl().newBuilder()
            .addQueryParameter("latitude", city.latitude.toString()).addQueryParameter("longitude", city.longitude.toString())
            .addQueryParameter("current", "temperature_2m,weather_code").addQueryParameter("temperature_unit", "celsius")
            .addQueryParameter("timezone", "auto").addQueryParameter("timeformat", "unixtime")
            .addQueryParameter("forecast_days", "1").build()))
}

internal class HomeWeatherModel(private val gateway: WeatherGateway, private val scope: CoroutineScope,
    city: WeatherCity? = null) {
    private val current = MutableStateFlow(WeatherState(city = city))
    val state = current.asStateFlow()
    private var job: Job? = null
    private var generation = 0
    fun pause() {
        generation++; job?.cancel()
        current.value = current.value.copy(weather = null, matches = emptyList(), busy = false, error = "")
    }
    private fun action(work: suspend (Int) -> Unit) {
        job?.cancel(); val stamp = ++generation
        current.value = current.value.copy(busy = true, error = "")
        job = scope.launch {
            try { work(stamp) }
            catch (cancelled: CancellationException) { throw cancelled }
            catch (_: Exception) { if (stamp == generation) current.value = current.value.copy(weather = null,
                matches = emptyList(), error = "天气暂时不可用，请检查网络后重试。") }
            finally { if (stamp == generation) current.value = current.value.copy(busy = false) }
        }
    }
    fun search(name: String) {
        current.value = current.value.copy(matches = emptyList())
        action { stamp ->
            require(name.trim().length >= 2)
            val matches = gateway.search(name.trim())
            if (stamp == generation) current.value = current.value.copy(matches = matches,
                error = if (matches.isEmpty()) "未找到城市，请试试完整城市名或拼音。" else "")
        }
    }
    fun select(city: WeatherCity?) {
        pause(); current.value = WeatherState(city = city); refresh()
    }
    fun refresh() {
        val city = current.value.city ?: return
        current.value = current.value.copy(weather = null)
        action { stamp ->
            val weather = gateway.forecast(city)
            if (stamp == generation) current.value = current.value.copy(weather = weather)
        }
    }
}

@Composable
internal fun HomeWeatherCard(profile: String, scale: Float = 1f) {
    val context = LocalContext.current
    val prefs = remember(context) { context.getSharedPreferences("home-weather", Context.MODE_PRIVATE) }
    val scope = rememberCoroutineScope()
    val model = remember(profile) { HomeWeatherModel(OpenMeteoWeather(), scope,
        runCatching { WeatherCity.parse(JSONObject(prefs.getString(profile, null) ?: "")) }.getOrNull()) }
    val state by model.state.collectAsState()
    val lifecycle = LocalLifecycleOwner.current.lifecycle
    var foreground by remember(lifecycle) { mutableStateOf(lifecycle.currentState.isAtLeast(Lifecycle.State.STARTED)) }
    var editing by remember(profile) { mutableStateOf(false) }
    var query by remember(profile) { mutableStateOf("") }
    val links = LocalUriHandler.current
    DisposableEffect(lifecycle, model) {
        val observer = LifecycleEventObserver { _, event ->
            if (event == Lifecycle.Event.ON_START) foreground = true
            if (event == Lifecycle.Event.ON_STOP) { foreground = false; model.pause(); editing = false }
        }
        lifecycle.addObserver(observer)
        onDispose { lifecycle.removeObserver(observer); model.pause() }
    }
    LaunchedEffect(foreground, model, state.city, editing) {
        if (foreground && !editing) while (true) { model.refresh(); delay(900_000) }
    }
    HomeCard {
        Text(state.city?.let { "天气 · ${it.label}" } ?: "天气 · 请选择城市", fontSize = (18 * scale).sp)
        when {
            state.busy -> Text("正在获取天气…")
            state.error.isNotBlank() -> Text(state.error, color = MaterialTheme.colorScheme.error)
            state.weather != null -> {
                val weather = state.weather!!
                Text("${weather.temperature.roundToInt()}°C · ${weatherDescription(weather.code)}", fontSize = (24 * scale).sp)
                Text("数据时间：${weather.time.atOffset(ZoneOffset.ofTotalSeconds(weather.offset))
                    .format(DateTimeFormatter.ofPattern("M月d日 HH:mm XXX"))}")
            }
            else -> Text("手动选择关注城市后显示天气，不代表家人的实时位置。")
        }
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            TextButton(onClick = { editing = true }) { Text("选择城市") }
            TextButton(onClick = { model.refresh() }, enabled = state.city != null && !state.busy) { Text("刷新") }
            TextButton(onClick = { links.openUri("https://open-meteo.com/") }) { Text("来源：Open-Meteo") }
        }
    }
    if (editing) AlertDialog(onDismissRequest = { editing = false }, title = { Text("选择天气城市") }, text = {
        Column(Modifier.verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text("搜索词和所选城市坐标将发送给 Open-Meteo；不获取设备定位。城市选择仅保存在本机。")
            OutlinedTextField(query, { query = it.take(80) }, label = { Text("城市名或拼音") }, singleLine = true)
            Button(onClick = { model.search(query) }, enabled = query.trim().length >= 2 && !state.busy) { Text("搜索城市") }
            if (state.busy) Text("正在查询…")
            if (state.error.isNotBlank()) Text(state.error)
            state.matches.forEach { city ->
                TextButton(onClick = {
                    prefs.edit().putString(profile, city.json()).apply()
                    model.select(city); editing = false
                }) { Text(city.label) }
            }
        }
    }, confirmButton = { TextButton(onClick = { editing = false }) { Text("关闭") } },
        dismissButton = { TextButton(onClick = {
            prefs.edit().remove(profile).apply(); model.select(null); editing = false
        }) { Text("清除城市") } })
}
