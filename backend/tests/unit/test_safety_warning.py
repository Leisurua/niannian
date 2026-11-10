from types import SimpleNamespace
from uuid import uuid4

import pytest
from app.modules.conversation.service import scam_warning
from app.modules.safety.rules import WARNING
from app.modules.safety.rules import explicit_help


@pytest.mark.parametrize('text', ['我要向家人求助', '我要联系急救', '救命，帮我叫人。', '念念，请帮我叫人！', '帮我联系家人'])
def test_explicit_help_commands(text):
    assert explicit_help(text)


@pytest.mark.parametrize('text', ['不要帮我叫人', '我刚才说了救命', '他说“帮我叫人”', '如果我要向家人求助怎么办？',
    '救命是什么意思', '我胸口有点不舒服', '我想女儿了', '我要向家人求助吗？'])
def test_non_commands_never_send_help(text):
    assert not explicit_help(text)


@pytest.mark.parametrize(('utterance', 'category'), [
    ('有人让我转账并且保密', 'TRANSFER_AND_SECRECY'),
    ('有人让我把验证码告诉他，还说别告诉孩子。', 'VERIFICATION_CODE_AND_SECRECY'),
    ('你是我儿子吗？马上给我转钱。', 'IMPERSONATION_URGENT_PAYMENT'),
    ('给我验证码和密码', 'CREDENTIAL_REQUEST'),
    ('点这个陌生链接就能领奖，马上付款。', 'UNKNOWN_LINK_PAYMENT'),
    ('马上转账到这个账户', 'URGENT_TRANSFER_REQUEST'),
    ('有人冒充我女儿。还让我保密。', 'IMPERSONATION_AND_SECRECY'),
    ('对方叫我汇款。别告诉家人。', 'TRANSFER_AND_SECRECY'),
    ('有人冒充我女儿说救命，还让我保密。', 'IMPERSONATION_AND_SECRECY'),
    ('有人自称我儿子，问我要验证码。', 'IMPERSONATION_AND_VERIFICATION_CODE'),
    ('对方让我打开陌生链接填写验证码。', 'UNKNOWN_LINK_AND_VERIFICATION_CODE'),
    ('我刚看了一段反诈宣传，但现在有人让我转账，还说别告诉孩子。', 'TRANSFER_AND_SECRECY'),
])
def test_warning_is_minimal_fixed_copy_with_monotonic_sequence(utterance, category):
    row = SimpleNamespace(id=uuid4(), server_sequence=8)
    result = scam_warning(row, utterance)
    assert len(result) == 1
    assert result[0]['type'] == 'warning'
    assert result[0]['conversation_id'] == str(row.id)
    assert result[0]['sequence'] == row.server_sequence == 9
    assert result[0]['payload'] == {'reason_category': category, 'display_text': WARNING}
    assert utterance not in str(result)
    assert 'signal_event_id' not in str(result)
    assert '已通知' not in str(result) and '已接通' not in str(result)


@pytest.mark.parametrize('utterance', [
    '我今天给自己的另一个账户转钱。', '验证码是什么东西？',
    '我想女儿了。', '我年轻时在杭州工作。', '我胸口有点不舒服。',
    '救命，帮我叫人。', '救命，有人让我转账并且保密',
    '这是防诈骗宣传，遇到让你转账并保密的人要小心。',
    '家人提醒我不要转账，也不要告诉陌生人验证码。',
    '社区提醒：千万不要转账，也不要告诉陌生人验证码。',
    '没人让我转账，也没人让我保密。',
    '我今天给自己转账了。朋友让我帮他保密生日惊喜。',
    '念念，请帮我转账。',
])
def test_safe_or_other_signal_does_not_emit_scam_warning(utterance):
    row = SimpleNamespace(id=uuid4(), server_sequence=8)
    assert scam_warning(row, utterance) == []
    assert row.server_sequence == 8
