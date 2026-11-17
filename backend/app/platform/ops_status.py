"""Read-only operational summary for deployment operators."""

import asyncio
from hmac import compare_digest

from fastapi import APIRouter, Header, Request
from fastapi.responses import JSONResponse
from sqlalchemy import func, or_, select
from sqlalchemy.exc import SQLAlchemyError

from app.modules.notification.models import Notification
from app.platform.config import get_settings
from app.platform.db import session_factory
from app.platform.errors import error_response
from app.platform.health import EXPECTED_MIGRATION_HEAD, task_counts
from app.platform.identifiers import utcnow


router = APIRouter(include_in_schema=False)
CHANNELS = ('IN_APP', 'PUSH', 'SMS', 'PHONE')
QUERY_TIMEOUT = 3


async def notification_counts(db):
    unknown = Notification.error_code == 'DELIVERY_UNKNOWN'
    rows = (await db.execute(select(Notification.channel, func.count(), func.count().filter(unknown))
        .where(Notification.deleted_at.is_(None), Notification.retention_until > utcnow(),
               or_(Notification.status == 'FAILED', Notification.error_code == 'PROVIDER_DELIVERY_FAILED'))
        .group_by(Notification.channel))).all()
    counts = {channel: {'failed': 0, 'unknown': 0} for channel in CHANNELS}
    for channel, total, uncertain in rows:
        counts[channel] = {'failed': total - uncertain, 'unknown': uncertain}
    return counts


@router.get('/internal/ops/status')
async def status(request: Request, authorization: str = Header(default='')):
    settings = get_settings()
    token = settings.ops_status_token.get_secret_value()
    scheme, _, provided = authorization.partition(' ')
    if not token:
        response = error_response(request, status_code=404, code='NOT_FOUND', message='Not found')
    elif scheme.lower() != 'bearer' or not compare_digest(provided.encode(), token.encode()):
        response = error_response(request, status_code=401, code='OPS_AUTH_REQUIRED', message='Operator credential required')
        response.headers['WWW-Authenticate'] = 'Bearer'
    else:
        response = await summary(request, settings)
    response.headers['Cache-Control'] = 'no-store'
    return response


async def summary(request, settings):
    version = {'api': request.app.version, 'build_revision': settings.ops_build_revision or None,
               'expected_migration': EXPECTED_MIGRATION_HEAD}
    factory = getattr(request.app.state, 'session_factory', session_factory)
    query = asyncio.create_task(read_counts(factory))
    query.add_done_callback(observe_cleanup)
    try:
        done, _ = await asyncio.wait({query}, timeout=QUERY_TIMEOUT)
        if done:
            tasks, notifications = query.result()
            return JSONResponse({'status': 'ok', 'version': version, 'tasks': tasks, 'notifications': notifications})
    except SQLAlchemyError:
        pass
    finally:
        if not query.done():
            # Returning 503 must not wait for a paused database to acknowledge cancellation.
            query.cancel()
    return JSONResponse({'status': 'unavailable', 'version': version, 'tasks': None, 'notifications': None},
                        status_code=503)


async def read_counts(factory):
    async with factory() as db:
        return await task_counts(db), await notification_counts(db)


def observe_cleanup(query):
    if not query.cancelled():
        query.exception()
