import os
from pathlib import Path
import secrets
import subprocess
import sys
import time
from urllib.error import URLError
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "niannian"
BACKEND = SOURCE / "backend"
DATA = ROOT / "data"
PG = ROOT / "runtime" / "pgsql" / "bin"
MINIO = ROOT / "runtime" / "minio.exe"
LOG = ROOT / "logs"
DB_PORT, API_PORT, S3_PORT, CONSOLE_PORT = 15432, 18000, 19000, 19001
CHILDREN = []

os.environ.update(APP_ENV="test", PYTHONUTF8="1", LLM_PROVIDER="mock", EMBEDDING_PROVIDER="mock",
                  NOTIFICATION_EXTERNAL_ENABLED="false", AVATAR_GENERATION_ENABLED="false",
                  FAMILY_VOICE_ENABLED="false")
sys.path[:0] = [str(BACKEND), str(ROOT / "runtime" / "site")]
os.environ["PYTHONPATH"] = os.pathsep.join(sys.path[:2])

from botocore.exceptions import ClientError
from app.platform.config import get_settings
from app.platform.storage import S3Storage
from sqlalchemy.engine import make_url


def run(name, args, *, env=None):
    with (LOG / f"{name}.log").open("ab") as output:
        subprocess.run(args, cwd=BACKEND, env=env, stdout=output, stderr=output,
                       check=True, timeout=120, creationflags=subprocess.CREATE_NO_WINDOW)


def start(name, args, *, env=None):
    with (LOG / f"{name}.log").open("ab") as output:
        child = subprocess.Popen(args, cwd=BACKEND, env=env, stdin=subprocess.DEVNULL,
                                 stdout=output, stderr=output, creationflags=subprocess.CREATE_NO_WINDOW)
    CHILDREN.append(child)
    return child


def wait_http(url):
    for _ in range(35):
        if any(child.poll() is not None for child in CHILDREN):
            raise RuntimeError("A process exited; see the service logs")
        try:
            with urlopen(url, timeout=2) as result:
                if result.status == 200:
                    return
        except (URLError, TimeoutError):
            time.sleep(1)
    raise RuntimeError(f"Service readiness timed out for {url}")


def private_settings():
    env_file = SOURCE / ".env"
    if not env_file.exists():
        if (DATA / "postgres" / "PG_VERSION").exists():
            raise RuntimeError("Existing database needs its original configuration")
        password = secrets.token_hex(24)
        content = (
            "AUTH_MODE=password\nPROVIDER_MODE=mock\nDEMO_DATA=false\n"
            f"DATABASE_URL=postgresql+psycopg://niannian:{password}@127.0.0.1:{DB_PORT}/niannian\n"
            f"AUTH_SIGNING_KEY={secrets.token_hex(32)}\n"
            f"PUBLIC_BASE_URL=http://127.0.0.1:{API_PORT}\n"
            f"S3_ENDPOINT=http://127.0.0.1:{S3_PORT}\n"
            f"S3_ACCESS_KEY={secrets.token_hex(10)}\nS3_SECRET_KEY={secrets.token_hex(24)}\n"
        )
        with env_file.open("x", encoding="ascii") as handle:
            handle.write(content)
    return get_settings()


def main():
    LOG.mkdir(exist_ok=True)
    DATA.mkdir(exist_ok=True)
    pg_data = DATA / "postgres"
    settings = private_settings()
    database = make_url(settings.database_url)
    if database.host != "127.0.0.1" or database.port != DB_PORT or database.database != "niannian":
        raise RuntimeError("Unexpected PostgreSQL settings")
    if not (pg_data / "PG_VERSION").exists():
        password_file = DATA / "pg-init.tmp"
        try:
            password_file.write_text(database.password + "\n", encoding="ascii")
            run("initdb", [PG / "initdb.exe", "-D", pg_data, "-U", database.username, "--encoding=UTF8",
                           "--locale=C", "--auth=scram-sha-256", f"--pwfile={password_file}"])
        finally:
            password_file.unlink(missing_ok=True)
    postgres = start("postgres", [PG / "postgres.exe", "-D", pg_data, "-h", "127.0.0.1", "-p", str(DB_PORT),
                                 "-c", "shared_buffers=32MB", "-c", "max_connections=30"])
    try:
        for _ in range(40):
            ready = subprocess.run([PG / "pg_isready.exe", "-h", "127.0.0.1", "-p", str(DB_PORT),
                                    "-U", database.username, "-d", "postgres"], capture_output=True,
                                   creationflags=subprocess.CREATE_NO_WINDOW, timeout=5)
            if ready.returncode == 0:
                break
            if postgres.poll() is not None:
                raise RuntimeError("PostgreSQL exited; check postgres.log")
            time.sleep(1)
        else:
            raise RuntimeError("PostgreSQL readiness timed out")
        pg_env = {**os.environ, "PGPASSWORD": database.password}
        result = subprocess.check_output([PG / "psql.exe", "-h", "127.0.0.1", "-p", str(DB_PORT),
                                          "-U", database.username, "-d", "postgres", "-At",
                                          "-c", "SELECT 1 FROM pg_database WHERE datname = 'niannian'"],
                                         env=pg_env, creationflags=subprocess.CREATE_NO_WINDOW, timeout=10)
        if result.strip() != b"1":
            run("createdb", [PG / "createdb.exe", "-h", "127.0.0.1", "-p", str(DB_PORT),
                             "-U", database.username, "niannian"], env=pg_env)
        run("migration", [sys.executable, "-m", "alembic", "upgrade", "head"])
        start("minio", [MINIO, "server", DATA / "objects", "--address", f"127.0.0.1:{S3_PORT}",
                        "--console-address", f"127.0.0.1:{CONSOLE_PORT}", "--quiet"],
              env={**os.environ, "MINIO_ROOT_USER": settings.s3_access_key,
                   "MINIO_ROOT_PASSWORD": settings.s3_secret_key, "GOMEMLIMIT": "160MiB"})
        wait_http(f"http://127.0.0.1:{S3_PORT}/minio/health/ready")
        storage = S3Storage(settings)
        try:
            storage.client.head_bucket(Bucket=settings.s3_bucket)
        except ClientError as exc:
            if exc.response["Error"]["Code"] not in {"404", "NoSuchBucket", "NotFound"}:
                raise
            storage.client.create_bucket(Bucket=settings.s3_bucket)
        start("api", [sys.executable, "-m", "app", "--host", "127.0.0.1", "--port", str(API_PORT)])
        start("worker", [sys.executable, "-m", "app.worker.main", "--serve"])
        wait_http(f"http://127.0.0.1:{API_PORT}/health/ready")
        print("Private test backend is ready", flush=True)
        while not any(child.poll() is not None for child in CHILDREN):
            time.sleep(2)
        raise RuntimeError("A backend process exited; see the individual service logs")
    finally:
        for child in reversed(CHILDREN[1:]):
            if child.poll() is None:
                child.terminate()
        if postgres.poll() is None:
            run("pg-stop", [PG / "pg_ctl.exe", "-D", pg_data, "-m", "fast", "-w", "stop"])


if __name__ == "__main__":
    main()
