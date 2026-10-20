package org.example.niannian.core.telemetry

import java.util.concurrent.atomic.AtomicReference
import org.junit.After
import org.junit.Assert.*
import org.junit.Test

class AppExecutionBoundaryTest {
    private val originalName = Thread.currentThread().name
    private val events = mutableListOf<String>()
    private val boundary = AppExecutionBoundary(TelemetryLogger { events.add(it) })
    private val canaries = listOf(
        "Bearer " + "synthetic".repeat(4), "sk-" + "S".repeat(24),
        "SYNTHETIC_AUDIO_PAYLOAD", "synthetic transcript", "1" + "3".repeat(10),
        "synthetic health", "synthetic memory", "https://example.invalid/?signature=synthetic",
    )

    @After fun restoreName() { Thread.currentThread().name = originalName }

    private fun failure(work: Runnable): Throwable {
        try {
            boundary.run(work)
        } catch (caught: Throwable) {
            return caught
        }
        throw AssertionError("Fatal callback returned")
    }

    private fun assertContentFree(caught: Throwable) {
        assertTrue(caught is Error)
        assertEquals("APP_EXECUTION_FAILED", caught.message)
        assertNull(caught.cause)
        assertTrue(caught.suppressed.isEmpty())
        assertTrue(caught.stackTrace.isEmpty())
        val diagnostics = caught.stackTraceToString() + events.joinToString() + Thread.currentThread().name
        canaries.forEach { assertFalse(diagnostics.contains(it)) }
    }

    @Test fun successfulWorkRunsOnceWithoutChangingThreadOrLogging() {
        var calls = 0
        boundary.run { calls++ }
        assertEquals(1, calls)
        assertEquals(originalName, Thread.currentThread().name)
        assertTrue(events.isEmpty())
    }

    @Test fun discardsAllSensitiveCategoriesCausesSuppressedAndThreadNames() {
        val original = RuntimeException(canaries.joinToString(), IllegalStateException(canaries.joinToString()))
        original.addSuppressed(IllegalArgumentException(canaries.joinToString()))
        Thread.currentThread().name = canaries.joinToString()
        val caught = failure { throw original }
        assertContentFree(caught)
        assertEquals("NianNian-fatal", Thread.currentThread().name)
        assertEquals(listOf("{\"event\":\"APP_EXECUTION_FAILED\",\"result\":\"FAILED\",\"error_code\":\"UNEXPECTED_FAILURE\"}"), events)
    }

    @Test fun neverCallsHostileThrowableFormattingOrAccessors() {
        val hostile = object : Error() {
            override val message: String get() = throw AssertionError("message accessed")
            override val cause: Throwable get() = throw AssertionError("cause accessed")
            override fun toString(): String = throw AssertionError("formatted")
        }
        assertContentFree(failure { throw hostile })
    }

    @Test fun failedSinkCannotLeakOrResumeWork() {
        val badSink = AppExecutionBoundary(TelemetryLogger { throw Error(canaries.joinToString()) })
        var resumed = false
        val caught = failure {
            badSink.run { throw RuntimeException(canaries.joinToString()) }
            resumed = true
        }
        assertFalse(resumed)
        assertContentFree(caught)
    }

    @Test fun fatalVmErrorsAreAlsoContentFree() {
        assertContentFree(failure { throw OutOfMemoryError(canaries.joinToString()) })
    }

    @Test fun failedThreadPreparationTerminatesWithoutLoggingOrContinuing() {
        val stopped = object : Error("TEST_TERMINATION") { }
        val guarded = AppExecutionBoundary(
            TelemetryLogger { events.add(it) },
            { throw SecurityException(canaries.joinToString()) },
            { throw stopped },
        )
        var resumed = false
        try {
            guarded.run { throw RuntimeException(canaries.joinToString()) }
            resumed = true
        } catch (caught: Throwable) {
            assertSame(stopped, caught)
        }
        assertFalse(resumed)
        assertTrue(events.isEmpty())
    }

    @Test fun failureCannotAccumulateSensitiveDiagnosticsAcrossCalls() {
        val caught = failure { throw RuntimeException(canaries.joinToString()) }
        caught.addSuppressed(RuntimeException(canaries.joinToString()))
        caught.stackTrace = arrayOf(StackTraceElement(canaries[0], canaries[1], canaries[2], 1))
        try {
            caught.initCause(RuntimeException(canaries.joinToString()))
            fail("Cause must remain immutable")
        } catch (_: IllegalStateException) { }
        assertContentFree(caught)
        assertContentFree(failure { throw RuntimeException("another synthetic failure") })
    }

    @Test fun actualWorkerDeliversOnlyContentFreeFailureAndDoesNotResume() {
        val escaped = AtomicReference<Throwable>()
        val escapedName = AtomicReference<String>()
        var resumed = false
        val worker = Thread({
            boundary.run { throw RuntimeException(canaries.joinToString()) }
            resumed = true
        }, canaries.joinToString())
        worker.uncaughtExceptionHandler = Thread.UncaughtExceptionHandler { thread, caught ->
            escaped.set(caught)
            escapedName.set(thread.name)
        }
        worker.start()
        worker.join(5000)
        assertFalse(worker.isAlive)
        assertFalse(resumed)
        assertEquals("NianNian-fatal", escapedName.get())
        assertContentFree(escaped.get())
    }
}
