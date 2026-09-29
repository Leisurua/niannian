from uuid import uuid4

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.platform.logging import correlation_id_context, is_safe_identifier, request_id_context


class RequestIdMiddleware:
    """Propagates a bounded correlation id without logging sensitive headers."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers", []))
        supplied = headers.get(b"x-request-id", b"").decode("ascii", errors="ignore")
        request_id = supplied if is_safe_identifier(supplied) else str(uuid4())
        scope["state"] = {**scope.get("state", {}), "request_id": request_id}
        request_token = request_id_context.set(request_id)
        correlation_token = correlation_id_context.set(request_id)

        async def send_with_request_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                message["headers"] = [
                    *message.get("headers", []),
                    (b"x-request-id", request_id.encode("ascii")),
                ]
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        finally:
            correlation_id_context.reset(correlation_token)
            request_id_context.reset(request_token)
