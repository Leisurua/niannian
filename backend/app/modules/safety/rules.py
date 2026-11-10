"""Evaluate current-turn scam signals without granting action or notification authority."""
from dataclasses import dataclass
import re
import unicodedata


RULE_VERSION = '1.2.0'
WARNING = '存在风险，建议先联系家人核实。请不要转账、分享验证码或打开陌生链接。'
SCAM_ADVICE = '这条要求值得核实。请先暂停操作，用自己保存的号码联系家人或相关机构确认。'
ACTION_REFUSAL = '我不能替您转账、发送验证码或打开陌生链接。如果有人要求您这样做，请先联系家人核实。'
EMERGENCY_COPY = '如需紧急帮助，请立即联系身边的人或使用紧急联系入口。'
SENSITIVE_ACTIONS = ('TRANSFER', 'SHARE_CODE', 'SHARE_CREDENTIAL', 'OPEN_LINK')


def explicit_help(text: str) -> bool:
    """Whole commands only: quotations, negation and model candidates cannot send help."""
    normalized = unicodedata.normalize('NFKC', text).strip()
    return bool(re.fullmatch(r'(?:念念[，,、\s]*)?(?:请)?(?:现在)?'
        r'(?:我要(?:向家人)?求助|帮我叫人|帮我联系家人|我要联系急救|救命(?:[，,、\s]*帮我叫人)?)'
        r'[。！!\s]*', normalized))

INDICATORS = {
    'TRANSFER': ('转账', '汇款', '打钱', '转钱'),
    'VERIFICATION_CODE': ('验证码', '短信码', '动态码'),
    'IMPERSONATION': ('冒充', '假扮', '自称是我儿子', '自称是我女儿', '自称我儿子', '自称我女儿', '你是我儿子吗', '你是我女儿吗'),
    'SECRECY': ('不要告诉', '别告诉', '别让别人知道', '不要跟家里说', '别跟家里说', '保密'),
    'UNKNOWN_LINK': ('陌生链接', '点击网址', '扫码'),
    'BANK_ACCOUNT': ('卡号', '账户', '开户', '收款账号', '银行卡'),
    'CREDENTIAL': ('密码', '登录口令', '身份证号'),
    'URGENT_PAYMENT': ('马上', '立刻', '现在付款', '逾期'),
}

_SENTENCE_END = re.compile(r'[。！!；;\n]+')
_INCIDENT_BOUNDARY = re.compile(
    r'[。！!；;\n]+(?![。！!；;\n]|\s*(?:还|又|并且|而且|接着|随后|不要告诉|别告诉|别让别人知道))|'
    r'[,，](?=\s*(?:但|可是|不过|却))'
)
_NON_INCIDENT = re.compile(
    r'^(?:如果|假如|假设|要是|比如|例如|举例|遇到(?:有人)?(?:让|叫|要)你|'
    r'(?:(?:这(?:是|段|则|篇))|(?:我)?(?:在|刚才|刚|正在)?(?:看|看到|听|听到|读|写|做|参加|学习)(?:了)?'
    r'(?:一段|一则|一篇|一条)?)?(?:反诈|防诈(?:骗)?)(?:的)?(?:宣传|演练|知识|案例|课程|测试)|'
    r'(?:新闻|电视|电影|小说|故事)(?:里|上|中)|(?:我)?(?:听说|听到新闻|看到新闻)|'
    r'(?:也)?(?:没有人|没人|并没有人)(?:让|叫|要|要求|催)|'
    r'(?:对方|他|她|那个人)(?:并)?没(?:有)?(?:让|叫|要|要求|催))'
)
_PREVENTION_ADVICE = re.compile(r'^(?:(?:我)?(?:家人|儿子|女儿|社区|警方|警察)(?:提醒|告诉)(?:我|大家)?[：:，,\s]*)?'
    r'(?:请)?(?:千万)?(?:不要|别)(?:转账|汇款|打钱|转钱|付款|分享验证码|发验证码|打开陌生链接|点陌生链接)')
_DELEGATED_ACTION = re.compile(
    r'^(?:念念[，,、\s]*)?(?:你)?(?:能不能|可以|能|请)?(?:帮我|替我|代我)'
    r'(?:(?P<payment>转账|汇款|打钱|转钱|付款|支付)|(?:把|将)[^。！？；]{0,28}(?:转给|汇给|发给|转发|发送|告诉|分享|提供)|'
    r'(?:发|发送|转发|分享|告诉|提供)[^。！？；]{0,16}(?:验证码|密码|动态码|短信码)|'
    r'(?:点开|点击|打开|访问|扫描)[^。！？；]{0,20}(?:链接|网址|二维码|https?://))'
)
_DELEGATED_SENSITIVE = re.compile(r'验证码|密码|动态码|短信码|卡号|账户|银行卡|链接|网址|二维码|https?://|钱|元|款')
_REPORTED_REQUEST = re.compile(r'(?<!不)(?<!没)(?<!没有)(?:要求|命令|问|要|让|叫|催|逼|劝)我(?!不要|别|不用|不必)|'
    r'(?:找|向)我(?:要|索要)')
_SENSITIVE_REQUEST = re.compile(
    r'验证码|短信码|密码|卡号|银行卡|卡背面|[二三四五六七八九十2-9]位数字|账户|把钱|转钱|汇款|'
    r'收款码|屏幕共享|共享屏幕|远程控制|陌生链接|网址|扫码'
)
_HELP_WORDS = ('救命', '帮我叫人', '我要联系急救')


def _incident(text: str) -> str:
    text = text.strip(' \t，,：“”"「」')
    if _NON_INCIDENT.match(text) or _PREVENTION_ADVICE.match(text):
        return ''
    return text


def supports_scam_advice(text: str, evidence: str | None) -> bool:
    """Require a complete current sentence with a reported sensitive request."""
    if not evidence:
        return False
    quoted = evidence.strip().rstrip('。！!；;').strip()
    if not quoted:
        return False
    sentences = [s.strip() for s in _SENTENCE_END.split(text)]
    if sentences.count(quoted) != 1:
        return False
    sentence = _incident(unicodedata.normalize('NFKC', quoted))
    request = _REPORTED_REQUEST.search(sentence)
    return bool(request and _SENSITIVE_REQUEST.search(sentence, request.end()))


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
    Rule('SCAM_IMPERSONATION_SECRECY', 'IMPERSONATION_AND_SECRECY', frozenset(('IMPERSONATION', 'SECRECY')), 'L2'),
    Rule('SCAM_IMPERSONATION_CODE', 'IMPERSONATION_AND_VERIFICATION_CODE', frozenset(('IMPERSONATION', 'VERIFICATION_CODE')), 'L2'),
    Rule('SCAM_CREDENTIAL_REQUEST', 'CREDENTIAL_REQUEST', frozenset(('VERIFICATION_CODE', 'CREDENTIAL')), 'L2'),
    Rule('SCAM_LINK_PAYMENT', 'UNKNOWN_LINK_PAYMENT', frozenset(('UNKNOWN_LINK', 'URGENT_PAYMENT')), 'L2'),
    Rule('SCAM_LINK_CODE', 'UNKNOWN_LINK_AND_VERIFICATION_CODE', frozenset(('UNKNOWN_LINK', 'VERIFICATION_CODE')), 'L2'),
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
    emergency = SafetyDecision('EMERGENCY', 'EMERGENCY_EXPLICIT', None, None, (), (), EMERGENCY_COPY)
    if explicit_help(normalized) or normalized.lstrip().startswith(_HELP_WORDS):
        return emergency
        return SafetyDecision('EMERGENCY', 'EMERGENCY_EXPLICIT', None, None, (), (), EMERGENCY_COPY)
    incidents = (_incident(part) for part in _INCIDENT_BOUNDARY.split(normalized))
    contexts = [{key for key, words in INDICATORS.items() if any(word in incident for word in words)}
                for incident in incidents if incident]
    indicators = tuple(sorted(set().union(*contexts)))
    if re.fullmatch(r'(?:验证码|短信码|动态码|密码)(?:和(?:验证码|短信码|动态码|密码))?'
            r'(?:是什么(?:东西|意思)?|什么意思)[？?。\s]*', normalized):
        return SafetyDecision('CLARIFY', None, None, None, indicators, (), None)
    for rule in RULES:
        if any(rule.required <= context for context in contexts):
            return SafetyDecision('SCAM_RISK', rule.rule_id, rule.category, rule.severity, indicators, SENSITIVE_ACTIONS, WARNING)
    delegation = _DELEGATED_ACTION.match(normalized.strip())
    if delegation and (delegation['payment'] or _DELEGATED_SENSITIVE.search(delegation.group())):
        return SafetyDecision('REFUSE_ACTION', None, None, None, indicators, SENSITIVE_ACTIONS, ACTION_REFUSAL)
    if any(word in normalized for word in _HELP_WORDS):
        return emergency
    return SafetyDecision('CLARIFY' if indicators else 'NONE', None, None, None, indicators, (), None)
