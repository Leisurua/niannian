from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.device import service
from app.modules.device.schemas import DeviceRegister
from app.platform.authentication import current_identity
from app.platform.config import get_settings
from app.platform.uow import transaction

router = APIRouter(prefix='/v1', tags=['Devices'])


@router.post('/devices/register', status_code=201, operation_id='registerDevice')
async def register(body: DeviceRegister, request: Request, idempotency_key: str = Header(),
                   actor=Depends(current_identity), db: AsyncSession = Depends(transaction)):
    return {**await service.register(db, actor, body, idempotency_key, get_settings(), request.state.request_id),
            'request_id': request.state.request_id}


@router.get('/devices', operation_id='listDevices')
async def listing(request: Request, family_id: UUID | None = None, limit: int = Query(20, ge=1, le=100),
                  cursor: str | None = Query(None, max_length=512), actor=Depends(current_identity),
                  db: AsyncSession = Depends(transaction)):
    return await service.listing(db, actor, family_id, limit, cursor, get_settings(), request.state.request_id)
