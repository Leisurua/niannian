from uuid import UUID
from fastapi import APIRouter, Depends, Header, Request, Response
from app.modules.avatar import service
from app.modules.avatar.schemas import AvatarCreate, AvatarConfirm
from app.modules.audit import service as audit
from app.modules.memory.files import store
from app.platform.authentication import current_identity
from app.platform.config import get_settings
from app.platform.uow import transaction

router = APIRouter(prefix='/v1', tags=['Avatars'])


@router.get('/avatar-generation', operation_id='getAvatarGenerationCapabilities')
async def capabilities(response: Response, actor=Depends(current_identity)):
    response.headers['Cache-Control'] = 'no-store'
    return service.capabilities(get_settings())


@router.post('/avatar-jobs', status_code=201, operation_id='createAvatarJob')
async def create(body: AvatarCreate, request: Request, response: Response, idempotency_key: str = Header(),
    actor=Depends(current_identity), db=Depends(transaction)):
    response.headers['Cache-Control'] = 'no-store'
    settings = get_settings()
    return await service.create(db, actor, body, idempotency_key, store(request, settings), settings, request.state.request_id)


@router.get('/avatar-jobs/latest', operation_id='getLatestAvatarJob')
async def latest(family_id: UUID, response: Response, actor=Depends(current_identity), db=Depends(transaction)):
    response.headers['Cache-Control'] = 'no-store'
    return {'job': await service.latest(db, actor, family_id)}


@router.get('/avatar-jobs/{job_id}', operation_id='getAvatarJob')
async def detail(job_id: UUID, response: Response, actor=Depends(current_identity), db=Depends(transaction)):
    response.headers['Cache-Control'] = 'no-store'
    return await service.view(db, await service.access(db, actor, job_id))


@router.post('/avatar-jobs/{job_id}/complete-upload', operation_id='completeAvatarPhotoUpload')
async def complete(job_id: UUID, request: Request, response: Response, idempotency_key: str = Header(),
    actor=Depends(current_identity), db=Depends(transaction)):
    response.headers['Cache-Control'] = 'no-store'
    settings = get_settings()
    return await service.complete_upload(db, actor, job_id, idempotency_key, store(request, settings), settings, request.state.request_id)


@router.post('/avatar-jobs/{job_id}/confirm', operation_id='confirmAvatarJob')
async def confirm(job_id: UUID, body: AvatarConfirm, request: Request, response: Response, idempotency_key: str = Header(),
    actor=Depends(current_identity), db=Depends(transaction)):
    response.headers['Cache-Control'] = 'no-store'
    return await service.confirm(db, actor, job_id, body, idempotency_key, get_settings(), request.state.request_id)


@router.delete('/avatar-jobs/{job_id}', status_code=202, operation_id='deleteAvatarJob')
async def delete(job_id: UUID, request: Request, response: Response, actor=Depends(current_identity), db=Depends(transaction)):
    response.headers['Cache-Control'] = 'no-store'
    row = await service.access(db, actor, job_id, removal=True)
    await service.cancel(db, row)
    await audit.record(db, actor.user_id, 'AVATAR_DELETED', 'AVATAR', row.id, row.family_id, request.state.request_id)
    return {'status': 'CANCELLED'}


def register_asset(kind, operation):
    async def content(job_id: UUID, request: Request, actor=Depends(current_identity), db=Depends(transaction)):
        settings = get_settings()
        data, mime = await service.asset_content(db, actor, job_id, kind, store(request, settings))
        return Response(data, media_type=mime, headers={'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff'})
    router.add_api_route('/avatar-jobs/{job_id}/' + kind, content, methods=['GET'], operation_id=operation)


register_asset('pack', 'downloadAvatarPack')
register_asset('preview', 'downloadAvatarPreview')
