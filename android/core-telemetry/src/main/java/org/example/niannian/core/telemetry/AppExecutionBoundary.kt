package org.example.niannian.core.telemetry

import android.os.Process
import kotlin.system.exitProcess

/**
 * Fatal boundary for synchronous app-owned root callbacks and worker bodies.
 * Wrap the work when it executes, not when a callback is merely registered.
 * This does not intercept unrelated framework, native, or unmanaged-thread failures.
 */
class AppExecutionBoundary internal constructor(
    private val logger: TelemetryLogger,
    private val prepareThread: () -> Unit,
    private val terminateProcess: () -> Nothing,
) {
    @JvmOverloads
    constructor(logger: TelemetryLogger = TelemetryLogger()) : this(
        logger,
        { Thread.currentThread().name = "NianNian-fatal" },
        { Process.killProcess(Process.myPid()); exitProcess(10) },
    )

    private val fatalFailure = ContentFreeFailure

    fun run(work: Runnable) {
        try {
            work.run()
        } catch (_: Throwable) {
            // Never inspect/format/attach the original Throwable, even for diagnostics.
            // Android's pre-handler prints thread names before the default handler runs.
            try {
                prepareThread()
            } catch (_: Throwable) {
                // If even naming fails, do not forward a sensitive thread name to
                // AndroidRuntime. Terminate directly without reporting the Throwable.
                terminateProcess()
            }
            try {
                logger.info("APP_EXECUTION_FAILED", mapOf("result" to "FAILED", "error_code" to "UNEXPECTED_FAILURE"))
            } catch (_: Throwable) {
                // A broken log sink must not expose its own exception or resume work.
            }
            throw fatalFailure
        }
    }

    // Preallocated, immutable diagnostics: no cause, suppression or captured stack.
    // Error (rather than Exception) prevents ordinary recoverable-error handlers from
    // accidentally resuming a callback after an unexpected fatal failure.
    private object ContentFreeFailure : Error("APP_EXECUTION_FAILED", null, false, false)
}
