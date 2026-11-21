import java.net.URI

plugins {
    id("com.android.library")
    id("org.jetbrains.kotlin.android")
    id("org.jetbrains.kotlin.plugin.compose")
}

val apiOrigin = providers.gradleProperty("niannianApiOrigin").orElse("").get().trim().trimEnd('/')
if (apiOrigin.isNotEmpty()) {
    val uri = URI(apiOrigin)
    require(uri.scheme == "https" && uri.host != null && uri.rawUserInfo == null && uri.rawPath.isEmpty()
        && uri.rawQuery == null && uri.rawFragment == null && (uri.port == -1 || uri.port in 1..65535)) {
        "niannianApiOrigin must be a HTTPS origin without a path or credentials"
    }
}

android {
    namespace = "org.example.niannian.shared"
    compileSdk = 35
    defaultConfig {
        minSdk = 26
        buildConfigField("String", "API_ORIGIN", "\"$apiOrigin\"")
        javaCompileOptions { annotationProcessorOptions { arguments["room.schemaLocation"] = "$projectDir/schemas" } }
    }
    buildFeatures {
        compose = true
        buildConfig = true
    }
}

dependencies {
    implementation(platform("androidx.compose:compose-bom:2024.12.01"))
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.material3:material3")
    implementation("androidx.activity:activity-compose:1.9.3")
    implementation("androidx.lifecycle:lifecycle-viewmodel-ktx:2.8.3")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.7.3")
    implementation("com.squareup.okhttp3:okhttp:4.12.0")
    implementation("androidx.room:room-runtime:2.6.1")
    annotationProcessor("androidx.room:room-compiler:2.6.1")
    testImplementation("junit:junit:4.13.2")
    testImplementation("org.json:json:20240303")
}
