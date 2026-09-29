"""E0-T03 / PRIV-008 source and fixture scan, runnable without app dependencies."""

import os
import re
import subprocess
import unittest
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PATTERNS = (
    re.compile(r"-----BEGIN " + r"(?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"AKIA[A-Z0-9]{16}"),
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
    re.compile(r"Bearer [A-Za-z0-9._-]{20,}"),
    re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)"),
)
FORBIDDEN_ARTIFACTS = {".log", ".wav", ".mp3", ".pcm", ".apk", ".aab"}
GENERATED_PARTS = {"build", ".gradle", ".gradle-home", ".venv", ".git", "__pycache__", "META-INF"}
TEXT_SUFFIXES = {".py", ".kt", ".kts", ".xml", ".env", ".example", ".md", ".toml", ".properties", ".yaml", ".yml", ".txt", ".sql", ".lock", ".lockfile", ".json", ".jsonl", ".csv", ".tsv"}
FIXTURE_SUFFIXES = {".json", ".jsonl", ".yaml", ".yml"}
TRANSCRIPT_FIELD = re.compile(r'["\'](?:transcript|raw_audio|audio_base64|conversation_text)["\']\s*:\s*["\'][^"\']+', re.IGNORECASE)


def is_fixture(path: Path) -> bool:
    return any(part.lower() in {"fixtures", "fixture", "seed", "seeds"} for part in path.parts)


def scan_bytes(content: bytes, patterns: tuple[re.Pattern[bytes], ...]) -> bool:
    return any(pattern.search(content) for pattern in patterns)


def repository_files():
    for current, directories, files in os.walk(ROOT):
        directories[:] = [name for name in directories if name not in GENERATED_PARTS]
        for name in files:
            yield Path(current) / name


class ArtifactScanTest(unittest.TestCase):
    def test_no_secret_or_full_phone_patterns_in_sources_and_fixtures(self) -> None:
        for path in repository_files():
            if path.suffix not in TEXT_SUFFIXES:
                continue
            content = path.read_text(encoding="utf-8")
            for pattern in PATTERNS:
                self.assertIsNone(pattern.search(content), f"Sensitive pattern in {path.relative_to(ROOT)}")

    def test_no_transcript_or_raw_audio_content_in_fixtures(self) -> None:
        for path in repository_files():
            if path.suffix.lower() not in FIXTURE_SUFFIXES or not is_fixture(path):
                continue
            content = path.read_text(encoding="utf-8")
            self.assertIsNone(TRANSCRIPT_FIELD.search(content), f"Sensitive content field in {path.relative_to(ROOT)}")

    def test_no_sensitive_artifacts_in_source_trees(self) -> None:
        for path in repository_files():
            self.assertNotIn(path.suffix.lower(), FORBIDDEN_ARTIFACTS, str(path.relative_to(ROOT)))

    def test_git_history_contains_no_secret_patterns(self) -> None:
        if not (ROOT / ".git").exists():
            self.skipTest("Git history unavailable")
        git = ["git", "-c", f"safe.directory={ROOT.as_posix()}"]
        listing = subprocess.run(
            [*git, "rev-list", "--objects", "--all"],
            cwd=ROOT, check=True, capture_output=True,
        ).stdout
        object_ids = [line.split(b" ", 1)[0] for line in listing.splitlines()]
        self.assertTrue(object_ids, "Git history has no objects to scan")
        batch = subprocess.run(
            [*git, "cat-file", "--batch"],
            cwd=ROOT, check=True, input=b"\n".join(object_ids) + b"\n", capture_output=True,
        ).stdout
        secret_patterns = tuple(re.compile(pattern.pattern.encode("ascii")) for pattern in PATTERNS)
        offset = 0
        scanned_blobs = 0
        for object_id in object_ids:
            header_end = batch.index(b"\n", offset)
            resolved_id, object_type, size_text = batch[offset:header_end].split()
            self.assertEqual(resolved_id, object_id)
            size = int(size_text)
            content_start = header_end + 1
            content_end = content_start + size
            if object_type == b"blob":
                self.assertFalse(
                    scan_bytes(batch[content_start:content_end], secret_patterns),
                    f"Sensitive pattern in Git blob {object_id.decode('ascii')}",
                )
                scanned_blobs += 1
            offset = content_end + 1
        self.assertGreater(scanned_blobs, 0)
        self.assertEqual(offset, len(batch))

    def test_built_apks_contain_no_secret_patterns(self) -> None:
        apks = [
            apk
            for app in ("app-elder", "app-family")
            for apk in (ROOT / "android" / app / "build" / "outputs" / "apk").rglob("*.apk")
        ]
        if not apks:
            self.skipTest("No APKs built yet")
        secret_patterns = tuple(re.compile(pattern.pattern.encode("ascii")) for pattern in PATTERNS)
        for apk in apks:
            with zipfile.ZipFile(apk) as package:
                for member in package.namelist():
                    content = package.read(member)
                    self.assertFalse(scan_bytes(content, secret_patterns), f"Sensitive pattern in {apk.name}:{member}")

    def test_apk_scan_includes_full_phone_pattern(self) -> None:
        patterns = tuple(re.compile(pattern.pattern.encode("ascii")) for pattern in PATTERNS)
        self.assertTrue(scan_bytes(b"phone=138" + b"12345678", patterns))

    def test_fixture_scan_detects_transcript_content(self) -> None:
        field = '"transcript"' + ': "private content"'
        self.assertIsNotNone(TRANSCRIPT_FIELD.search(field))
        self.assertIsNone(TRANSCRIPT_FIELD.search('"transcript"' + ': ""'))


if __name__ == "__main__":
    unittest.main()
