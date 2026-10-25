from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request, Response

from app.modules.audit import service as audit
from app.modules.family import service as family
from app.modules.report import metrics, service
from app.platform.authentication import current_identity
from app.platform.uow import transaction

router = APIRouter(prefix='/v1', tags=['Reports'])


@router.get('/statistics', operation_id='getStatistics')
async def statistics(request: Request, response: Response, family_id: UUID, owner_user_id: UUID,
                     start: date, end: date, timezone: str = Query(default='Asia/Shanghai', max_length=64),
                     x_access_reason: str | None = Header(default=None), actor=Depends(current_identity), db=Depends(transaction)):
    response.headers['Cache-Control'] = 'no-store'
    return await service.statistics(db, actor, family_id, owner_user_id, start, end, timezone, x_access_reason, request.state.request_id)


@router.get('/reports/weekly', operation_id='getWeeklyReport')
async def weekly(request: Request, response: Response, family_id: UUID, owner_user_id: UUID,
                 week_start: date | None = None, timezone: str = Query(default='Asia/Shanghai', max_length=64),
                 x_access_reason: str | None = Header(default=None), actor=Depends(current_identity), db=Depends(transaction)):
    response.headers['Cache-Control'] = 'no-store'
    return await service.weekly(db, actor, family_id, owner_user_id, week_start, timezone, x_access_reason, request.state.request_id)


@router.delete('/reports/data', status_code=204, operation_id='deleteMyInteractionStatistics')
async def erase(request: Request, family_id: UUID, actor=Depends(current_identity), db=Depends(transaction)):
    await family.context(db, actor.user_id, family_id)
    await metrics.erase(db, family_id, actor.user_id)
    await audit.record(db, actor.user_id, 'INTERACTION_STATS_DELETED', 'REPORT', actor.user_id, family_id, request.state.request_id)
    return Response(status_code=204, headers={'Cache-Control': 'no-store'})
