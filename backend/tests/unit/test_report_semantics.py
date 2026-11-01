import asyncio
from types import SimpleNamespace

import pytest

from app.modules.report import semantics
from app.modules.report.metrics import classify


@pytest.mark.parametrize('text', [
    '我不想包饺子。', '女儿说她每天给盆栽施肥。', '如果我去散步。',
    '“我包饺子。每天种花。以前上班很忙。”', '你喜欢下厨吗？', '我女儿喜欢种花。',
])
def test_nonaffirmed_topics_never_reach_embedding(monkeypatch, text):
    monkeypatch.setattr(semantics, 'configured_embedding', lambda _: pytest.fail('Unasserted text sent to model'))
    result = asyncio.run(semantics.classify_topics(text, SimpleNamespace(embedding_provider='local')))
    assert result.topics == () and classify(text)[0] == []


def test_semantic_failure_is_explicit_and_mock_is_never_semantic(monkeypatch):
    settings = SimpleNamespace(embedding_provider='local', embedding_timeout_seconds=1)
    def unavailable(_):
        raise OSError('local weights unavailable')
    monkeypatch.setattr(semantics, 'configured_embedding', unavailable)
    result = asyncio.run(semantics.classify_topics('我包饺子，今天还给盆栽换盆。', settings))
    assert result.topics == ('DUMPLINGS',) and result.method == 'RULE_FALLBACK'
    settings.embedding_provider = 'mock'
    result = asyncio.run(semantics.classify_topics('我包饺子，今天还给盆栽换盆。', settings))
    assert result.method == 'RULE' and result.model_version is None


def test_explicit_emotion_synonyms_do_not_infer_another_persons_mood():
    assert classify('我今天挺舒心。')[0] == ['HAPPY']
    assert classify('我心里发愁。')[0] == ['WORRIED']
    assert classify('我心情低落。')[0] == ['SAD']
    assert classify('我没有心情低落。')[0] == []
    assert classify('女儿今天很难过。')[0] == []
    assert classify('我不开心，朋友说我孤单。')[0] == []


def test_denial_in_one_clause_does_not_change_an_affirmed_clause():
    assert classify('我不想散步，我今天喜欢下厨。')[1] == ['COOKING']
    assert classify('女儿不开心，我很高兴。')[0] == ['HAPPY']
    assert classify('如果明天下雨，我就在家做饭。')[1] == []
