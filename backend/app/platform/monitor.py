"""Independent operational probes and private ntfy alerts, without account data."""
import argparse
import asyncio
from collections import deque
import json
import logging
import math
import os
from pathlib import Path
import ssl
import time
from urllib.parse import urlsplit

import httpx
from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.platform.logging import configure_logging, log_event

LOGGER = logging.getLogger('nianian.runtime')
CODES = ('API_UNREACHABLE', 'DATABASE_UNAVAILABLE', 'MIGRATIONS_UNREADY', 'STORAGE_UNAVAILABLE',
         'WORKER_UNAVAILABLE', 'TASKS_UNAVAILABLE', 'DEAD_TASKS', 'TASK_BACKLOG',
         'METRICS_UNAVAILABLE', 'HTTP_ERRORS', 'HTTP_LATENCY')


class MonitorSettings(BaseSettings):
    api_url: str = 'http://127.0.0.1:8000'
    ntfy_url: str
    ntfy_token_file: Path
    ca_file: str = ''
    state_file: Path = Path('/srv/niannian/monitor/state.json')
    poll_seconds: float = Field(default=30, ge=1, le=300)
    failure_samples: int = Field(default=3, ge=1, le=60)
    recovery_samples: int = Field(default=2, ge=1, le=60)
    repeat_seconds: int = Field(default=3600, ge=60, le=86400)
    retry_seconds: int = Field(default=60, ge=1, le=3600)
    backlog_threshold: int = Field(default=100, ge=1)
    rate_window_seconds: int = Field(default=300, ge=30, le=3600)
    min_requests: int = Field(default=20, ge=1)
    error_rate: float = Field(default=0.05, gt=0, le=1)
    mean_latency_seconds: float = Field(default=3, gt=0)
    model_config = SettingsConfigDict(env_prefix='OPS_', extra='ignore', hide_input_in_errors=True)

    @model_validator(mode='after')
    def endpoints(self):
        for value, schemes in ((self.api_url, ('http', 'https')), (self.ntfy_url, ('https',))):
            url = urlsplit(value)
            if url.scheme not in schemes or not url.hostname or url.username or url.password or url.query or url.fragment:
                raise ValueError('Use an explicit service URL without credentials or query')
        if not urlsplit(self.ntfy_url).path.strip('/'):
            raise ValueError('A private operations topic is required')
        return self


async def bounded_get(client, url):
    async with client.stream('GET', url) as response:
        if response.status_code not in (200, 503):
            raise ValueError('Probe failed')
        data = bytearray()
        async for chunk in response.aiter_bytes():
            data.extend(chunk)
            if len(data) > 65536:
                raise ValueError('Probe too large')
        return response.status_code, bytes(data)


def counters(data):
    names = ('nianian_http_requests_total', 'nianian_http_errors_total',
             'nianian_http_request_duration_seconds_sum')
    values = {}
    for line in data.decode('utf-8').splitlines():
        fields = line.split()
        if len(fields) == 2 and fields[0] in names:
            value = float(fields[1])
            if not math.isfinite(value) or value < 0 or fields[0] in values:
                raise ValueError('Invalid counter')
            values[fields[0]] = value
    result = tuple(values[name] for name in names)
    if result[1] > result[0]:
        raise ValueError('Invalid error count')
    return result


class RateWindow:
    def __init__(self):
        self.samples = deque()

    def observe(self, values, now, settings):
        if self.samples and (now < self.samples[-1][0] or any(a < b for a, b in zip(values, self.samples[-1][1]))):
            self.samples.clear()  # API restart or clock change; warm up again.
        self.samples.append((now, values))
        while len(self.samples) > 1 and self.samples[1][0] <= now - settings.rate_window_seconds:
            self.samples.popleft()
        count, errors, duration = (a - b for a, b in zip(values, self.samples[0][1]))
        if count < settings.min_requests:
            return {'HTTP_ERRORS': None, 'HTTP_LATENCY': None}
        return {'HTTP_ERRORS': errors / count >= settings.error_rate,
                'HTTP_LATENCY': duration / count >= settings.mean_latency_seconds}


async def probe(client, settings, window, now):
    result = dict.fromkeys(CODES)
    try:
        _, raw = await bounded_get(client, settings.api_url.rstrip('/') + '/health/ready')
        components = json.loads(raw)['components']
        if components['api']['status'] != 'ok':
            raise ValueError('API probe invalid')
        result['API_UNREACHABLE'] = False
        for component, code in (('database', 'DATABASE_UNAVAILABLE'), ('migrations', 'MIGRATIONS_UNREADY'),
                                ('storage', 'STORAGE_UNAVAILABLE'), ('worker', 'WORKER_UNAVAILABLE')):
            status = components[component]['status']
            # Do not report dependent probes as recovered while their DB is unknown.
            result[code] = None if status == 'unknown' else status != 'ok'
        tasks = components['tasks']
        result['TASKS_UNAVAILABLE'] = tasks['status'] == 'unknown'
        if tasks['status'] != 'unknown':
            result['DEAD_TASKS'] = tasks['dead'] > 0
            result['TASK_BACKLOG'] = sum(tasks[name] for name in ('pending', 'running', 'retry')) >= settings.backlog_threshold
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        result['API_UNREACHABLE'] = True
    try:
        status, raw = await bounded_get(client, settings.api_url.rstrip('/') + '/metrics')
        if status != 200:
            raise ValueError('Metrics probe failed')
        result.update(window.observe(counters(raw), now, settings))
        result['METRICS_UNAVAILABLE'] = False
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        window.samples.clear()
        result['METRICS_UNAVAILABLE'] = None if result['API_UNREACHABLE'] else True
    return result


def load_state(path):
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(data, dict) or set(data) - set(CODES):
        raise ValueError('Invalid monitor state')
    for value in data.values():
        if (not isinstance(value, dict) or type(value.get('active')) is not bool
                or any(type(value.get(key)) not in (int, float) or not math.isfinite(value[key]) or value[key] < 0
                       for key in ('bad', 'good', 'last_sent', 'last_attempt'))):
            raise ValueError('Invalid monitor state')
    return data


def save_state(path, state):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    try:
        with temporary.open('w', encoding='utf-8') as output:
            json.dump(state, output)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


class AlertMonitor:
    def __init__(self, settings, state=None):
        self.settings, self.state = settings, state if state is not None else {}

    async def update(self, conditions, now, send):
        for code in CODES:
            row = self.state.setdefault(code, dict(active=False, bad=0, good=0, last_sent=0, last_attempt=0))
            bad = conditions.get(code)
            if bad is None:
                row['bad'] = row['good'] = 0
                continue
            row['bad'] = min(row['bad'] + 1, self.settings.failure_samples) if bad else 0
            row['good'] = min(row['good'] + 1, self.settings.recovery_samples) if not bad else 0
            firing = bad and row['bad'] >= self.settings.failure_samples and (
                not row['active'] or now - row['last_sent'] >= self.settings.repeat_seconds)
            recovery = not bad and row['active'] and row['good'] >= self.settings.recovery_samples
            if not (firing or recovery) or (row['last_attempt'] and now - row['last_attempt'] < self.settings.retry_seconds):
                continue
            row['last_attempt'] = now
            if await send(code, 'FIRING' if firing else 'RECOVERED'):
                row['active'], row['last_sent'] = bool(firing), now


async def publish(client, settings, token, code, status):
    try:
        async with client.stream('POST', settings.ntfy_url, headers={
                'Authorization': 'Bearer ' + token, 'Title': 'NianNian operations',
                'Priority': '4' if status == 'FIRING' else '3'},
                content=f'NianNian {status}: {code}. Check the private service logs and readiness probes.'.encode()) as response:
            if response.status_code != 200:
                raise ValueError('Publish rejected')
            data = bytearray()
            async for chunk in response.aiter_bytes():
                data.extend(chunk)
                if len(data) > 8192:
                    raise ValueError('Publish response too large')
            identifier = json.loads(data)['id']
            if not isinstance(identifier, str) or not 1 <= len(identifier) <= 128:
                raise ValueError('Publish not confirmed')
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        log_event(LOGGER, logging.ERROR, 'OPS_ALERT_SEND_FAILED', error_code=code)
        return False
    log_event(LOGGER, logging.INFO, 'OPS_ALERT_PUBLISHED', error_code=code, result=status)
    return True


async def run(settings, once=False):
    token = settings.ntfy_token_file.read_text(encoding='utf-8').strip()
    if not token or len(token) > 4096 or not token.isascii() or any(c.isspace() for c in token):
        raise ValueError('Invalid operations token')
    monitor = AlertMonitor(settings, load_state(settings.state_file))
    verify = ssl.create_default_context(cafile=settings.ca_file or None)
    async with httpx.AsyncClient(timeout=8, verify=verify, follow_redirects=False, trust_env=False) as client:
        window = RateWindow()
        while True:
            now = time.time()
            conditions = await probe(client, settings, window, now)
            await monitor.update(conditions, now, lambda code, status: publish(client, settings, token, code, status))
            save_state(settings.state_file, monitor.state)
            if once:
                return
            await asyncio.sleep(settings.poll_seconds)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--once', action='store_true')
    args = parser.parse_args()
    configure_logging('INFO')
    try:
        asyncio.run(run(MonitorSettings(), args.once))
    except KeyboardInterrupt:
        pass
    except Exception:
        log_event(LOGGER, logging.ERROR, 'OPS_MONITOR_FAILED', error_code='MONITOR_CONFIG_OR_STATE_UNAVAILABLE')
        raise SystemExit(1) from None


if __name__ == '__main__':
    main()
