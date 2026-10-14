import hashlib
import io
from uuid import UUID

import pytest
from pydantic import ValidationError

from app.modules.memory.file_validation import (
    FilePreflightError, UploadDeclaration, verify_upload_bytes,
)
from app.modules.memory.validation import MemoryDraft

FAMILY = UUID('0192f1e4-6ed8-7c21-a4c1-5d58db7c3001')
SUBJECT = UUID('0192f1e4-6ed8-7c21-a4c1-5d58db7c3002')


def draft(**changes):
    return MemoryDraft.model_validate(dict(
        family_id=FAMILY, subject_user_id=SUBJECT, type='EVENT', title='虚构往事',
        content='仅用于测试的虚构记忆', required_consent_scope='FAMILY_MEMORY', **changes,
    ))


def test_model_candidate_is_pending_and_cannot_self_confirm():
    assert draft(source='AI_CANDIDATE').verification_status == 'PENDING'
    with pytest.raises(ValidationError):
        draft(source='AI_CANDIDATE', verification_status='CONFIRMED')
    assert draft(source='USER', verification_status='CONFIRMED').source == 'USER'
    assert draft().source is None


@pytest.mark.parametrize('changes', [
    {'verification_status': 'DELETED'}, {'verification_status': 'REJECTED'},
    {'verification_status': 'REVOKED'}, {'verified_by': SUBJECT},
    {'expires_at': '2026-10-09T12:00:00'}, {'attachment_ids': [SUBJECT, SUBJECT]},
    {'source': 'PROVIDER_CONFIRMED'}, {'content': 'a' * 10001},
])
def test_untrusted_memory_fields_are_rejected(changes):
    body = dict(family_id=FAMILY, subject_user_id=SUBJECT, type='EVENT', title='测试',
                content='虚构', required_consent_scope='FAMILY_MEMORY')
    with pytest.raises(ValidationError):
        MemoryDraft.model_validate(body | changes)


def declaration(data, mime='image/png', **changes):
    fields = dict(media_type='PHOTO', mime_type=mime, size_bytes=len(data),
                  checksum=hashlib.sha256(data).hexdigest())
    return UploadDeclaration(**(fields | changes))


@pytest.mark.parametrize('data,mime', [
    (b'\x89PNG\r\n\x1a\nfictional', 'image/png'),
    (b'\xff\xd8\xfffictional', 'image/jpeg'),
    (b'RIFF\x00\x00\x00\x00WEBPfictional', 'image/webp'),
])
def test_header_and_digest_match_still_requires_real_inspection(data, mime):
    # These are deliberately NOT valid decoded images; magic bytes alone never
    # produce AVAILABLE. One-byte chunks exercise signatures across boundaries.
    source = io.BytesIO(data)
    result = verify_upload_bytes(declaration(data, mime), iter(lambda: source.read(1), b''), max_size_bytes=128)
    assert result.size_bytes == len(data)
    assert result.needs_content_inspection is True


@pytest.mark.parametrize('changes,code', [
    ({'media_type': 'AUDIO'}, 'FILE_TYPE_NOT_ALLOWED'),
    ({'mime_type': 'image/svg+xml'}, 'FILE_TYPE_NOT_ALLOWED'),
    ({'mime_type': 'text/html'}, 'FILE_TYPE_NOT_ALLOWED'),
    ({'size_bytes': 0}, 'FILE_SIZE_INVALID'),
    ({'size_bytes': True}, 'FILE_SIZE_INVALID'),
    ({'size_bytes': 129}, 'FILE_SIZE_INVALID'),
    ({'checksum': '0' * 64}, 'FILE_CHECKSUM_INVALID'),
    ({'checksum': '../fictional'}, 'FILE_CHECKSUM_INVALID'),
])
def test_bad_declaration_is_rejected_before_reading_stream(changes, code):
    def must_not_read():
        pytest.fail('Invalid declaration must fail before any object read')
        yield b''
    with pytest.raises(FilePreflightError, match=code):
        verify_upload_bytes(declaration(b'fictional', **changes), must_not_read(), max_size_bytes=128)


def test_size_mismatch_corruption_and_mime_spoofing():
    data = b'\x89PNG\r\n\x1a\nfictional'
    with pytest.raises(FilePreflightError, match='FILE_SIZE_INVALID'):
        verify_upload_bytes(declaration(data), [data[:-1]], max_size_bytes=128)
    with pytest.raises(FilePreflightError, match='FILE_CHECKSUM_MISMATCH'):
        verify_upload_bytes(declaration(data), [data[:-1] + b'X'], max_size_bytes=128)
    with pytest.raises(FilePreflightError, match='FILE_CONTENT_TYPE_MISMATCH'):
        verify_upload_bytes(declaration(b'<script>fictional</script>'), [b'<script>fictional</script>'], max_size_bytes=128)
    assert verify_upload_bytes(declaration(data, checksum=hashlib.sha256(data).hexdigest().upper()), [data], max_size_bytes=128)


def test_oversized_stream_stops_without_consuming_remaining_chunks():
    data = b'\x89PNG\r\n\x1a\nfictional'
    def stream():
        yield data + b'overflow'
        pytest.fail('Must stop consuming an oversized object')
    with pytest.raises(FilePreflightError, match='FILE_SIZE_INVALID'):
        verify_upload_bytes(declaration(data), stream(), max_size_bytes=128)
