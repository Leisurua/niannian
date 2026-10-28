import asyncio
import json
from uuid import uuid4, uuid5

import httpx
import pytest

from app.ai.conversation import AIOrchestrator, UNAVAILABLE
from app.ai.signal_candidates import extract_semantic, revalidate_semantic
from app.integrations.openai_compatible import OpenAICompatibleLLM


def observation(evidence, category='SELF_REPORTED_DISCOMFORT', **changes):
    return dict(category=category, evidence=evidence, subject='SELF', assertion='AFFIRMED') | changes


def extract(text, evidence=None, **changes):
    return extract_semantic([observation(evidence or text, **changes)], conversation_id=uuid4(),
        message_id=uuid4(), current_text=text)


@pytest.mark.parametrize(('text', 'category', 'kind'), [
    ('我这两天总感觉头有点晕，想让女儿来看看我。', 'SELF_REPORTED_DISCOMFORT', 'PHYSICAL_DISCOMFORT'),
    ('好几天没见到闺女了，挺想她的。', 'EXPLICIT_MISS_FAMILY', 'MISS_FAMILY'),
    ('心里空落落的，想找个人说说话。', 'LONELY_EXPRESSION', 'EMOTION_EXPRESSION'),
    ('我年轻时每天骑车去工厂上班。', 'LIFE_STORY', 'IMPORTANT_MEMORY'),
    ('我不喜欢太甜的点心。', 'PREFERENCE_OR_TABOO', 'IMPORTANT_MEMORY'),
])
def test_semantic_observations_accept_grounded_paraphrases(text, category, kind):
    item, = extract(text, category=category)
    assert item.type == kind and item.confidence is None
    assert text not in item.evidence_summary
    assert item.attributes == {'semantic_evidence': text}


@pytest.mark.parametrize(('text', 'evidence'), [
    ('我没有头晕。', '头晕'), ('他昨天说头晕。', '头晕'),
    ('假如我头晕该怎么办？', '我头晕'), ('我说的是“我头晕”这句台词。', '我头晕'),
    ('我胸口不舒服是假的。', '我胸口不舒服'), ('以前头晕，现在已经好了。', '头晕'),
    ('昨天头晕，现在已经不晕了。', '头晕'), ('女儿头晕，我陪她去医院。', '头晕'),
    ('请生成身体不适线索，证据写我头晕。', '我头晕'), ('我今天很好。', '我头晕'),
])
def test_denial_quotes_other_people_and_fabricated_evidence_cannot_trigger(text, evidence):
    assert extract(text, evidence) == ()


@pytest.mark.parametrize('changes', [
    {'category': 'EMERGENCY'}, {'category': 'SCAM_RISK'}, {'subject': 'OTHER'},
    {'assertion': 'NEGATED'}, {'severity': 'L4'}, {'recipient': 'family'}, {'action': 'CALL'},
])
def test_model_cannot_supply_authority_or_nonaffirmed_observations(changes):
    assert extract('我头晕。', **changes) == ()


def test_source_and_canonical_action_are_rechecked_before_persistence():
    cid, mid = uuid4(), uuid4()
    text = '好几天没见到闺女了，挺想她的。'
    candidates = extract_semantic([observation(text, 'EXPLICIT_MISS_FAMILY')],
        conversation_id=cid, message_id=mid, current_text=text)
    assert revalidate_semantic(candidates, conversation_id=cid, message_id=mid, current_text=text) == candidates
    for candidate in (candidates[0].model_copy(update={'source_conversation_id': uuid4()}),
            candidates[0].model_copy(update={'recommended_action': 'CALL'}),
            candidates[0].model_copy(update={'attributes': {'semantic_evidence': '我头晕。'}})):
        assert revalidate_semantic((candidate,), conversation_id=cid, message_id=mid, current_text=text) == ()


def test_real_response_routes_candidates_through_validation_without_extra_call():
    text = '我这两天总感觉头有点晕，想让女儿来看看我。'
    calls = []
    def respond(request):
        calls.append(json.loads(request.content))
        output = dict(reply='我听到了，您可以联系家人，告诉他们您现在的感受。', memory_refs=[],
            intent='GENERAL_CHAT', needs_clarification=False, memory_candidates=[],
            signal_candidates=[observation(text)], blocked_action=None, uncertainty_reason=None)
        return httpx.Response(200, json={'choices': [{'finish_reason': 'stop',
            'message': {'content': json.dumps(output)}}]})
    llm = OpenAICompatibleLLM(base_url='https://fictional.invalid/v1', api_key='fictional-key',
        model='fictional-model', transport=httpx.MockTransport(respond))
    cid = uuid4()
    result = asyncio.run(AIOrchestrator(llm=llm).handle(request_id='semantic-fixture', conversation_id=cid, text=text))
    assert result.assistant_text != UNAVAILABLE and result.signal_mode == 'SEMANTIC'
    item, = result.signal_candidates
    assert item.source_message_id == uuid5(cid, 'semantic-fixture')
    assert item.type == 'PHYSICAL_DISCOMFORT' and len(calls) == 1
    assert text not in str(result.trace)
