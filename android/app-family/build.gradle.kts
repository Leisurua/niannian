plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("org.jetbrains.kotlin.plugin.compose")
}

android {
    namespace = "org.example.niannian.family"
    compileSdk = 35

    defaultConfig {
        applicationId = "org.example.niannian.family"
        minSdk = 26
        targetSdk = 35
        versionCode = 1
        versionName = "0.1.0"
    }

    flavorDimensions += "environment"
    productFlavors {
        listOf("dev" to "dev", "qa" to "test", "demo" to "demo").forEach { (flavor, environment) ->
            create(flavor) {
                dimension = "environment"
                applicationIdSuffix = ".$environment"
                versionNameSuffix = "-$environment"
                buildConfigField("String", "ENVIRONMENT", "\"$environment\"")
                buildConfigField("String", "PROVIDER_MODE", "\"mock\"")
            }
        }
    }

    buildFeatures {
        compose = true
        buildConfig = true
    }
}

dependencies {
    implementation(project(":core-common"))
    implementation(project(":core-telemetry"))
    implementation(platform("androidx.compose:compose-bom:2024.12.01"))
    implementation("androidx.activity:activity-compose:1.9.3")
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.material3:material3")
    implementation("androidx.compose.ui:ui-tooling-preview")
    debugImplementation("androidx.compose.ui:ui-tooling")
}
