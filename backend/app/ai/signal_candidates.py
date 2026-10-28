import json
import re
from typing import Literal
from uuid import UUID, uuid5

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.modules.safety.rules import evaluate


class SignalCandidate(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, frozen=True)
    candidate_id: UUID
    type: Literal['PHYSICAL_DISCOMFORT', 'EMOTION_EXPRESSION', 'IMPORTANT_MEMORY', 'MISS_FAMILY', 'SCAM_RISK', 'EMERGENCY']
    confidence: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    confidence_band: Literal['LOW', 'MEDIUM', 'HIGH']
    evidence_summary: str = Field(min_length=1, max_length=240)
    trigger_category: str = Field(min_length=1, max_length=64)
    recommended_action: str = Field(min_length=1, max_length=64)
    source_conversation_id: UUID
    source_message_id: UUID
    attributes: dict = Field(default_factory=dict, max_length=1)


class CandidateBatch(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    candidates: list[SignalCandidate] = Field(max_length=3)


class SemanticSignal(BaseModel):
    """Untrusted observations only; source, severity and actions are assigned by code."""
    model_config = ConfigDict(extra='forbid', strict=True)
    category: Literal['SELF_REPORTED_DISCOMFORT', 'EXPLICIT_MISS_FAMILY', 'EXPLICIT_CONTACT_REQUEST',
        'SAD_EXPRESSION', 'LONELY_EXPRESSION', 'HAPPY_EXPRESSION', 'WORRIED_EXPRESSION',
        'LIFE_STORY', 'PREFERENCE_OR_TABOO', 'PHOTO_BACKGROUND']
    evidence: str = Field(min_length=2, max_length=240)
    subject: Literal['SELF']
    assertion: Literal['AFFIRMED']


SEMANTIC_CATEGORIES = {
    'SELF_REPORTED_DISCOMFORT': ('PHYSICAL_DISCOMFORT', 'CHECK_IN_AND_OFFER_CONTACT', '老人提到身体不舒服，可提供联系家人或紧急帮助的入口。'),
    'EXPLICIT_MISS_FAMILY': ('MISS_FAMILY', 'OFFER_FAMILY_CONTACT', '老人表达了对家人的思念，可建议主动联系。'),
    'EXPLICIT_CONTACT_REQUEST': ('MISS_FAMILY', 'OFFER_FAMILY_CONTACT', '老人表达了联系家人的意愿。'),
    'LIFE_STORY': ('IMPORTANT_MEMORY', 'OFFER_MEMORY_REVIEW', '老人讲述了往事，可作为待核实的记忆候选。'),
    'PREFERENCE_OR_TABOO': ('IMPORTANT_MEMORY', 'OFFER_MEMORY_REVIEW', '老人提到了偏好，可作为待核实的记忆候选。'),
    'PHOTO_BACKGROUND': ('IMPORTANT_MEMORY', 'OFFER_MEMORY_REVIEW', '老人描述了照片背景，可作为待核实的记忆候选。'),
    **{category: ('EMOTION_EXPRESSION', 'OFFER_COMPANIONSHIP', '本次有情绪相关表达，仅为交流观察线索。')
       for category in ('SAD_EXPRESSION', 'LONELY_EXPRESSION', 'HAPPY_EXPRESSION', 'WORRIED_EXPRESSION')},
}

# Inspect the surrounding original sentence, so quoting only the positive part
# of a denial cannot turn it into an affirmed observation. Ambiguity is withheld.
_NON_ASSERTED = re.compile(r'[“”"「」『』]|假如|假设|如果|要是|比如|例如|举例|转述|引用|复述|'
    r'小说|故事里|电影|电视|新闻|听说|(?:他|她|别人|有人|邻居|朋友|医生|女儿|儿子)(?:昨天|今天|刚才)?(?:说|问)|'
    r'没(?:有)?说|并非|不是我|只是测试|是假的|开玩笑|已(?:经)?好(?:了|转)|以前.{0,12}现在|'
    r'(?:没有|没再|不再|并不|从未|从不|否认|没感到|没有感到).{0,12}(?:晕|疼|痛|不舒服|难过|孤单|孤独|寂寞|担心|思念|想念)|'
    r'(?:已经|现在).{0,6}(?:不.{0,2}晕|不疼|不痛|不难过|不孤单|没事)|'
    r'(?:请|帮我|给我).{0,12}(?:生成|提取|输出|标记).{0,12}(?:线索|候选|通知)|'
    r'(?:不想|不再想|没有想|没想).{0,8}(?:家人|女儿|儿子|孩子|闺女|联系|打电话)|'
    r'(?:不要|不必|不用|别).{0,8}(?:联系|打电话)|'
    r'(?:晕|疼|痛|不舒服|难过|孤单).{0,8}(?:没有了|不存在|不是真的)|'
    r'(?:他|她|女儿|儿子|老伴|邻居|朋友|孩子|妈妈|爸爸)(?:最近|今天|一直|有点|很|总)?(?:头晕|胸口|疼|难过|孤单)')


def extract_semantic(items, *, conversation_id, message_id, current_text):
    """Ground transient evidence in this turn; never persist the quoted text."""
    if len(items) > 3 or not isinstance(current_text, str) or not 0 < len(current_text) <= 2000:
        return ()
    result, seen = [], set()
    for item in items:
        try:
            item = SemanticSignal.model_validate(item)
        except (ValidationError, ValueError, TypeError):
            return ()
        evidence = item.evidence.strip()
        position = current_text.find(evidence)
        if position < 0 or current_text.find(evidence, position + 1) >= 0:
            continue
        boundaries = [m.end() for m in re.finditer(r'[。！？!?；;\n]', current_text)]
        start = max((n for n in boundaries if n <= position), default=0)
        end = min((n for n in boundaries if n >= position + len(evidence)), default=len(current_text))
        if _NON_ASSERTED.search(current_text[start:end]):
            continue
        if item.category in seen:
            continue
        seen.add(item.category)
        kind, action, summary = SEMANTIC_CATEGORIES[item.category]
        result.append(SignalCandidate(candidate_id=uuid5(message_id, kind + ':' + item.category),
            type=kind, confidence_band='MEDIUM', evidence_summary=summary,
            trigger_category=item.category, recommended_action=action,
            source_conversation_id=conversation_id, source_message_id=message_id,
            attributes={'semantic_evidence': evidence}))
    return tuple(result)


def revalidate_semantic(candidates, *, conversation_id, message_id, current_text):
    try:
        items = [dict(category=c.trigger_category, evidence=c.attributes.get('semantic_evidence'),
            subject='SELF', assertion='AFFIRMED') for c in candidates]
        expected = extract_semantic(items, conversation_id=conversation_id,
            message_id=message_id, current_text=current_text)
        return expected if tuple(candidates) == expected else ()
    except (AttributeError, TypeError, ValueError):
        return ()


def supported(text):
    """Finite fictional-demo phrase coverage, not general semantic accuracy."""
    safety = evaluate(text)
    if safety.kind == 'EMERGENCY':
        return [('EMERGENCY', 'EXPLICIT_HELP_REQUEST', 'OFFER_EMERGENCY_CONTACT', '本轮出现明确求助表达，可提供紧急联系入口。')]
    result = []
    if safety.kind == 'SCAM_RISK':
        result.append(('SCAM_RISK', safety.category, 'PAUSE_AND_VERIFY_WITH_FAMILY', '本轮交流出现需核实的敏感操作组合，请先联系家人核实。'))
    if re.fullmatch(r'我(?:今天)?(?:胸口(?:有点)?不舒服|头晕|觉得疼)[。！!\s]*', text):
        result.append(('PHYSICAL_DISCOMFORT', 'SELF_REPORTED_DISCOMFORT', 'CHECK_IN_AND_OFFER_CONTACT', '老人提到身体不舒服，可提供联系家人或紧急帮助的入口。'))
    if re.fullmatch(r'我(?:很)?想(?:女儿|儿子|家人|孩子)了[。！!\s]*', text):
        result.append(('MISS_FAMILY', 'EXPLICIT_MISS_FAMILY', 'OFFER_FAMILY_CONTACT', '老人表达了对家人的思念，可建议主动联系。'))
    if re.fullmatch(r'我想(?:联系|打电话给|和)(?:女儿|儿子|家人)(?:聊聊)?[。！!\s]*', text):
        result.append(('MISS_FAMILY', 'EXPLICIT_CONTACT_REQUEST', 'OFFER_FAMILY_CONTACT', '老人表达了联系家人的意愿。'))
    for phrase, category in [('难过', 'SAD_EXPRESSION'), ('孤单', 'LONELY_EXPRESSION'), ('高兴', 'HAPPY_EXPRESSION'), ('担心', 'WORRIED_EXPRESSION')]:
        if re.fullmatch(r'我(?:今天)?(?:有点|很)?' + phrase + r'[。！!\s]*', text):
            result.append(('EMOTION_EXPRESSION', category, 'OFFER_COMPANIONSHIP', '本次有情绪相关表达，仅为交流观察线索。'))
    if re.fullmatch(r'我年轻时在[^。！？!?]{1,20}工作[。！!\s]*', text):
        result.append(('IMPORTANT_MEMORY', 'LIFE_STORY', 'OFFER_MEMORY_REVIEW', '老人讲述了往事，可作为待核实的记忆候选。'))
    if re.fullmatch(r'我(?:喜欢|不喜欢)[^。！？!?]{1,30}[。！!\s]*', text):
        result.append(('IMPORTANT_MEMORY', 'PREFERENCE_OR_TABOO', 'OFFER_MEMORY_REVIEW', '老人提到了偏好，可作为待核实的记忆候选。'))
    if re.fullmatch(r'这张照片是[^。！？!?]{1,30}[。！!\s]*', text):
        result.append(('IMPORTANT_MEMORY', 'PHOTO_BACKGROUND', 'OFFER_MEMORY_REVIEW', '老人描述了照片背景，可作为待核实的记忆候选。'))
    return result[:3]


def extract_mock(text, *, conversation_id, message_id):
    try:
        rows = supported(text)
    except (ValueError, TypeError):
        return ()
    items = [dict(candidate_id=str(uuid5(message_id, kind + ':' + category)), type=kind,
        confidence_band='MEDIUM', evidence_summary=evidence, trigger_category=category, recommended_action=action,
        source_conversation_id=str(conversation_id), source_message_id=str(message_id), attributes={})
        for kind, category, action, evidence in rows]
    return validate_candidates(json.dumps({'candidates': items}), conversation_id=conversation_id,
        message_id=message_id, current_text=text)


def validate_candidates(raw: str, *, conversation_id: UUID, message_id: UUID, current_text: str) -> tuple[SignalCandidate, ...]:
    """Validate untrusted JSON without logging it; confidence grants no authority.

    Deterministic emergency evaluation remains independent of this function.
    """
    if not isinstance(raw, str) or len(raw) > 8192:
        return ()
    try:
        # Pydantic's JSON path accepts UUID strings while retaining strict types.
        batch = CandidateBatch.model_validate_json(raw)
        safety = evaluate(current_text)
        allowed = {(kind, category, action): evidence for kind, category, action, evidence in supported(current_text)}
    except (ValidationError, ValueError, TypeError):
        return ()
    result, seen = [], set()
    for candidate in batch.candidates:
        if candidate.source_conversation_id != conversation_id or candidate.source_message_id != message_id:
            return ()
        evidence = allowed.get((candidate.type, candidate.trigger_category, candidate.recommended_action))
        if evidence is None:
            return ()
        if candidate.type == 'SCAM_RISK':
            supplied = candidate.attributes.get('semantic_indicators', [])
            if (set(candidate.attributes) - {'semantic_indicators'} or not isinstance(supplied, list)
                    or any(not isinstance(item, str) or item not in safety.indicators for item in supplied)):
                return ()
        elif candidate.attributes:
            return ()
        key = (candidate.type, candidate.trigger_category)
        if key not in seen:
            seen.add(key)
            result.append(candidate.model_copy(update={'evidence_summary': evidence, 'attributes': {}}))
    return tuple(result)
