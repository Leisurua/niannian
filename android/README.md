# Android skeleton

Two native Kotlin + Jetpack Compose applications are included:

- `app-elder` — future elder/device-facing application
- `app-family` — future family-facing application
- `core-common` — shared stable primitives only
- `core-telemetry` — shared redacted event logging

Each app has `dev`, `qa`, and `demo` Gradle flavors with separate application IDs. `qa` supplies the `test` runtime environment because Android Gradle Plugin reserves flavor names beginning with `test`. The shared `RuntimeConfig` gives the environment and provider source a visible status label. All current flavors use `Mock`; the demo label identifies fictional data and demo capability. This is configuration only: demo seed data and provider implementations belong to later tasks.

No networking, navigation, Room schema, hardware permissions or business UI is included yet.

Run `gradlew.bat clean build` with JDK 17 and Android SDK 35. Gradle dependency versions are recorded in each module's `gradle.lockfile`.
