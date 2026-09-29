package org.example.niannian.core.common

enum class AppEnvironment { DEV, TEST, DEMO }

enum class ProviderMode { MOCK, REAL }

data class RuntimeConfig(
    val environment: AppEnvironment,
    val providerMode: ProviderMode,
) {
    init {
        require(environment != AppEnvironment.DEMO || providerMode == ProviderMode.MOCK) {
            "Demo requires Mock provider"
        }
    }

    val statusLabel: String
        get() {
            val environmentLabel = when (environment) {
                AppEnvironment.DEV -> "开发环境"
                AppEnvironment.TEST -> "测试环境"
                AppEnvironment.DEMO -> "DEMO · 演示数据"
            }
            val providerLabel = when (providerMode) {
                ProviderMode.MOCK -> "演示能力（Mock）"
                ProviderMode.REAL -> "真实能力（Real）"
            }
            return "$environmentLabel · $providerLabel"
        }

    companion object {
        fun fromBuildValues(environment: String, providerMode: String): RuntimeConfig = RuntimeConfig(
            AppEnvironment.valueOf(environment.uppercase()),
            ProviderMode.valueOf(providerMode.uppercase()),
        )
    }
}
