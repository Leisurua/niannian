import asyncio
from urllib.parse import parse_qs

import httpx
import pytest
from pydantic import ValidationError

from app.integrations.notifications import DeliveryFailure, ExternalNotifications, MESSAGE, capabilities
from app.platform.config import Settings


def settings(**kwargs):
    return Settings(app_env='dev', notification_external_enabled=True, notification_push_provider='ntfy',
        ntfy_base_url='https://ntfy.example.invalid', push_api_key='fictional-token',
        twilio_account_sid='AC' + 'a' * 32, twilio_auth_token='fictional-token', twilio_from_number='+12025550100', **kwargs)


def test_external_off_by_default_and_demo_cannot_enable():
    assert capabilities(Settings())['channels']['SMS'] == 'DISABLED'
    for environment in ('demo', 'test'):
        with pytest.raises(ValidationError):
            Settings(app_env=environment, demo_data=True, notification_external_enabled=True)
    for url in ('http://host', 'https://user:pass@host', 'https://host?secret=x'):
        with pytest.raises(ValidationError):
            Settings(ntfy_base_url=url)


@pytest.mark.parametrize('channel', ['PUSH', 'SMS', 'PHONE'])
def test_real_requests_are_minimal_and_only_provider_acceptance(channel):
    requests = []
    def handle(request):
        requests.append(request)
        if channel == 'PUSH':
            import json
            body = json.loads(request.content)
            assert body == {'topic': 'fictional-private-topic', 'title': '念念 AI', 'message': MESSAGE}
            assert request.headers['authorization'] == 'Bearer fictional-token'
            return httpx.Response(200, json={'id': 'accepted123'})
        body = parse_qs(request.content.decode())
        assert body['To'] == ['+12025550101']
        assert 'signal_event_id' not in body
        assert (body.get('Body', [''])[0] == MESSAGE) if channel == 'SMS' else '<Say language="zh-CN">' in body['Twiml'][0]
        return httpx.Response(201, json={'sid': ('SM' if channel == 'SMS' else 'CA') + 'b' * 32, 'status': 'queued'})
    result = asyncio.run(ExternalNotifications(settings(), httpx.MockTransport(handle)).send(channel,
        'fictional-private-topic' if channel == 'PUSH' else '+12025550101'))
    assert result.status in ('queued', 'accepted') and len(requests) == 1


def test_disabled_transport_and_uncertain_timeout_never_retry():
    calls = []
    def handle(request):
        calls.append(request)
        raise httpx.ReadTimeout('private-number-must-not-escape')
    provider = ExternalNotifications(Settings(), httpx.MockTransport(handle))
    with pytest.raises(DeliveryFailure, match='CHANNEL_NOT_CONFIGURED'):
        asyncio.run(provider.send('SMS', '+12025550101'))
    assert not calls
    provider = ExternalNotifications(settings(), httpx.MockTransport(handle))
    with pytest.raises(DeliveryFailure) as error:
        asyncio.run(provider.send('PHONE', '+12025550101'))
    assert str(error.value) == 'DELIVERY_UNKNOWN' and len(calls) == 1


def test_receipt_polling_checks_account_and_resource_identity():
    sid = 'CA' + 'b' * 32
    def handle(request):
        assert request.method == 'GET' and request.url.path.endswith('/Calls/' + sid + '.json')
        return httpx.Response(200, json={'sid': sid, 'account_sid': 'AC' + 'a' * 32, 'status': 'completed'})
    provider = ExternalNotifications(settings(), httpx.MockTransport(handle))
    assert asyncio.run(provider.status('PHONE', sid)) == 'completed'


@pytest.mark.parametrize(('channel', 'receipt', 'expected'), [
    ('SMS', 'delivered', 'DELIVERED'), ('SMS', 'undelivered', 'FAILED'),
    ('PHONE', 'completed', 'SENT'), ('PHONE', 'busy', 'FAILED')])
def test_terminal_receipt_at_acceptance_is_applied_without_waiting_for_poll(channel, receipt, expected):
    from types import SimpleNamespace
    from app.modules.notification.service import apply_receipt
    row = SimpleNamespace(channel=channel, status='SENT', delivered_at=None, error_code=None)
    apply_receipt(row, receipt)
    assert row.status == expected
    assert bool(row.delivered_at) == (expected == 'DELIVERED')


def test_push_click_contains_only_notification_and_recipient_ids():
    import json
    from uuid import uuid4
    from app.integrations.notifications import notification_link
    notice, recipient = uuid4(), uuid4()
    def handle(request):
        body = json.loads(request.content)
        assert body['click'] == notification_link(notice, recipient)
        assert body['click'] == f'niannian-family://notification/{notice}/{recipient}'
        assert set(body) == {'topic', 'title', 'message', 'click'}
        assert 'fictional-token' not in str(body)
        return httpx.Response(200, json={'id': 'accepted123'})
    asyncio.run(ExternalNotifications(settings(), httpx.MockTransport(handle)).send('PUSH', 'fictional-private-topic',
        notification_id=notice, recipient_id=recipient))


def test_subscription_route_requires_configured_private_service_and_valid_topic():
    from app.integrations.notifications import subscription_link
    from app.modules.notification.contacts import ContactInput
    configured = settings()
    assert subscription_link(configured, 'fictional-topic') == 'ntfy://ntfy.example.invalid/fictional-topic'
    assert subscription_link(Settings(), 'fictional-topic') is None
    for topic in ('', 'a/b', 'topic?token=x', 'x' * 65):
        assert subscription_link(configured, topic) is None
    with pytest.raises(ValidationError):
        ContactInput(ntfy_topic='x' * 65)
    assert subscription_link(configured.model_copy(update={'ntfy_base_url': 'https://ntfy.example.invalid/prefix'}), 'topic') is None


def test_invalid_private_ca_does_not_disable_tls_or_send(tmp_path):
    certificate = tmp_path / 'invalid.crt'
    certificate.write_text('not a certificate')
    def unexpected(request):
        pytest.fail('An invalid CA must fail before contacting the push server')
    provider = ExternalNotifications(settings(ntfy_ca_file=str(certificate)), httpx.MockTransport(unexpected))
    with pytest.raises(DeliveryFailure, match='CHANNEL_NOT_CONFIGURED'):
        asyncio.run(provider.send('PUSH', 'fictional-private-topic'))
