"""Bounded, streaming file preflight. This is NOT a malware/image decoder.

The storage service must separately authorize, decode, strip metadata and scan
the object before it can become AVAILABLE. No storage URL or state is produced.
"""

from collections.abc import Iterable
from dataclasses import dataclass
import hashlib
import hmac
import re

ALLOWED_PHOTO_TYPES = frozenset({'image/jpeg', 'image/png', 'image/webp'})


class FilePreflightError(ValueError):
    """Safe error code only; filenames, object keys and content are never echoed."""


@dataclass(frozen=True)
class UploadDeclaration:
    media_type: str
    mime_type: str
    size_bytes: int
    checksum: str

    def validate(self, *, max_size_bytes: int) -> None:
        if type(max_size_bytes) is not int or max_size_bytes < 1:
            raise ValueError('A positive deployment file limit is required')
        if self.media_type != 'PHOTO' or self.mime_type not in ALLOWED_PHOTO_TYPES:
            raise FilePreflightError('FILE_TYPE_NOT_ALLOWED')
        if type(self.size_bytes) is not int or not 1 <= self.size_bytes <= max_size_bytes:
            raise FilePreflightError('FILE_SIZE_INVALID')
        if not isinstance(self.checksum, str) or not re.fullmatch(r'[a-fA-F0-9]{64}', self.checksum):
            raise FilePreflightError('FILE_CHECKSUM_INVALID')
        if self.checksum == '0' * 64:
            raise FilePreflightError('FILE_CHECKSUM_INVALID')


@dataclass(frozen=True)
class PreflightReceipt:
    size_bytes: int
    # Deliberately no availability flag: matching bytes are not a safe image.
    needs_content_inspection: bool = True


def verify_upload_bytes(
    declaration: UploadDeclaration, chunks: Iterable[bytes], *, max_size_bytes: int,
) -> PreflightReceipt:
    declaration.validate(max_size_bytes=max_size_bytes)
    digest = hashlib.sha256()
    prefix = bytearray()
    total = 0
    for chunk in chunks:
        if not isinstance(chunk, bytes):
            raise FilePreflightError('FILE_STREAM_INVALID')
        total += len(chunk)
        if total > declaration.size_bytes or total > max_size_bytes:
            raise FilePreflightError('FILE_SIZE_INVALID')
        digest.update(chunk)
        prefix.extend(chunk[:max(0, 12 - len(prefix))])
    if total != declaration.size_bytes:
        raise FilePreflightError('FILE_SIZE_INVALID')
    if not hmac.compare_digest(digest.hexdigest(), declaration.checksum.lower()):
        raise FilePreflightError('FILE_CHECKSUM_MISMATCH')
    detected = None
    if prefix.startswith(b'\x89PNG\r\n\x1a\n'):
        detected = 'image/png'
    elif prefix.startswith(b'\xff\xd8\xff'):
        detected = 'image/jpeg'
    elif prefix[:4] == b'RIFF' and prefix[8:12] == b'WEBP':
        detected = 'image/webp'
    if detected != declaration.mime_type:
        raise FilePreflightError('FILE_CONTENT_TYPE_MISMATCH')
    return PreflightReceipt(size_bytes=total)
