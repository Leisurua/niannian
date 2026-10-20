from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.modules.conversation.service import scam_warning
from app.modules.safety.rules import WARNING


@pytest.mark.parametrize(('utterance', 'category'), [
    ('有人让我转账并且保密', 'TRANSFER_AND_SECRECY'),
    ('有人让我把验证码告诉他，还说别告诉孩子。', 'VERIFICATION_CODE_AND_SECRECY'),
    ('你是我儿子吗？马上给我转钱。', 'IMPERSONATION_URGENT_PAYMENT'),
    ('给我验证码和密码', 'CREDENTIAL_REQUEST'),
    ('点这个陌生链接就能领奖，马上付款。', 'UNKNOWN_LINK_PAYMENT'),
    ('马上转账到这个账户', 'URGENT_TRANSFER_REQUEST'),
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
])
def test_safe_or_other_signal_does_not_emit_scam_warning(utterance):
    row = SimpleNamespace(id=uuid4(), server_sequence=8)
    assert scam_warning(row, utterance) == []
    assert row.server_sequence == 8
