from uuid import UUID
from fastapi import APIRouter, Depends, Request, Response
from app.modules.voice import service
from app.modules.memory.files import store
from app.modules.audit import service as audit
from app.platform.authentication import current_identity
from app.platform.config import get_settings
from app.platform.uow import transaction
from app.platform.errors import AppError

router = APIRouter(prefix='/v1', tags=['Family voices'])


@router.get('/voice-profiles', operation_id='listVoiceProfiles')
async def listing(family_id: UUID, response: Response, available: bool = False,
                  actor=Depends(current_identity), db=Depends(transaction)):
    response.headers['Cache-Control'] = 'no-store'
    return {'items': await service.listing(db, actor, family_id, available),
            'available': service.available(get_settings())}


@router.post('/voice-profiles', status_code=201, operation_id='createVoiceProfile')
async def create(body: service.Create, actor=Depends(current_identity), db=Depends(transaction)):
    return service.view(await service.create(db, actor, body))


@router.get('/voice-preferences', operation_id='getVoicePreference')
async def preference(family_id: UUID, response: Response, actor=Depends(current_identity), db=Depends(transaction)):
    response.headers['Cache-Control'] = 'no-store'
    return await service.preference(db, actor, family_id)


@router.put('/voice-preferences', operation_id='setVoicePreference')
async def set_preference(body: service.Preference, request: Request, actor=Depends(current_identity), db=Depends(transaction)):
    result = await service.set_preference(db, actor, body)
    await audit.record(db, actor.user_id, 'CLOUD_TTS_PREFERENCE_CHANGED', 'VOICE_PREFERENCE',
        actor.user_id, body.family_id, request.state.request_id,
        metadata={'allowed': body.cloud_tts_allowed})
    return result


@router.get('/voice-profiles/{profile_id}', operation_id='getVoiceProfile')
async def detail(profile_id: UUID, response: Response, actor=Depends(current_identity), db=Depends(transaction)):
    response.headers['Cache-Control'] = 'no-store'
    return service.view(await service.access(db, actor, profile_id))


@router.put('/voice-profiles/{profile_id}/sample', operation_id='uploadVoiceSample')
async def upload(profile_id: UUID, request: Request, actor=Depends(current_identity), db=Depends(transaction)):
    await service.access(db, actor, profile_id)
    data = bytearray()
    async for chunk in request.stream():
        data.extend(chunk)
        if len(data) > service.MAX_SAMPLE:
            raise AppError('FILE_TOO_LARGE', '录音不能超过 60 秒。', 413)
    return service.view(await service.upload(db, actor, profile_id, bytes(data), store(request, get_settings())))


@router.post('/voice-profiles/{profile_id}/approve', operation_id='approveVoiceProfile')
async def approve(profile_id: UUID, actor=Depends(current_identity), db=Depends(transaction)):
    return service.view(await service.approve(db, actor, profile_id, get_settings()))


@router.post('/voice-profiles/{profile_id}/activate', operation_id='activateVoiceProfile')
async def activate(profile_id: UUID, request: Request, actor=Depends(current_identity), db=Depends(transaction)):
    row = await service.activate(db, actor, profile_id)
    await audit.record(db, actor.user_id, 'VOICE_ACTIVATED', 'VOICE_PROFILE', row.id, row.family_id, request.state.request_id)
    return service.view(row)


@router.delete('/voice-profiles/{profile_id}', status_code=202, operation_id='revokeVoiceProfile')
async def revoke(profile_id: UUID, request: Request, actor=Depends(current_identity), db=Depends(transaction)):
    row = await service.access(db, actor, profile_id)
    if actor.user_id != row.owner_user_id and row.status not in ('UPLOADING', 'PENDING'):
        raise AppError('PERMISSION_DENIED', '已授权声音只能由本人撤回。', 403)
    await service.revoke(db, row)
    await audit.record(db, actor.user_id, 'VOICE_REVOKED', 'VOICE_PROFILE', row.id, row.family_id, request.state.request_id)
    return service.view(row)


def asset(kind, operation):
    async def content(profile_id: UUID, request: Request, actor=Depends(current_identity), db=Depends(transaction)):
        row = await service.access(db, actor, profile_id)
        if row.status in ('REVOKED', 'DELETED'):
            raise AppError('VOICE_UNAVAILABLE', '声音已撤回。', 404)
        if kind == 'sample' and actor.user_id not in (row.owner_user_id, row.creator_user_id):
            raise AppError('PERMISSION_DENIED', '无权访问原始录音。', 403)
        if row.expires_at and row.expires_at <= service.utcnow():
            raise AppError('VOICE_UNAVAILABLE', '录音已过期。', 404)
        key = row.sample_key if kind == 'sample' else row.preview_key
        if not key:
            raise AppError('VOICE_UNAVAILABLE', '录音尚不可用或已清理。', 404)
        data = await store(request, get_settings()).read(key, 3_000_000)
        await audit.record(db, actor.user_id, 'VOICE_AUDIO_READ', 'VOICE_PROFILE', row.id, row.family_id, request.state.request_id, metadata={'kind': kind})
        return Response(data, media_type='audio/wav', headers={'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff'})
    router.add_api_route('/voice-profiles/{profile_id}/' + kind, content, methods=['GET'], operation_id=operation)


asset('sample', 'downloadVoiceSample')
asset('preview', 'previewVoiceProfile')
