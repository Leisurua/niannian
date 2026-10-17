# Week 5 reminders

Both apps use this Compose feature. The Elder app keeps an encrypted, owner/family/version/expiry-scoped
Room snapshot containing reminder rules, occurrences and pending feedback in one transaction. The Family
app reads online and hides content on connection or authorization failure. Notification scheduling and
boot/time-change receivers live only in app-elder; app-family has no notification or boot permissions.

The calendar follows the accepted W3 policy: Monday = 0; weekly intervals anchored to the start-date
week; first instant in a DST overlap; skip nonexistent local times; equal quiet-hour endpoints disabled.
The rule's IANA zone determines scheduling, independent of the phone zone. Quiet hours annotate an
occurrence without changing its UTC hash. The 16 static calendar vectors are checked in Python and Kotlin.

W5-03 limits reminder cache freshness to 24 hours (shortened by known rule expiry) and pending feedback
to 24 hours from the user's action. Room stores AES-GCM ciphertext backed by Android Keystore, excluded
from backups. Cache/queue erasure runs on expiry checks, known access loss, family switch and logout;
key erasure and generation checks prevent an in-flight old save from restoring content. Clock rollback
fails closed. A fully offline device learns remote revocation at reconnect or expiry, as approved.

Pending requests retain their UUID idempotency key, canonical payload hash, retry count and backoff.
They are removed after a validated matching ACK, explicit conflict reconciliation, invalidation or expiry.
A snooze followed by DONE/SKIPPED offline keeps two ordered actions; the second never changes the first
request's key/body. At most five automatic attempts are made. Family/source/version is rechecked after
validated reconnection; stale rules and elapsed snooze times are not silently rewritten. NO_RESPONSE is
server-only and displayed as “尚未收到反馈”. No medication inference or automatic dose edit exists.

The Elder receiver uses inexact AlarmManager scheduling and minimal notifications without health text.
It records notification submission, never delivery. Android/OEM restrictions, force-stop and permission
denial can delay/prevent background checks; the page shows the limitation. Eligible cache can be opened
after an offline process restart using the previously authenticated account binding. Synchronization
retries run while the reminder page is active (every minute); background notifications do not log in or
upload actions. Physical expiry cleanup resumes on the next allowed wake/start if Android suspends the app.
No real speech playback is implemented by this feature.

Room runtime/compiler are pinned to 2.6.1, using Java annotation processing with a checked-in version-1
schema. See [Room documentation](https://developer.android.com/training/data-storage/room).
No dependency on a new server, push provider or real AI service was introduced.

From an ASCII-path Android checkout with JDK 17 and SDK 35:

```powershell
./gradlew.bat --offline --no-daemon :feature-reminder:test :feature-auth:test build
```

From the repository root with locked Python dependencies:

```powershell
$env:PYTHONPATH = 'backend'
$env:PYTHONUTF8 = '1'
.venv/Scripts/python.exe -m pytest backend/tests/unit/test_week3_schedule.py backend/tests/unit/test_week5_calendar_parity.py -q -p no:cacheprovider
```

The ledger/ViewModel tests use an injected store and clock. They do not verify Android Keystore, actual
Room I/O, notification permission dialogs, reboot, Doze or OEM delivery. Those require the named-device gate.
See docs/evidence/week5.md for the actual scope and results.
