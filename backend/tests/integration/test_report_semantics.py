"""Real local topic inference plus authorized report persistence; no substitute vectors."""
import asyncio
import os
from uuid import UUID

import pytest
from sqlalchemy import text

from app.modules.conversation.models import Conversation
from app.modules.report import metrics, semantics
from app.platform.config import get_settings
from app.platform.identifiers import utcnow
from backend.tests.integration.test_reports import enable, report
from backend.tests.integration.test_summary_proactive import converse
from backend.tests.support import URL, grant, household, post

MODEL_PATH = os.environ.get('TEST_EMBEDDING_MODEL_PATH')
pytestmark = pytest.mark.skipif(not URL or not MODEL_PATH, reason='Disposable database and real BGE weights required')


@pytest.fixture
def semantic_report(system, monkeypatch):
    monkeypatch.setenv('EMBEDDING_PROVIDER', 'local')
    monkeypatch.setenv('EMBEDDING_MODEL_PATH', MODEL_PATH)
    get_settings.cache_clear()
    return system


def test_real_synonyms_unknown_and_assertion_boundaries(semantic_report):
    samples = {
        '我把肉馅放进擀好的面皮里，再捏紧边沿。': ('DUMPLINGS',),
        '我给阳台的绿植换盆施肥。': ('GARDENING',),
        '我饭后沿河岸慢慢步行一圈。': ('WALKING',),
        '我想起在单位和同事一起加班的那些年。': ('WORK_STORY',),
        '我想起当年坐在教室里听老师讲课。': ('SCHOOL_STORY',),
        '我盼着儿孙都回到家里，一家人见个面。': ('FAMILY_VISIT',),
        '我今天研究菜谱准备晚饭。': ('COOKING',),
        '我想了解太阳和月亮。': (),
        '我今天逛超市买生活用品。': (),
    }
    async def check():
        for phrase, expected in samples.items():
            result = await semantics.classify_topics(phrase, get_settings())
            assert result.method == 'LOCAL_SEMANTIC'
            assert result.topics == expected, phrase
    asyncio.run(check())


def test_cross_session_topics_permissions_and_no_source_retention(semantic_report):
    client, engine, factory, _ = semantic_report
    home = household(client)
    first = '我今天准备包饺子。'
    second = '我把肉馅放进擀好的面皮里，再捏紧边沿。'
    converse(client, home, second)
    with engine.connect() as conn:
        assert conn.execute(text('SELECT count(*) FROM interaction_metric')).scalar() == 0
    own = enable(client, home); grant(client, home, 'INTERACTION_STATS')
    converse(client, home, first)
    cid = converse(client, home, second)
    async def another_turn():
        async with factory() as db:
            row = await db.get(Conversation, UUID(cid))
            await metrics.collect(db, row, 4, second, utcnow(), utcnow())
            await db.commit()
    asyncio.run(another_turn())
    data = report(client, home).json()['current']['interaction']
    assert data['repeated_topics'] == [dict(topic='包饺子', sessions=2)]
    assert data['topic_classification'] == dict(RULE=1, LOCAL_SEMANTIC=2, RULE_FALLBACK=0)
    with engine.connect() as conn:
        rows = conn.execute(text('SELECT * FROM interaction_metric')).all()
        assert first not in str(rows) and second not in str(rows)
        assert conn.execute(text("SELECT count(*) FROM interaction_metric WHERE topic_model_version IS NOT NULL")).scalar() == 2
    post(client, '/v1/consents/' + own + '/revoke', home[4])
    assert report(client, home).json()['current']['interaction']['repeated_topics'] == []
    enable(client, home)
    assert report(client, home).json()['current']['interaction']['turns'] == 0


def test_grant_expiry_during_inference_discards_metric(semantic_report, monkeypatch):
    from datetime import timedelta
    from app.modules.consent import service as consent
    client, engine, _, _ = semantic_report
    home = household(client); enable(client, home)
    with engine.begin() as conn:
        conn.execute(text("UPDATE consent SET expires_at=now()+interval '1 minute' WHERE scope='INTERACTION_STATS'"))
    async def expire(text, settings):
        now = utcnow()
        monkeypatch.setattr(consent, 'utcnow', lambda: now + timedelta(minutes=2))
        return semantics.TopicResult(('GARDENING',), 'LOCAL_SEMANTIC', 'a' * 64)
    monkeypatch.setattr(metrics, 'classify_topics', expire)
    converse(client, home, '我给盆栽换盆。')
    with engine.connect() as conn:
        assert conn.execute(text('SELECT count(*) FROM interaction_metric')).scalar() == 0
