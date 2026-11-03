import asyncio
from datetime import timedelta

from sqlalchemy import delete, update

from app.platform.health import ServiceHeartbeat, record_worker
from app.platform.identifiers import utcnow


def test_readiness_distinguishes_worker_state_and_dependencies(system, monkeypatch):
    from app.platform import health
    client, _, factory, _ = system

    async def clear():
        async with factory() as db:
            await db.execute(delete(ServiceHeartbeat))
            await db.commit()

    asyncio.run(clear())
    missing = client.get('/health/ready', headers={'X-Request-ID': 'ready-missing'})
    assert missing.status_code == 503
    body = missing.json()
    assert body['status'] == 'not_ready'
    assert body['components']['database']['status'] == 'ok'
    assert body['components']['migrations']['status'] == 'ok'
    assert body['components']['storage']['status'] == 'ok'
    assert body['components']['worker']['status'] == 'missing'
    assert body['components']['tasks']['dead'] == 0

    async def seed():
        async with factory() as db:
            await record_worker(db, 'integration-worker', utcnow())
            await db.commit()

    asyncio.run(seed())
    ready = client.get('/health/ready', headers={'X-Request-ID': 'ready-ok'})
    assert ready.status_code == 200
    assert ready.json()['status'] == 'ready'
    assert ready.json()['components']['worker']['status'] == 'ok'

    monkeypatch.setattr(health, 'EXPECTED_MIGRATION_HEAD', 'not-the-current-head')
    mismatch = client.get('/health/ready')
    assert mismatch.status_code == 503
    assert mismatch.json()['components']['database']['status'] == 'ok'
    assert mismatch.json()['components']['migrations']['status'] == 'mismatch'
    monkeypatch.setattr(health, 'EXPECTED_MIGRATION_HEAD', '20261101_operational_readiness')

    async def stale():
        async with factory() as db:
            await db.execute(update(ServiceHeartbeat).values(last_seen_at=utcnow() - timedelta(minutes=5)))
            await db.commit()

    asyncio.run(stale())
    stale_response = client.get('/health/ready')
    assert stale_response.status_code == 503
    assert stale_response.json()['components']['worker']['status'] == 'stale'
    asyncio.run(clear())
