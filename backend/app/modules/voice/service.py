from datetime import timedelta
from io import BytesIO
import hashlib
import wave
from uuid import UUID
from sqlalchemy import delete, or_, select
from app.modules.auth.schemas import Input
from app.modules.audit import service as audit
from app.modules.family import service as family
from app.modules.voice.models import VoiceProfile, VoicePreference
from app.platform import tasks
from app.platform.errors import AppError
from app.platform.identifiers import utcnow, uuid7
from pydantic import Field

MAX_SAMPLE = 2_880_044
PREVIEW_TEXT = '您好，我是念念 AI。这是家人授权合成的声音，我可以陪您聊聊天。'


class Create(Input):
    family_id: UUID
    owner_user_id: UUID
    display_name: str = Field(min_length=1, max_length=60)


class Preference(Input):
    family_id: UUID
    voice_profile_id: UUID | None = None
    cloud_tts_allowed: bool


def available(settings):
    return bool(settings.app_env == 'dev' and getattr(settings, 'family_voice_enabled', False) and
                getattr(settings, 'family_voice_api_key', None) and
                getattr(settings, 'family_voice_workspace_id', None))


def view(row):
    return {**{k: str(getattr(row, k)) for k in ('id', 'family_id', 'owner_user_id', 'creator_user_id')},
            'display_name': row.display_name, 'status': row.status, 'version': row.version,
            'error_code': row.error_code, 'sample_available': bool(row.sample_key),
            'preview_available': bool(row.preview_key), 'approved': row.approved_at is not None}


async def access(db, actor, profile_id, *, owner=False):
    row = await db.get(VoiceProfile, profile_id)
    if row is None:
        raise AppError('VOICE_NOT_FOUND', '声音不存在。', 404)
    _, member = await family.context(db, actor.user_id, row.family_id)
    await db.refresh(row)
    if owner and actor.user_id != row.owner_user_id:
        raise AppError('PERMISSION_DENIED', '只能由声音本人确认或撤回。', 403)
    if actor.user_id not in (row.owner_user_id, row.creator_user_id) and not (member.role == 'ELDER' and row.status == 'ACTIVE'):
        raise AppError('VOICE_NOT_FOUND', '声音不存在或不可访问。', 404)
    return row


async def usable(db, actor, profile_id):
    row = await access(db, actor, profile_id)
    await family.require_member(db, row.family_id, row.owner_user_id)
    if row.status != 'ACTIVE' or not row.approved_at or not row.provider_voice_id:
        raise AppError('VOICE_UNAVAILABLE', '此声音暂不可用。', 409)
    return row


async def preference(db, actor, family_id):
    _, member = await family.context(db, actor.user_id, family_id)
    if member.role != 'ELDER':
        raise AppError('PERMISSION_DENIED', '此设置由长辈本人操作。', 403)
    row = await db.get(VoicePreference, (family_id, actor.user_id))
    return {'family_id': str(family_id), 'voice_profile_id': str(row.voice_profile_id) if row and row.voice_profile_id else None,
            'cloud_tts_allowed': row.cloud_tts_allowed if row else False}


async def selected(db, actor, family_id):
    pref = await preference(db, actor, family_id)
    if not pref['cloud_tts_allowed'] or not pref['voice_profile_id']:
        return None, pref['cloud_tts_allowed']
    try:
        return await usable(db, actor, UUID(pref['voice_profile_id'])), True
    except AppError:
        return None, True


async def set_preference(db, actor, body):
    await preference(db, actor, body.family_id)
    if body.voice_profile_id:
        row = await usable(db, actor, body.voice_profile_id)
        if row.family_id != body.family_id or not body.cloud_tts_allowed:
            raise AppError('PERMISSION_DENIED', '请先同意将回复文本发给云端声音服务。', 403)
    pref = await db.get(VoicePreference, (body.family_id, actor.user_id))
    if not pref:
        pref = VoicePreference(family_id=body.family_id, owner_user_id=actor.user_id)
        db.add(pref)
    pref.voice_profile_id, pref.cloud_tts_allowed = body.voice_profile_id, body.cloud_tts_allowed
    await db.flush()
    return await preference(db, actor, body.family_id)


async def listing(db, actor, family_id, playable):
    _, member = await family.context(db, actor.user_id, family_id)
    query = select(VoiceProfile).where(VoiceProfile.family_id == family_id)
    if playable:
        query = query.where(VoiceProfile.status == 'ACTIVE')
    else:
        query = query.where(or_(VoiceProfile.owner_user_id == actor.user_id, VoiceProfile.creator_user_id == actor.user_id))
    rows = (await db.scalars(query.order_by(VoiceProfile.created_at.desc()).limit(100))).all()
    result = []
    for row in rows:
        if playable:
            try:
                await usable(db, actor, row.id)
            except AppError:
                continue
        result.append(view(row))
    return result


async def create(db, actor, body):
    await family.context(db, actor.user_id, body.family_id)
    await family.require_member(db, body.family_id, body.owner_user_id)
    row = VoiceProfile(id=uuid7(), family_id=body.family_id, owner_user_id=body.owner_user_id,
        creator_user_id=actor.user_id, display_name=body.display_name.strip(), status='UPLOADING', version=1,
        expires_at=utcnow() + timedelta(days=7))
    if not row.display_name:
        raise AppError('VALIDATION_ERROR', '请填写声音名称。', 422)
    db.add(row)
    await db.flush()
    return row


def validate_sample(data):
    try:
        if len(data) > MAX_SAMPLE:
            raise ValueError()
        with wave.open(BytesIO(data), 'rb') as recording:
            if (recording.getnchannels(), recording.getsampwidth(), recording.getframerate(), recording.getcomptype()) != (1, 2, 24000, 'NONE'):
                raise ValueError()
            frames = recording.getnframes()
            if not 240000 <= frames <= 1440000 or len(recording.readframes(frames)) != frames * 2:
                raise ValueError()
    except (ValueError, EOFError, wave.Error):
        raise AppError('VOICE_SAMPLE_INVALID', '请录制 10 至 60 秒、24 kHz 单声道的清晰 WAV 录音。', 422) from None


async def upload(db, actor, profile_id, data, storage):
    row = await access(db, actor, profile_id)
    if row.status not in ('UPLOADING', 'PENDING') or row.expires_at <= utcnow():
        raise AppError('VOICE_STATE_INVALID', '请新建录音，已授权样本不能替换。', 409)
    validate_sample(data)
    key = f'voices/{row.id}/sample.wav'
    await storage.write(key, data, 'audio/wav')
    row.sample_key, row.sample_hash, row.status = key, hashlib.sha256(data).hexdigest(), 'PENDING'
    row.version += 1
    return row


async def approve(db, actor, profile_id, settings):
    row = await access(db, actor, profile_id, owner=True)
    if row.status in ('QUEUED', 'GENERATING', 'READY', 'ACTIVE'):
        return row
    if row.status != 'PENDING' or row.expires_at <= utcnow():
        raise AppError('VOICE_STATE_INVALID', '请先完成有效录音。', 409)
    if not available(settings):
        raise AppError('VOICE_NOT_CONFIGURED', '云端声音服务尚未配置。', 503)
    row.status, row.approved_at = 'QUEUED', utcnow()
    row.provider_workspace = settings.family_voice_workspace_id
    await audit.record(db, actor.user_id, 'VOICE_CLONE_APPROVED', 'VOICE_PROFILE', row.id, row.family_id,
        metadata={'sample_hash': row.sample_hash, 'version': row.version, 'scope': 'CURRENT_AND_FUTURE_FAMILY_ELDERS'})
    await tasks.enqueue(db, 'VOICE_GENERATE', row.family_id, row.id, row.version)
    return row


async def revoke(db, row):
    if row.status == 'DELETED':
        return
    row.status = 'REVOKED'
    await tasks.enqueue(db, 'VOICE_CLEANUP', row.family_id, row.id, row.version, rearm=True)


async def activate(db, actor, profile_id):
    row = await access(db, actor, profile_id, owner=True)
    if row.status == 'ACTIVE':
        return row
    if row.status != 'READY' or not row.preview_key:
        raise AppError('VOICE_STATE_INVALID', '请等待制作成功并试听。', 409)
    old = (await db.scalars(select(VoiceProfile).where(VoiceProfile.family_id == row.family_id,
        VoiceProfile.owner_user_id == row.owner_user_id, VoiceProfile.status == 'ACTIVE'))).all()
    for previous in old:
        await revoke(db, previous)
        prefs = (await db.scalars(select(VoicePreference).where(VoicePreference.voice_profile_id == previous.id))).all()
        for pref in prefs:
            pref.voice_profile_id = row.id
    await db.flush()
    row.status, row.expires_at = 'ACTIVE', None
    return row


async def invalidate_member(db, family_id, user_id):
    rows = (await db.scalars(select(VoiceProfile).where(VoiceProfile.family_id == family_id,
        VoiceProfile.owner_user_id == user_id, VoiceProfile.status != 'DELETED'))).all()
    for row in rows:
        await revoke(db, row)
    await db.execute(delete(VoicePreference).where(VoicePreference.family_id == family_id, VoicePreference.owner_user_id == user_id))


async def maintenance(db):
    rows = (await db.scalars(select(VoiceProfile).where(VoiceProfile.status.notin_(('REVOKED', 'DELETED')),
        VoiceProfile.expires_at <= utcnow()).limit(100))).all()
    for row in rows:
        await revoke(db, row)
