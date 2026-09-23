plugins {
    id("com.android.library")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "org.example.niannian.core.common"
    compileSdk = 35

    defaultConfig { minSdk = 26 }
}

dependencies {
    testImplementation("junit:junit:4.13.2")
}
