"""Reviewed baseline combinations as versioned code (scam policy §§3-5/13).

Pure decisions only: callers must enforce actions/Consent. No event, notification
or call is created. SC-001 is included under approved W6-03.
"""
from dataclasses import dataclass
import re
import unicodedata


RULE_VERSION = '1.1.0'
WARNING = '存在风险，建议先联系家人核实。请不要转账、分享验证码或打开陌生链接。'
EMERGENCY_COPY = '如需紧急帮助，请立即联系身边的人或使用紧急联系入口。'

INDICATORS = {
    'TRANSFER': ('转账', '汇款', '打钱', '转钱'),
    'VERIFICATION_CODE': ('验证码', '短信码', '动态码'),
    'IMPERSONATION': ('冒充', '自称是我儿子', '自称是我女儿', '你是我儿子吗'),
    'SECRECY': ('不要告诉', '别告诉', '别让别人知道', '保密'),
    'UNKNOWN_LINK': ('陌生链接', '点击网址', '扫码'),
    'BANK_ACCOUNT': ('卡号', '账户', '开户', '收款账号', '银行卡'),
    'CREDENTIAL': ('密码', '登录口令', '身份证号'),
    'URGENT_PAYMENT': ('马上', '立刻', '现在付款', '逾期'),
}


@dataclass(frozen=True)
class Rule:
    rule_id: str
    category: str
    required: frozenset[str]
    severity: str


RULES = (
    Rule('SCAM_URGENT_TRANSFER', 'URGENT_TRANSFER_REQUEST', frozenset(('TRANSFER', 'BANK_ACCOUNT', 'URGENT_PAYMENT')), 'L3'),
    Rule('SCAM_TRANSFER_SECRECY', 'TRANSFER_AND_SECRECY', frozenset(('TRANSFER', 'SECRECY')), 'L2'),
    Rule('SCAM_CODE_SECRECY', 'VERIFICATION_CODE_AND_SECRECY', frozenset(('VERIFICATION_CODE', 'SECRECY')), 'L2'),
    Rule('SCAM_IMPERSONATION_PAYMENT', 'IMPERSONATION_URGENT_PAYMENT', frozenset(('IMPERSONATION', 'URGENT_PAYMENT')), 'L2'),
    Rule('SCAM_CREDENTIAL_REQUEST', 'CREDENTIAL_REQUEST', frozenset(('VERIFICATION_CODE', 'CREDENTIAL')), 'L2'),
    Rule('SCAM_LINK_PAYMENT', 'UNKNOWN_LINK_PAYMENT', frozenset(('UNKNOWN_LINK', 'URGENT_PAYMENT')), 'L2'),
)


@dataclass(frozen=True)
class SafetyDecision:
    kind: str
    rule_id: str | None
    category: str | None
    severity: str | None
    indicators: tuple[str, ...]
    blocked_actions: tuple[str, ...]
    message: str | None
    rule_version: str = RULE_VERSION


def evaluate(text: str) -> SafetyDecision:
    if not isinstance(text, str) or not text.strip() or len(text) > 2000:
        raise ValueError('Invalid safety input')
    normalized = unicodedata.normalize('NFKC', text)
    if any(word in normalized for word in ('救命', '帮我叫人', '我要联系急救')):
        return SafetyDecision('EMERGENCY', 'EMERGENCY_EXPLICIT', None, None, (), (), EMERGENCY_COPY)
    indicators = tuple(sorted(key for key, words in INDICATORS.items() if any(word in normalized for word in words)))
    if re.fullmatch(r'(?:验证码|短信码|动态码|密码)(?:和(?:验证码|短信码|动态码|密码))?'
            r'(?:是什么(?:东西|意思)?|什么意思)[？?。\s]*', normalized):
        return SafetyDecision('CLARIFY' if indicators else 'NONE', None, None, None, indicators, (), None)
    for rule in RULES:
        if rule.required.issubset(indicators):
            return SafetyDecision('SCAM_RISK', rule.rule_id, rule.category, rule.severity, indicators,
                ('TRANSFER', 'SHARE_CODE', 'SHARE_CREDENTIAL', 'OPEN_LINK'), WARNING)
    return SafetyDecision('CLARIFY' if indicators else 'NONE', None, None, None, indicators, (), None)
