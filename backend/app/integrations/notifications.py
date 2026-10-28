"""Explicitly enabled ntfy and Twilio transports; no automatic retry of external sends."""
import re
import ssl
from dataclasses import dataclass
from uuid import UUID
from urllib.parse import urlsplit

import httpx

MESSAGE = '念念 AI 提醒：有一条关注提示，请打开念念应用查看当前获授权的详情。'


def notification_link(notification_id, recipient_id):
    return f'niannian-family://notification/{UUID(str(notification_id))}/{UUID(str(recipient_id))}'


def subscription_link(settings, topic):
    if (capabilities(settings)['channels']['PUSH'] != 'AVAILABLE'
            or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', topic)):
        return None
    server = urlsplit(settings.ntfy_base_url)
    if server.path not in ('', '/'):
        return None
    return f'ntfy://{server.netloc}/{topic}'


@dataclass(frozen=True)
class Receipt:
    provider: str
    message_id: str
    status: str


class DeliveryFailure(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def provider_name(settings, channel):
    if channel == 'IN_APP':
        return 'in_app'
    if channel == 'PUSH':
        return settings.notification_push_provider
    return 'twilio'


def capabilities(settings):
    enabled = settings.notification_external_enabled and settings.app_env == 'dev'
    twilio = enabled and all((settings.twilio_account_sid, settings.twilio_auth_token, settings.twilio_from_number))
    return dict(external_enabled=enabled, channels={
        'IN_APP': 'AVAILABLE',
        'PUSH': 'MOCK' if settings.notification_push_provider == 'mock' else (
            'AVAILABLE' if enabled and settings.ntfy_base_url and settings.push_api_key else 'DISABLED'),
        'SMS': 'AVAILABLE' if twilio else 'DISABLED', 'PHONE': 'AVAILABLE' if twilio else 'DISABLED'})


class ExternalNotifications:
    def __init__(self, settings, transport=None):
        self.settings, self.transport = settings, transport

    async def send(self, channel, destination, *, notification_id=None, recipient_id=None):
        settings = self.settings
        if capabilities(settings)['channels'].get(channel) != 'AVAILABLE':
            raise DeliveryFailure('CHANNEL_NOT_CONFIGURED')
        if not destination:
            raise DeliveryFailure('CONTACT_REQUIRED')
        verify = True
        if channel == 'PUSH' and settings.ntfy_ca_file:
            try:
                verify = ssl.create_default_context(cafile=settings.ntfy_ca_file)
            except (OSError, ssl.SSLError):
                raise DeliveryFailure('CHANNEL_NOT_CONFIGURED') from None
        try:
            async with httpx.AsyncClient(timeout=5, follow_redirects=False, transport=self.transport, verify=verify) as client:
                if channel == 'PUSH':
                    if not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', destination):
                        raise DeliveryFailure('INVALID_PUSH_TOPIC')
                    payload = {'topic': destination, 'title': '念念 AI', 'message': MESSAGE}
                    if notification_id is not None and recipient_id is not None:
                        payload['click'] = notification_link(notification_id, recipient_id)
                    response = await client.post(settings.ntfy_base_url.rstrip('/') + '/',
                        headers={'Authorization': 'Bearer ' + settings.push_api_key},
                        json=payload)
                    self.check(response)
                    identifier = response.json().get('id', '')
                    if not re.fullmatch(r'[A-Za-z0-9_-]{1,160}', identifier):
                        raise DeliveryFailure('DELIVERY_UNKNOWN')
                    return Receipt('ntfy', identifier, 'accepted')
                kind = 'Messages' if channel == 'SMS' else 'Calls'
                data = {'To': destination, 'From': settings.twilio_from_number}
                if channel == 'SMS':
                    data['Body'] = MESSAGE
                else:
                    data['Twiml'] = '<Response><Say language="zh-CN">' + MESSAGE + '</Say></Response>'
                    data['Timeout'] = '20'
                response = await client.post(self.url(kind), data=data,
                    auth=(settings.twilio_account_sid, settings.twilio_auth_token))
                self.check(response)
                value = response.json()
                identifier = value.get('sid', '')
                if not re.fullmatch(('SM' if channel == 'SMS' else 'CA') + r'[0-9a-fA-F]{32}', identifier):
                    raise DeliveryFailure('DELIVERY_UNKNOWN')
                status = value.get('status', 'queued')
                if status not in ('queued', 'accepted', 'sending', 'sent', 'delivered', 'failed', 'undelivered',
                        'scheduled', 'canceled', 'ringing', 'in-progress', 'completed', 'busy', 'no-answer'):
                    status = 'accepted'
                return Receipt('twilio', identifier, status)
        except DeliveryFailure:
            raise
        except Exception:
            # A timeout or lost reply does not prove the provider rejected the request.
            raise DeliveryFailure('DELIVERY_UNKNOWN') from None

    def url(self, kind, identifier=None):
        return ('https://api.twilio.com/2010-04-01/Accounts/' + self.settings.twilio_account_sid +
            '/' + kind + ('/' + identifier if identifier else '') + '.json')

    @staticmethod
    def check(response):
        if 400 <= response.status_code < 500:
            raise DeliveryFailure('PROVIDER_REJECTED')
        if not 200 <= response.status_code < 300:
            raise DeliveryFailure('DELIVERY_UNKNOWN')

    async def status(self, channel, identifier):
        if not re.fullmatch(r'(?:SM|CA)[0-9a-fA-F]{32}', identifier):
            raise DeliveryFailure('INVALID_RECEIPT')
        async with httpx.AsyncClient(timeout=5, follow_redirects=False, transport=self.transport) as client:
            response = await client.get(self.url('Messages' if channel == 'SMS' else 'Calls', identifier),
                auth=(self.settings.twilio_account_sid, self.settings.twilio_auth_token))
            self.check(response)
            value = response.json()
            if value.get('sid') != identifier or value.get('account_sid') != self.settings.twilio_account_sid:
                raise DeliveryFailure('INVALID_RECEIPT')
            return value['status']
