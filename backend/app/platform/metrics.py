"""Small process-local HTTP metrics without request labels or user data."""

from threading import Lock
from time import perf_counter

from starlette.types import ASGIApp, Message, Receive, Scope, Send


class RequestMetrics:
    def __init__(self):
        self._lock = Lock()
        self._requests = 0
        self._errors = 0
        self._duration_sum = 0.0
        self._duration_max = 0.0

    def observe(self, status, duration):
        with self._lock:
            self._requests += 1
            self._errors += int(status >= 500)
            self._duration_sum += duration
            self._duration_max = max(self._duration_max, duration)

    def snapshot(self):
        with self._lock:
            return dict(requests=self._requests, errors=self._errors,
                        duration_sum=self._duration_sum, duration_max=self._duration_max)


class RequestMetricsMiddleware:
    def __init__(self, app: ASGIApp, metrics: RequestMetrics):
        self.app, self.metrics = app, metrics

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope['type'] != 'http':
            await self.app(scope, receive, send)
            return
        started, status = perf_counter(), 500

        async def capture(message: Message):
            nonlocal status
            if message['type'] == 'http.response.start':
                status = message['status']
            await send(message)

        try:
            await self.app(scope, receive, capture)
        finally:
            self.metrics.observe(status, perf_counter() - started)


def exposition(snapshot, ready, components):
    lines = [
        '# HELP niannian_http_requests_total HTTP requests handled by this API process.',
        '# TYPE niannian_http_requests_total counter',
        f"nianian_http_requests_total {snapshot['requests']}",
        '# HELP niannian_http_errors_total HTTP responses with a 5xx status.',
        '# TYPE niannian_http_errors_total counter',
        f"nianian_http_errors_total {snapshot['errors']}",
        '# HELP niannian_http_request_duration_seconds Request duration summary.',
        '# TYPE niannian_http_request_duration_seconds summary',
        f"nianian_http_request_duration_seconds_count {snapshot['requests']}",
        f"nianian_http_request_duration_seconds_sum {snapshot['duration_sum']:.6f}",
        '# HELP niannian_http_request_duration_seconds_max Longest request observed by this process.',
        '# TYPE niannian_http_request_duration_seconds_max gauge',
        f"nianian_http_request_duration_seconds_max {snapshot['duration_max']:.6f}",
        '# HELP niannian_ready Whether all readiness dependencies are healthy.',
        '# TYPE niannian_ready gauge',
        f'nianian_ready {int(ready)}',
        '# HELP niannian_dependency_ready Readiness of an individual dependency.',
        '# TYPE niannian_dependency_ready gauge',
    ]
    for name in ('api', 'database', 'migrations', 'storage', 'worker'):
        lines.append(f'nianian_dependency_ready{{component="{name}"}} '
                     f'{int(components[name]["status"] == "ok")}')
    worker = components.get('worker', {})
    if 'age_seconds' in worker:
        lines.extend(('# HELP niannian_worker_heartbeat_age_seconds Age of the durable worker heartbeat.',
                      '# TYPE niannian_worker_heartbeat_age_seconds gauge',
                      f'niannian_worker_heartbeat_age_seconds {worker["age_seconds"]}'))
    tasks = components.get('tasks', {})
    lines.extend(('# HELP niannian_task_outbox Tasks not yet successfully completed.',
                  '# TYPE niannian_task_outbox gauge'))
    for status in ('pending', 'running', 'retry', 'dead'):
        if status in tasks:
            lines.append(f'nianian_task_outbox{{status="{status}"}} {tasks[status]}')
    return '\n'.join(lines) + '\n'
