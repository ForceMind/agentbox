"""Request limits, correlation IDs, and baseline response security headers."""

from __future__ import annotations

import json
import logging
import re
import secrets
from collections.abc import Awaitable, Callable

from agentbox_core.logging import log_event, request_id_context
from starlette.types import Message, Receive, Scope, Send

REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,63}$")
logger = logging.getLogger("agentbox.api.request")
SECURITY_HEADERS = (
    (b"x-content-type-options", b"nosniff"),
    (b"referrer-policy", b"no-referrer"),
    (b"x-frame-options", b"DENY"),
    (
        b"content-security-policy",
        b"default-src 'self'; base-uri 'none'; frame-ancestors 'none'; "
        b"form-action 'self'; object-src 'none'; script-src 'self'; style-src 'self'; "
        b"img-src 'self' data:; connect-src 'self'",
    ),
)


class ControlPlaneHttpMiddleware:
    """Bound request bodies before parsing and attach safe correlation headers."""

    def __init__(self, app: Callable[..., Awaitable[None]], max_body_bytes: int) -> None:
        self.app = app
        self.max_body_bytes = max_body_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = scope.get("headers", [])
        supplied_request_ids = [value for name, value in headers if name.lower() == b"x-request-id"]
        request_id = f"req_{secrets.token_hex(16)}"
        if supplied_request_ids:
            if len(supplied_request_ids) != 1:
                await self._error(send, 400, request_id, "REQUEST_ID_INVALID", "Invalid request ID")
                return
            try:
                candidate = supplied_request_ids[0].decode("ascii")
            except UnicodeDecodeError:
                candidate = ""
            if not REQUEST_ID_PATTERN.fullmatch(candidate):
                await self._error(send, 400, request_id, "REQUEST_ID_INVALID", "Invalid request ID")
                return
            request_id = candidate

        scope.setdefault("state", {})["request_id"] = request_id
        limited_receive = receive
        if scope.get("method") in {"POST", "PUT", "PATCH", "DELETE"}:
            content_lengths = [
                value for name, value in headers if name.lower() == b"content-length"
            ]
            if len(content_lengths) > 1:
                await self._error(
                    send,
                    400,
                    request_id,
                    "CONTENT_LENGTH_INVALID",
                    "Invalid Content-Length header",
                )
                return
            if content_lengths:
                try:
                    content_length = int(content_lengths[-1])
                except ValueError:
                    content_length = -1
                if content_length < 0 or content_length > self.max_body_bytes:
                    await self._error(
                        send,
                        413,
                        request_id,
                        "REQUEST_BODY_TOO_LARGE",
                        "Request body is too large",
                    )
                    return

            buffered: list[Message] = []
            total = 0
            while True:
                message = await receive()
                buffered.append(message)
                if message["type"] == "http.disconnect":
                    return
                total += len(message.get("body", b""))
                if total > self.max_body_bytes:
                    await self._error(
                        send,
                        413,
                        request_id,
                        "REQUEST_BODY_TOO_LARGE",
                        "Request body is too large",
                    )
                    return
                if not message.get("more_body", False):
                    break

            index = 0

            async def receive_buffered() -> Message:
                nonlocal index
                if index < len(buffered):
                    value = buffered[index]
                    index += 1
                    return value
                return await receive()

            limited_receive = receive_buffered

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                response_headers = list(message.get("headers", []))
                existing = {name.lower() for name, _value in response_headers}
                for name, value in SECURITY_HEADERS:
                    if name not in existing:
                        response_headers.append((name, value))
                if (
                    str(scope.get("path", "")).startswith("/api/")
                    and b"cache-control" not in existing
                ):
                    response_headers.append((b"cache-control", b"no-store"))
                response_headers.append((b"x-request-id", request_id.encode("ascii")))
                message["headers"] = response_headers
            await send(message)

        token = request_id_context.set(request_id)
        try:
            await self.app(scope, limited_receive, send_with_headers)
        finally:
            request_id_context.reset(token)
            log_event(
                logger,
                logging.INFO,
                "request_completed",
                "HTTP request completed",
                method=str(scope.get("method", ""))[:12],
                path=str(scope.get("path", ""))[:256],
            )

    async def _error(
        self,
        send: Send,
        status: int,
        request_id: str,
        code: str,
        message: str,
    ) -> None:
        body = json.dumps(
            {
                "api_version": "v1",
                "request_id": request_id,
                "error": {
                    "code": code,
                    "category": "validation",
                    "message": message,
                    "retryable": False,
                    "details": {},
                },
            },
            separators=(",", ":"),
        ).encode("utf-8")
        headers = [
            (b"content-type", b"application/json"),
            (b"content-length", str(len(body)).encode("ascii")),
            (b"cache-control", b"no-store"),
            (b"x-request-id", request_id.encode("ascii")),
            *SECURITY_HEADERS,
        ]
        await send({"type": "http.response.start", "status": status, "headers": headers})
        await send({"type": "http.response.body", "body": body})
