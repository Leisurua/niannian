from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request, Response

from app.modules.memory import files, service
from app.modules.memory.schemas import Action, FileConfirm, FileUpload, MemoryCreate, MemoryFeedback, MemoryUpdate
from app.modules.memory.validation import MemoryStatus, MemoryType, Visibility
from app.platform.authentication import current_identity
from app.platform.config import get_settings
from app.platform.resource_access import expected_version
from app.platform.uow import transaction

router = APIRouter(prefix='/v1', tags=['Memories'])


@router.get('/memories', operation_id='listMemories')
async def listing(request: Request, family_id: UUID | None = None, subject_user_id: UUID | None = None,
    type: MemoryType | None = None, verification_status: MemoryStatus | None = None, visibility: Visibility | None = None,
    pending_confirmation: bool = False, q: str | None = Query(None, max_length=240),
    limit: int = Query(20, ge=1, le=100), cursor: str | None = Query(None, max_length=512),
    actor=Depends(current_identity), db=Depends(transaction)):
    filters = dict(family_id=family_id, subject_user_id=subject_user_id, type=type,
                   verification_status=verification_status, visibility=visibility, pending_confirmation=pending_confirmation, q=q)
    return await service.listing(db, actor, filters, limit, cursor, get_settings(), request.state.request_id)


@router.post('/memories', status_code=201, operation_id='createMemory')
async def create(body: MemoryCreate, request: Request, idempotency_key: str = Header(), actor=Depends(current_identity), db=Depends(transaction)):
    return await service.create(db, actor, body, idempotency_key, get_settings(), request.state.request_id)


@router.get('/memories/{memory_id}', operation_id='getMemory')
async def detail(memory_id: UUID, request: Request, actor=Depends(current_identity), db=Depends(transaction)):
    return await service.detail(db, actor, memory_id, request.state.request_id)


@router.patch('/memories/{memory_id}', operation_id='updateMemory')
async def update(memory_id: UUID, body: MemoryUpdate, request: Request, if_match: str = Header(), actor=Depends(current_identity), db=Depends(transaction)):
    return await service.update(db, actor, memory_id, body, expected_version(if_match), request.state.request_id)


def register_action(action, operation_id):
    async def handle(memory_id: UUID, request: Request, idempotency_key: str = Header(), actor=Depends(current_identity), db=Depends(transaction)):
        return await service.action(db, actor, memory_id, action, Action(), idempotency_key, get_settings(), request.state.request_id)
    router.add_api_route('/memories/{memory_id}/' + action, handle, methods=['POST'], operation_id=operation_id)


register_action('confirm', 'confirmMemory')
register_action('reject', 'rejectMemory')
register_action('revoke', 'revokeMemory')


@router.delete('/memories/{memory_id}', status_code=202, operation_id='deleteMemory')
async def delete(memory_id: UUID, request: Request, idempotency_key: str = Header(), actor=Depends(current_identity), db=Depends(transaction)):
    return await service.action(db, actor, memory_id, 'delete', Action(), idempotency_key, get_settings(), request.state.request_id)


@router.post('/memories/{memory_id}/feedback', status_code=202, operation_id='reportMemoryFeedback')
async def feedback(memory_id: UUID, body: MemoryFeedback, request: Request, idempotency_key: str = Header(), actor=Depends(current_identity), db=Depends(transaction)):
    return await service.feedback(db, actor, memory_id, body, idempotency_key, get_settings(), request.state.request_id)


@router.post('/files/upload-requests', status_code=201, operation_id='createFileUploadRequest')
async def upload(body: FileUpload, request: Request, actor=Depends(current_identity), db=Depends(transaction)):
    settings = get_settings()
    return await files.upload(db, actor, body, files.store(request, settings), settings, request.state.request_id)


@router.post('/files/{file_id}/confirm', status_code=202, operation_id='confirmFileUpload')
async def confirm(file_id: UUID, body: FileConfirm, request: Request, idempotency_key: str = Header(), actor=Depends(current_identity), db=Depends(transaction)):
    settings = get_settings()
    return await files.confirm(db, actor, file_id, body, idempotency_key, files.store(request, settings), settings, request.state.request_id)


@router.get('/files/{file_id}/download-url', operation_id='createFileDownloadUrl')
async def download_url(file_id: UUID, request: Request, actor=Depends(current_identity), db=Depends(transaction)):
    return await files.download_url(db, actor, file_id, get_settings(), request.state.request_id)


@router.get('/files/{file_id}/content', operation_id='downloadFileContent')
async def download(file_id: UUID, request: Request, expires: int = Query(ge=1), signature: str = Query(min_length=1, max_length=128),
    actor=Depends(current_identity), db=Depends(transaction)):
    settings = get_settings()
    data, mime = await files.content(db, actor, file_id, expires, signature, files.store(request, settings), settings, request.state.request_id)
    return Response(data, media_type=mime, headers={'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff', 'Content-Disposition': 'inline; filename="photo"'})


@router.delete('/files/{file_id}', status_code=202, operation_id='deleteFile')
async def delete_file(file_id: UUID, request: Request, idempotency_key: str = Header(), actor=Depends(current_identity), db=Depends(transaction)):
    return await files.delete(db, actor, file_id, idempotency_key, get_settings(), request.state.request_id)
