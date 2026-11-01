"""Local, bounded topic classification. User text and vectors are never retained."""
import asyncio
from collections import OrderedDict
from dataclasses import dataclass
import math
import re

from app.integrations.contracts import EmbeddingRequest, ProviderError
from app.integrations.embedding import configured_embedding, validate_result

TOPICS = {
    'DUMPLINGS': ('包饺子', ('包饺子', '做饺子', '饺子馅')),
    'GARDENING': ('种花种菜', ('种花', '养花', '浇花', '种菜', '园艺')),
    'COOKING': ('做饭', ('做饭', '烧菜', '炒菜', '下厨', '烹饪')),
    'WALKING': ('散步', ('散步', '遛弯', '走走')),
    'WORK_STORY': ('工作往事', ('以前上班', '在工厂', '工作的时候', '当年工作')),
    'SCHOOL_STORY': ('求学往事', ('上学时', '读书时', '同窗', '求学')),
    'FAMILY_VISIT': ('家人团聚', ('团圆', '团聚', '来看我', '回家过年', '回家探亲')),
}
EXAMPLES = {
    'DUMPLINGS': ('我和面擀皮，把馅料捏进面皮包成水饺。', '我准备肉馅和面皮，和家人一起包饺子。', '我在厨房捏水饺，包好以后下锅煮。'),
    'GARDENING': ('我给阳台的盆栽松土施肥，照料花草。', '我在院里栽种蔬菜，每天给菜苗浇水。', '我喜欢种花养花，照顾植物。'),
    'COOKING': ('我准备食材做午饭，炒几个家常菜。', '我在厨房煮饭烧菜，准备一家人的饭菜。', '我喜欢研究菜谱，做各种美食。'),
    'WALKING': ('我沿着河边慢慢步行，活动一下身体。', '我饭后去公园散步遛弯，走一圈。', '我到外面步行活动，舒展身体。'),
    'WORK_STORY': ('我回忆以前在单位工作的经历。', '我讲年轻时上班、同事和厂里的往事。', '我想起退休前在岗位上做事的日子。'),
    'SCHOOL_STORY': ('我回忆学生时代，老师和同学的往事。', '我想起当年在课堂读书学习的日子。', '我讲求学时和同窗一起学习的经历。'),
    'FAMILY_VISIT': ('我的孩子回家探望我，一家人见面团聚。', '我和儿孙过节团圆，一家人聚在一起。', '我盼着亲人来家里，一起吃团圆饭。'),
}
_BLOCKED = re.compile(r'如果|假如|假设|要是|听说|据说|转述|引用|比如|例如|开玩笑|测试|说|问|[？?吗]')
_DENIED = re.compile(r'不|没|别|未曾|从未|并非|不是')
_OTHER_SUBJECT = re.compile(r'^(?:我(?:的)?)?(?:他|她|他们|她们|女儿|儿子|孩子|孙子|孙女|邻居|朋友|老伴|医生|妈妈|爸爸)')
_ANCHORS = OrderedDict()


def affirmed_parts(text):
    # Withhold quoted or ambiguous utterances rather than leaking quoted clauses.
    if not isinstance(text, str) or any(mark in text for mark in ('"', '“', '”', '「', '」', '『', '』', '‘', '’')):
        return ()
    result = []
    for sentence in re.findall(r'[^。！？!?；;\n]+[。！？!?；;\n]?', text):
        if _BLOCKED.search(sentence):
            continue
        for clause in re.split(r'[，,]', sentence):
            clause = clause.strip(' 。！!；;\n')
            self_context = not _OTHER_SUBJECT.search(clause) or any(
                phrase in clause for phrase in ('来看我', '陪我', '和我', '跟我', '到我家', '我们'))
            if 2 <= len(clause) <= 240 and not _DENIED.search(clause) and self_context:
                result.append(clause)
    return tuple(result[:8])


def rule_topics(parts):
    result = set()
    for part in parts:
        matches = {code for code, (_, words) in TOPICS.items() if any(word in part for word in words)}
        if 'DUMPLINGS' in matches:
            matches.discard('COOKING')
        result.update(matches)
    return sorted(result)


def cosine(a, b):
    return sum(x * y for x, y in zip(a, b)) / math.sqrt(sum(x * x for x in a) * sum(x * x for x in b))


@dataclass(frozen=True)
class TopicResult:
    topics: tuple[str, ...]
    method: str = 'RULE'
    model_version: str | None = None


async def classify_topics(text, settings):
    parts = affirmed_parts(text)
    rules = set(rule_topics(parts))
    if settings.embedding_provider != 'local' or not parts:
        return TopicResult(tuple(sorted(rules)))
    # Only classify phrases without a direct match; avoid adding a vague parent
    # category to an already specific topic such as dumplings versus cooking.
    phrases = [part for part in parts if not rule_topics((part,))]
    if not phrases:
        return TopicResult(tuple(sorted(rules)))
    try:
        async with asyncio.timeout(settings.embedding_timeout_seconds):
            provider = configured_embedding(settings)
            caps = provider.capabilities()
            if caps.provider != 'local' or not caps.offline:
                raise ValueError('Local offline inference required')
            key = (caps.model, caps.version)
            anchors = _ANCHORS.get(key)
            examples = [sample for values in EXAMPLES.values() for sample in values]
            texts = phrases if anchors is not None else examples + phrases
            result = await provider.embed(EmbeddingRequest(request_id='report-topics', texts=texts, purpose='document'))
            result = validate_result(result, provider, len(texts))
            if anchors is None:
                anchors = tuple(tuple(v) for v in result.vectors[:len(examples)])
                _ANCHORS[key] = anchors
                if len(_ANCHORS) > 4:
                    _ANCHORS.popitem(last=False)
            vectors = result.vectors[-len(phrases):]
        codes = [code for code, values in EXAMPLES.items() for _ in values]
        for vector in vectors:
            scores = {code: max(cosine(vector, anchor) for label, anchor in zip(codes, anchors) if label == code)
                for code in TOPICS}
            ranked = sorted(scores, key=scores.get, reverse=True)
            if scores[ranked[0]] >= 0.67 and scores[ranked[0]] - scores[ranked[1]] >= 0.035:
                rules.add(ranked[0])
        return TopicResult(tuple(sorted(rules)), 'LOCAL_SEMANTIC', caps.version)
    except (TimeoutError, OSError, ValueError, RuntimeError, ProviderError):
        return TopicResult(tuple(sorted(rules)), 'RULE_FALLBACK')
