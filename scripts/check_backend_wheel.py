import os
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile


def main() -> None:
    wheels = list(Path(sys.argv[1]).resolve().glob("nian_nian_backend-*.whl"))
    if len(wheels) != 1:
        raise RuntimeError("Expected one backend wheel")
    with zipfile.ZipFile(wheels[0]) as wheel:
        members = set(wheel.namelist())
        assert all(f"config/{profile}.env" in members for profile in ("dev", "test", "demo"))
        assert not any(name.startswith(("tests/", "alembic/")) for name in members)
    with tempfile.TemporaryDirectory(prefix="niannian-wheel-") as temporary:
        subprocess.run([sys.executable, "-m", "pip", "install", "--no-deps", "--no-compile",
                        "--disable-pip-version-check", "--target", temporary, str(wheels[0])], check=True)
        for profile in ("dev", "test", "demo"):
            environment = {**os.environ, "PYTHONPATH": temporary, "APP_ENV": profile,
                           "PROVIDER_MODE": "mock", "PYTHONUTF8": "1"}
            environment.pop("DEMO_DATA", None)
            subprocess.run([sys.executable, "-c", "\n".join([
                "from pathlib import Path",
                "import app",
                "from app.main import app as api, settings",
                "from fastapi.testclient import TestClient",
                "assert Path(app.__file__).is_relative_to(Path.cwd())",
                "assert settings.provider_mode == 'mock'",
                "assert settings.demo_data == (settings.app_env == 'demo')",
                "response = TestClient(api).get('/health')",
                "assert response.status_code == 200",
                "assert response.json()['environment'] == settings.app_env",
            ])], cwd=temporary, env=environment, check=True, timeout=15)
    print("PASS: installed wheel supplies all three profiles and health; no source import")


if __name__ == "__main__":
    main()
