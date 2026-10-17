import asyncio
from uuid import uuid4

import pytest

from app.ai.conversation import AIOrchestrator, MockConversationLLM, UNAVAILABLE
from app.integrations.contracts import EmbeddingResult
from app.modules.memory import rag


@pytest.mark.parametrize('change', [
    {'dimension': 9}, {'provider': 'real'}, {'model_version': 'other'},
    {'vectors': []}, {'vectors': [[0.0] * 8]}, {'vectors': [[float('nan')] * 8]},
    {'vectors': [[float('inf')] * 8]}, {'vectors': [[1.0] * 7]},
])
def test_bad_embedding_fails_before_publication(monkeypatch, change):
    class Broken:
        async def embed(self, request):
            return EmbeddingResult(vectors=[[1.0] * 8], dimension=8, provider='mock',
                model='mock-embedding-v1', model_version=rag.VERSION).model_copy(update=change)
    monkeypatch.setattr(rag, 'PROVIDER', Broken())
    with pytest.raises(ValueError):
        asyncio.run(rag.embed(['fictional fixture'], 'fixture'))


def test_foreign_citation_rejected_even_when_authorized_context_exists():
    class Forged(MockConversationLLM):
        async def generate(self, request):
            value = await super().generate(request)
            return value.model_copy(update={'structured_output': {**value.structured_output, 'memory_refs': [uuid4()]}})
    record = rag.RetrievedMemory(uuid4(), uuid4(), uuid4(), 1, '虚构家庭往事', 'EVENT', 1)
    result = asyncio.run(AIOrchestrator(llm=Forged()).handle(request_id='fixture', conversation_id=uuid4(),
        text='记得我家吗', memory_records=(record,)))
    assert result.assistant_text == UNAVAILABLE and result.memory_records == ()
