"""Real CPU model + pgvector. Never substitute synthetic vectors for this check."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import threading

import pytest
from sqlalchemy import text

from app.ai.conversation import UNKNOWN
from app.modules.memory import rag
from app.platform.config import get_settings
from backend.tests.integration.test_rag_offline import drain, own_grant, retrieve
from backend.tests.support import URL, grant, handshake, household, memory, post, start, ws_frame

MODEL_PATH = os.environ.get('TEST_EMBEDDING_MODEL_PATH')
pytestmark = pytest.mark.skipif(not URL or not MODEL_PATH, reason='Explicit test database and local BGE model required')
FACT = '下周三女儿小梅陪我到医院复查，上午九点在门口等。'


@pytest.fixture
def semantic(system, monkeypatch):
    monkeypatch.setenv('EMBEDDING_PROVIDER', 'local')
    monkeypatch.setenv('EMBEDDING_MODEL_PATH', str(Path(MODEL_PATH).resolve()))
    get_settings.cache_clear()
    return system


def setup(system):
    client, _, factory, storage = system
    home = household(client)
    grant(client, home)
    own = own_grant(client, home)
    row = memory(client, home, title='下周医院陪诊安排', content=FACT)
    memory(client, home, title='公园散步', content='上周儿子小林陪我在公园散步。')
    memory(client, home, title='孙女的喜好', content='小孙女喜欢吃苹果。')
    asyncio.run(drain(factory, storage))
    return home, row, own


def test_real_semantic_questions_conversation_and_immediate_revoke(semantic):
    client, engine, factory, _ = semantic
    home, row, own = setup(semantic)
    for query in ('下周谁陪我去医院', '下星期看病是谁陪着我', '我去复诊有人陪同吗'):
        records = retrieve(factory, home, query)
        assert [str(record.id) for record in records] == [row['id']]
        assert records[0].content == FACT
    assert retrieve(factory, home, '火星上有几座城市') == ()
    with engine.connect() as connection:
        assert connection.execute(text('SELECT DISTINCT provider, dimension FROM memory_embedding')).all() == [('local', 512)]
    cid = start(client, home)
    with client.websocket_connect('/v1/ws/conversations/' + cid, headers=home[4]) as ws:
        handshake(ws, cid)
        ws.send_json(ws_frame(cid, 'text.input', 2, {'text': '下周谁陪我去医院'}))
        assert ws.receive_json()['payload']['state'] == 'THINKING'
        assert ws.receive_json()['payload']['text'] == 'Mock · 已确认的家庭记录：' + FACT
        ws.receive_json()
        assert post(client, '/v1/consents/' + own + '/revoke', home[4]).status_code == 201
        # Deliberately leave the old vectors in the database.
        with engine.connect() as connection:
            assert connection.execute(text('SELECT count(*) FROM memory_embedding')).scalar() > 0
        assert retrieve(factory, home, '下周谁陪我去医院') == ()
        ws.send_json(ws_frame(cid, 'repeat', 3))
        assert ws.receive_json()['payload']['text'] == UNKNOWN
        ws.receive_json()


def test_mock_and_old_model_indexes_are_rebuilt(system, monkeypatch):
    client, engine, factory, storage = system
    home, row, _ = setup(system)
    assert [str(record.id) for record in retrieve(factory, home, FACT)] == [row['id']]
    monkeypatch.setenv('EMBEDDING_PROVIDER', 'local')
    monkeypatch.setenv('EMBEDDING_MODEL_PATH', str(Path(MODEL_PATH).resolve()))
    get_settings.cache_clear()
    assert retrieve(factory, home, '下周谁陪我去医院') == ()
    async def rebuild():
        async with factory() as db:
            await rag.maintenance(db)
            await db.commit()
        await drain(factory, storage)
    asyncio.run(rebuild())
    assert str(retrieve(factory, home, '下周谁陪我去医院')[0].id) == row['id']
    with engine.begin() as connection:
        connection.execute(text("UPDATE memory_embedding SET model_version='old-model-fixture'"))
    assert retrieve(factory, home, '下周谁陪我去医院') == ()
    asyncio.run(rebuild())
    assert str(retrieve(factory, home, '下周谁陪我去医院')[0].id) == row['id']
    with engine.connect() as connection:
        assert connection.execute(text('SELECT DISTINCT dimension FROM memory_embedding')).all() == [(512,)]


def test_revoke_during_query_embedding_never_returns_stale_records(semantic, monkeypatch):
    client, _, factory, _ = semantic
    home, _, own = setup(semantic)
    provider = rag.get_provider()
    started, release = threading.Event(), threading.Event()
    original = provider.embed
    async def held(request):
        started.set()
        while not release.is_set():
            await asyncio.sleep(0.01)
        return await original(request)
    monkeypatch.setattr(provider, 'embed', held)
    with ThreadPoolExecutor(max_workers=2) as pool:
        pending = pool.submit(retrieve, factory, home, '下周谁陪我去医院')
        try:
            assert started.wait(3)
            revoked = pool.submit(post, client, '/v1/consents/' + own + '/revoke', home[4])
            assert revoked.result(timeout=3).status_code == 201
        finally:
            release.set()
        assert pending.result(timeout=5) == ()


def test_revoke_during_indexing_prevents_late_publication(semantic, monkeypatch):
    client, engine, factory, storage = semantic
    home = household(client)
    grant(client, home)
    own = own_grant(client, home)
    memory(client, home, title='下周医院陪诊安排', content=FACT)
    provider = rag.get_provider()
    started, release = threading.Event(), threading.Event()
    original = provider.embed
    async def held(request):
        started.set()
        while not release.is_set():
            await asyncio.sleep(0.01)
        return await original(request)
    monkeypatch.setattr(provider, 'embed', held)
    with ThreadPoolExecutor(max_workers=2) as pool:
        pending = pool.submit(asyncio.run, drain(factory, storage))
        try:
            assert started.wait(3)
            revoked = pool.submit(post, client, '/v1/consents/' + own + '/revoke', home[4])
            assert revoked.result(timeout=3).status_code == 201
        finally:
            release.set()
        pending.result(timeout=5)
    with engine.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM memory_embedding WHERE status='ACTIVE'")).scalar() == 0


def test_real_vectors_still_enforce_source_family_and_visibility(semantic):
    client, engine, factory, _ = semantic
    home, row, _ = setup(semantic)
    other = post(client, '/v1/families', home[2], {'name': '其他虚构家庭'}).json()['id']
    assert retrieve(factory, home, '下周谁陪我去医院', family=other) == ()
    with engine.begin() as connection:
        connection.execute(text("UPDATE memory SET visibility='OWNER_ONLY'"))
    assert retrieve(factory, home, '下周谁陪我去医院', actor=home[1]) == ()
    with engine.begin() as connection:
        connection.execute(text('UPDATE memory SET version=version+1'))
    assert retrieve(factory, home, '下周谁陪我去医院') == ()
