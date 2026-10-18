"""W6-03 bounded Mock candidates; no events, facts, diagnosis or notification."""
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
    """Deterministic fixture extractor routed through the same output validator."""
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
