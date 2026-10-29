import asyncio
from uuid import uuid4
import sys
from types import SimpleNamespace

import pytest
from app.ai.conversation import UNAVAILABLE, AIOrchestrator, MockConversationLLM
from app.integrations.contracts import EmbeddingRequest, EmbeddingResult
from app.integrations.embedding import LocalEmbedding, MODEL_FILES, QUERY_PREFIX, configured_embedding
from app.integrations.mock import MockEmbedding
from app.modules.memory import rag
from app.platform.config import Settings


@pytest.mark.parametrize('change', [
    {'dimension': 9}, {'provider': 'real'}, {'model_version': 'other'},
    {'vectors': []}, {'vectors': [[0.0] * 8]}, {'vectors': [[float('nan')] * 8]},
    {'vectors': [[float('inf')] * 8]}, {'vectors': [[1.0] * 7]},
    {'vectors': [[1e100] * 8]}, {'vectors': [[1e-100] * 8]},
])
def test_bad_embedding_fails_before_publication(monkeypatch, change):
    class Broken(MockEmbedding):
        async def embed(self, request):
            return EmbeddingResult(vectors=[[1.0] * 8], dimension=8, provider='mock',
                model='mock-embedding-v1', model_version=self.capabilities().version).model_copy(update=change)
    monkeypatch.setattr(rag, 'get_provider', Broken)
    with pytest.raises(ValueError):
        asyncio.run(rag.embed(['fictional fixture'], 'fixture'))


def model_directory(tmp_path):
    for name in MODEL_FILES:
        (tmp_path / name).write_text('fictional model fixture', encoding='utf-8')
    return tmp_path


def test_local_inference_uses_only_files_and_separates_query_instruction(tmp_path, monkeypatch):
    seen = []
    class Array:
        def tolist(self): return [1.0] * 512
    class Model:
        def __init__(self, **kwargs): seen.append(kwargs)
        def embed(self, texts, **kwargs):
            seen.append(texts)
            return [Array() for _ in texts]
    monkeypatch.setitem(sys.modules, 'fastembed', SimpleNamespace(TextEmbedding=Model))
    provider = LocalEmbedding(model_directory(tmp_path))
    document = asyncio.run(provider.embed(EmbeddingRequest(request_id='fixture', texts=['虚构陪诊安排'])))
    query = asyncio.run(provider.embed(EmbeddingRequest(request_id='fixture', texts=['谁陪我看病'], purpose='query')))
    assert document.provider == 'local' and query.dimension == 512
    assert provider.capabilities().offline is True
    assert seen[0]['local_files_only'] is True
    assert seen[0]['specific_model_path'] == str(tmp_path.resolve())
    assert seen[1] == ['虚构陪诊安排']
    assert seen[2] == [QUERY_PREFIX + '谁陪我看病']


def test_model_fingerprint_changes_when_weights_or_tokenizer_change(tmp_path):
    model_directory(tmp_path)
    before = LocalEmbedding(tmp_path).capabilities().version
    (tmp_path / 'tokenizer.json').write_text('changed fixture', encoding='utf-8')
    assert LocalEmbedding(tmp_path).capabilities().version != before


def test_local_missing_model_fails_without_mock_fallback(tmp_path):
    with pytest.raises(FileNotFoundError):
        configured_embedding(Settings(embedding_provider='local', embedding_model_path=str(tmp_path)))
    with pytest.raises(ValueError):
        Settings(embedding_provider='local', embedding_model_path=None)
    with pytest.raises(ValueError):
        Settings(app_env='demo', demo_data=True, embedding_provider='local', embedding_model_path=str(tmp_path))


def test_foreign_citation_rejected_even_when_authorized_context_exists():
    class Forged(MockConversationLLM):
        async def generate(self, request):
            value = await super().generate(request)
            return value.model_copy(update={'structured_output': {**value.structured_output, 'memory_refs': [uuid4()]}})
    record = rag.RetrievedMemory(uuid4(), uuid4(), uuid4(), 1, '虚构家庭往事', 'EVENT', 1)
    result = asyncio.run(AIOrchestrator(llm=Forged()).handle(request_id='fixture', conversation_id=uuid4(),
        text='记得我家吗', memory_records=(record,)))
    assert result.assistant_text == UNAVAILABLE and result.memory_records == ()


def test_authorized_title_is_supplied_to_answer_model():
    seen = []
    class Capture(MockConversationLLM):
        async def generate(self, request):
            seen.extend(request.authorized_memory)
            return await super().generate(request)
    record = rag.RetrievedMemory(uuid4(), uuid4(), uuid4(), 1, '每周三一起去医院复诊。',
        'EVENT', 1, title='女儿小梅的陪诊安排')
    asyncio.run(AIOrchestrator(llm=Capture()).handle(request_id='title-fixture', conversation_id=uuid4(),
        text='谁陪我去医院', memory_records=(record,)))
    assert seen[0]['title'] == record.title and seen[0]['content'] == record.content
