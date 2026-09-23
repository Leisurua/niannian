plugins {
    id("com.android.application") version "8.7.3" apply false
    id("com.android.library") version "8.7.3" apply false
    id("org.jetbrains.kotlin.android") version "2.0.21" apply false
    id("org.jetbrains.kotlin.plugin.compose") version "2.0.21" apply false
}

// Allows constrained CI/sandbox environments to redirect generated outputs.
val externalBuildRoot = providers.environmentVariable("NIANNIAN_BUILD_ROOT")
allprojects {
    dependencyLocking {
        lockAllConfigurations()
    }
    if (externalBuildRoot.isPresent) {
        layout.buildDirectory.set(file("${externalBuildRoot.get()}/${project.name}"))
    }
}

subprojects {
    plugins.withId("org.jetbrains.kotlin.android") {
        extensions.configure<org.jetbrains.kotlin.gradle.dsl.KotlinAndroidProjectExtension> {
            jvmToolchain(17)
        }
    }
}
