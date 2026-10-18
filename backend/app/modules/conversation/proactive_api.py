from uuid import UUID
from fastapi import APIRouter, Depends, Header, Request, Response

from app.modules.conversation import proactive
from app.platform.authentication import current_identity
from app.platform.config import get_settings
from app.platform.resource_access import expected_version
from app.platform.uow import transaction

router = APIRouter(prefix='/v1/families/{family_id}/proactive-preferences/{owner_user_id}', tags=['Conversations'])


@router.get('', operation_id='getProactivePreference')
async def get(family_id: UUID, owner_user_id: UUID, request: Request, response: Response,
              actor=Depends(current_identity), db=Depends(transaction)):
    response.headers['Cache-Control'] = 'no-store'
    return await proactive.read(db, actor, family_id, owner_user_id, request.state.request_id)


@router.put('', operation_id='putProactivePreference')
async def put(family_id: UUID, owner_user_id: UUID, body: proactive.PreferenceInput, request: Request,
              if_match: str = Header(), actor=Depends(current_identity), db=Depends(transaction)):
    return await proactive.update(db, actor, family_id, owner_user_id, body, expected_version(if_match), request.state.request_id)


@router.post('/confirm', operation_id='confirmProactivePreference')
async def confirm(family_id: UUID, owner_user_id: UUID, body: proactive.ConfirmInput, request: Request,
                  idempotency_key: str = Header(), actor=Depends(current_identity), db=Depends(transaction)):
    return await proactive.command(db, actor, family_id, owner_user_id, 'confirm', body.model_dump(),
        idempotency_key, get_settings(), request.state.request_id)


@router.post('/pause-today', operation_id='pauseProactiveToday')
async def pause(family_id: UUID, owner_user_id: UUID, request: Request,
                idempotency_key: str = Header(), actor=Depends(current_identity), db=Depends(transaction)):
    return await proactive.command(db, actor, family_id, owner_user_id, 'pause', {}, idempotency_key,
        get_settings(), request.state.request_id)
