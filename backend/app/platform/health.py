"""Dependency readiness and the durable worker heartbeat."""

from datetime import datetime

from sqlalchemy import DateTime, String, delete, func, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Mapped, mapped_column

from app.platform.db import Base
from app.platform.identifiers import utcnow


EXPECTED_MIGRATION_HEAD = '20261101_operational_readiness'
WORKER_SERVICE = 'worker'


class ServiceHeartbeat(Base):
    __tablename__ = 'service_heartbeat'

    service: Mapped[str] = mapped_column(String(32), primary_key=True)
    instance_id: Mapped[str] = mapped_column(String(64))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


async def record_worker(db, instance_id, started_at, *, now=None):
    now = now or utcnow()
    command = insert(ServiceHeartbeat).values(service=WORKER_SERVICE, instance_id=instance_id,
        started_at=started_at, last_seen_at=now).on_conflict_do_update(index_elements=['service'], set_={
            'instance_id': instance_id, 'started_at': started_at, 'last_seen_at': now,
        })
    await db.execute(command)


async def retire_worker(db, instance_id):
    await db.execute(delete(ServiceHeartbeat).where(ServiceHeartbeat.service == WORKER_SERVICE,
        ServiceHeartbeat.instance_id == instance_id))


async def worker_component(db, stale_seconds, *, now=None):
    row = await db.get(ServiceHeartbeat, WORKER_SERVICE)
    if row is None:
        return {'status': 'missing'}
    age = max(0, int(((now or utcnow()) - row.last_seen_at).total_seconds()))
    return {'status': 'ok' if age <= stale_seconds else 'stale', 'age_seconds': age}


async def worker_is_fresh(db, stale_seconds):
    return (await worker_component(db, stale_seconds))['status'] == 'ok'


async def _database_components(factory, settings):
    from app.platform.tasks import Task

    async with factory() as db:
        await db.execute(text('SELECT 1'))
        try:
            revisions = set((await db.scalars(text('SELECT version_num FROM alembic_version'))).all())
            migration = {'status': 'ok' if revisions == {EXPECTED_MIGRATION_HEAD} else 'mismatch',
                         'expected': EXPECTED_MIGRATION_HEAD}
        except Exception:
            migration = {'status': 'unavailable', 'expected': EXPECTED_MIGRATION_HEAD}
        try:
            worker = await worker_component(db, settings.worker_stale_seconds)
        except Exception:
            worker = {'status': 'unknown'}
        try:
            rows = (await db.execute(select(Task.status, func.count()).where(Task.status != 'SUCCEEDED')
                .group_by(Task.status))).all()
            counts = {name.lower(): 0 for name in ('PENDING', 'RUNNING', 'RETRY', 'DEAD')}
            counts.update({status.lower(): count for status, count in rows})
            tasks = {'status': 'degraded' if counts['dead'] else 'ok', **counts}
        except Exception:
            tasks = {'status': 'unknown'}
        return migration, worker, tasks


async def _storage_component(app, settings):
    from app.platform.storage import S3Storage

    storage = getattr(app.state, 'object_storage', None)
    if storage is None:
        storage = S3Storage(settings)
    probe = getattr(storage, 'health', None)
    if probe is None:
        raise RuntimeError('Storage health probe unavailable')
    await probe()
    return {'status': 'ok'}


async def readiness(app, settings):
    """Return a bounded, secret-free readiness snapshot."""
    import asyncio
    from app.platform.db import session_factory

    factory = getattr(app.state, 'session_factory', session_factory)

    async def database_snapshot():
        try:
            async with asyncio.timeout(3):
                migration, worker, tasks = await _database_components(factory, settings)
            return {'database': {'status': 'ok'}, 'migrations': migration, 'worker': worker, 'tasks': tasks}
        except Exception:
            return {'database': {'status': 'unavailable'}, 'migrations': {'status': 'unknown'},
                    'worker': {'status': 'unknown'}, 'tasks': {'status': 'unknown'}}

    async def storage_snapshot():
        try:
            async with asyncio.timeout(4):
                return await _storage_component(app, settings)
        except Exception:
            return {'status': 'unavailable'}

    database, storage = await asyncio.gather(database_snapshot(), storage_snapshot())
    components = {'api': {'status': 'ok'}, **database, 'storage': storage}
    ready = all(components[name]['status'] == 'ok' for name in (
        'api', 'database', 'migrations', 'storage', 'worker'))
    return ready, components
