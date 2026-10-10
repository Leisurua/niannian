# Android auth / family / consent slice

Two native Kotlin + Jetpack Compose applications are included:

- `app-elder` — DEMO login, invitation identity confirmation and subject-owned Consent
- `app-family` — DEMO login, family creation, invitation and membership management, Consent history
- `feature-auth` — shared Compose screens, ViewModel, REST repository and Keystore-backed session storage
- `core-common` — shared stable primitives only
- `core-telemetry` — shared redacted event logging

Each app has `dev`, `qa`, and `demo` Gradle flavors with separate application IDs. `qa` supplies the `test` runtime environment because Android Gradle Plugin reserves flavor names beginning with `test`. `RuntimeConfig` keeps the environment and Mock label visible. These screens call the FastAPI backend; authorization remains server-enforced.

Debug HTTP is allowed only for emulator/loopback addresses; release requires HTTPS. No hardware permissions are requested. Access/refresh tokens and unresolved idempotent writes are encrypted with a Keystore AES-GCM key, excluded from backup, and cleared on logout or revoked authentication. Offline information is marked stale and new mutations require reconciliation. On a timeout the user can explicitly retry the same request with its original key. Invitation confirmation is bound to the selected family.

Start the backend with `python -m app` from `backend/`, then use `http://10.0.2.2:8000` in an emulator debug build. For a physical device use a trusted HTTPS endpoint, or an explicitly configured loopback forwarding setup. No real device acceptance is implied by a successful Gradle build.

Run `gradlew.bat clean build` with JDK 17 and Android SDK 35. Gradle dependency versions are recorded in each module's `gradle.lockfile`.

On Windows use an ASCII-only checkout path for Android tooling. The Week 2 record documents source hash comparison for the local build copy and the separate UI/Keystore/device gates.
