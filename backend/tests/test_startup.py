import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from urllib.error import URLError
from urllib.request import urlopen

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("profile", ["dev", "test", "demo"])
def test_live_health_and_worker_startup(profile):
    environment = {**os.environ, "APP_ENV": profile, "PROVIDER_MODE": "mock",
                   "DEMO_DATA": "true" if profile == "demo" else "false",
                   "PYTHONPATH": str(ROOT / "backend"), "PYTHONUTF8": "1"}
    worker = subprocess.run([sys.executable, "-m", "app.worker.main"], cwd=ROOT,
                            env=environment, capture_output=True, text=True,
                            encoding="utf-8", timeout=15, check=True)
    records = [json.loads(line) for line in (worker.stdout + worker.stderr).splitlines() if line.strip()]
    assert any(record.get("event") == "WORKER_READY" for record in records)
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    process = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1",
                                "--port", str(port), "--no-access-log"], cwd=ROOT, env=environment,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            assert process.poll() is None, "API process exited before health check"
            try:
                with urlopen(f"http://127.0.0.1:{port}/health", timeout=1) as response:
                    payload = json.load(response)
                    assert response.status == 200
                    assert payload["status"] == "ok" and payload["environment"] == profile
                    assert payload["request_id"] == response.headers["X-Request-ID"]
                    return
            except (URLError, TimeoutError):
                time.sleep(.05)
        pytest.fail("HTTP health endpoint did not become ready within 15 seconds")
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
