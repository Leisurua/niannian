"""Explicitly enabled ntfy and Twilio transports; no automatic retry of external sends."""
import re
from dataclasses import dataclass

import httpx

MESSAGE = '念念 AI 提醒：有一条关注提示，请打开念念应用查看当前获授权的详情。'


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
        return 'mock'  # Signal extraction is still explicitly simulated.
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

    async def send(self, channel, destination):
        settings = self.settings
        if capabilities(settings)['channels'].get(channel) != 'AVAILABLE':
            raise DeliveryFailure('CHANNEL_NOT_CONFIGURED')
        if not destination:
            raise DeliveryFailure('CONTACT_REQUIRED')
        try:
            async with httpx.AsyncClient(timeout=5, follow_redirects=False, transport=self.transport) as client:
                if channel == 'PUSH':
                    response = await client.post(settings.ntfy_base_url.rstrip('/') + '/',
                        headers={'Authorization': 'Bearer ' + settings.push_api_key},
                        json={'topic': destination, 'title': '念念 AI', 'message': MESSAGE})
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
