package org.example.niannian.feature.family

import kotlinx.coroutines.*
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import java.time.Instant

class HomeWeatherTest {
    private val now = Instant.parse("2026-10-23T06:00:00Z")
    private val first = WeatherCity("测试城市一", 30.0, 120.0)
    private val second = WeatherCity("测试城市二", 40.0, 116.0)
    private val weather = HomeWeather(16.5, 3, now, 28800)
    private fun payload(time: Instant = now) = JSONObject().put("utc_offset_seconds", 28800)
        .put("current_units", JSONObject().put("temperature_2m", "°C"))
        .put("current", JSONObject().put("temperature_2m", 16.5).put("weather_code", 3).put("time", time.epochSecond))

    @Test fun forecastUsesServerTimeAndRejectsMissingOrStaleData() {
        assertEquals(weather, parseHomeWeather(payload(), now))
        assertEquals("阴", weatherDescription(weather.code))
        assertEquals("天气状态未知", weatherDescription(1000))
        for (invalid in listOf(payload(now.minusSeconds(10801)), payload(now.plusSeconds(1801)),
            payload().apply { getJSONObject("current").put("temperature_2m", JSONObject.NULL) },
            payload().apply { getJSONObject("current_units").put("temperature_2m", "°F") })) {
            assertTrue(runCatching { parseHomeWeather(invalid, now) }.isFailure)
        }
    }

    @Test fun cityPreferenceRoundTripsWithoutInventingLocation() {
        assertEquals(first, WeatherCity.parse(JSONObject(first.json())))
        assertTrue(runCatching { WeatherCity.parse(JSONObject(first.json()).put("latitude", 100)) }.isFailure)
    }

    @Test fun noDefaultCityAndFailureNeverFallsBackToSampleWeather() = runBlocking {
        var calls = 0
        var fail = false
        val gateway = object : WeatherGateway {
            override suspend fun search(name: String) = emptyList<WeatherCity>()
            override suspend fun forecast(city: WeatherCity): HomeWeather {
                calls++; if (fail) error("offline"); return weather
            }
        }
        val model = HomeWeatherModel(gateway, this)
        model.refresh(); yield(); assertEquals(0, calls)
        model.select(first); yield(); assertEquals(weather, model.state.value.weather)
        fail = true; model.refresh(); yield()
        assertNull(model.state.value.weather); assertTrue(model.state.value.error.isNotBlank())
        fail = false; model.refresh(); yield()
        assertEquals(weather, model.state.value.weather); assertEquals("", model.state.value.error)
        model.search("不存在的城市"); yield()
        assertTrue(model.state.value.matches.isEmpty()); assertTrue(model.state.value.error.contains("未找到"))
        model.select(null); yield(); assertNull(model.state.value.city); assertNull(model.state.value.weather)
    }

    @Test fun switchingCityAndStoppingDiscardEvenNonCancellableLateResults() = runBlocking {
        val delayed = CompletableDeferred<Unit>()
        val gateway = object : WeatherGateway {
            override suspend fun search(name: String) = listOf(first)
            override suspend fun forecast(city: WeatherCity): HomeWeather {
                if (city == first) withContext(NonCancellable) { delayed.await() }
                return weather.copy(temperature = if (city == first) 10.0 else 20.0)
            }
        }
        val model = HomeWeatherModel(gateway, this)
        model.select(first); yield()
        model.select(second); yield()
        delayed.complete(Unit); yield(); yield()
        assertEquals(second, model.state.value.city)
        assertEquals(20.0, model.state.value.weather!!.temperature, 0.01)
        model.pause(); assertNull(model.state.value.weather)
    }
}
