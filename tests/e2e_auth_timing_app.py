"""Opt-in, bounded numeric observations around the unchanged synthetic E2E API.

No arguments, SQL parameters, exception messages, headers, bodies, URLs or real
request IDs are retained. This module is never imported by the production app.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator, Callable
from concurrent.futures import Executor
from contextlib import asynccontextmanager, suppress
from contextvars import ContextVar
from threading import Lock
from time import perf_counter
from typing import Any, TypeVar

from agentbox_api.auth import BoundedLoginExecutor
from agentbox_core.security import PasswordManager
from agentbox_core.services import IssuedSession
from fastapi import FastAPI
from sqlalchemy import Connection, event
from sqlalchemy.engine import ExceptionContext
from starlette.responses import JSONResponse
from starlette.types import Message, Receive, Scope, Send

if (
    os.environ.get("AGENTBOX_ENV") != "test"
    or os.environ.get("AGENTBOX_E2E_AUTH_TIMING") != "1"
    or os.environ.get("AGENTBOX_BIND_HOST") != "127.0.0.1"
    or not all(
        os.environ.get(name)
        for name in ("AGENTBOX_E2E_USERNAME", "AGENTBOX_E2E_PASSWORD", "AGENTBOX_E2E_PAIR_CODE")
    )
):
    raise RuntimeError("auth timing requires the isolated E2E harness")

# Validate opt-in before importing the fixture that initializes synthetic data.
from e2e_app import app as fixture_app  # noqa: E402

_T = TypeVar("_T")
_sample: ContextVar[int] = ContextVar("e2e_timing_sample", default=0)
_admission_start: ContextVar[float] = ContextVar("e2e_timing_admission", default=0)
_guard = Lock()
_events: list[dict[str, int | float | str]] = []
_dropped = 0
_lag_max = 0.0
_sequence = 0
_epoch = perf_counter()


def record(phase: str, milliseconds: float, sample: int | None = None) -> None:
    global _dropped
    with _guard:
        if len(_events) < 254:
            _events.append(
                {
                    "sample": _sample.get() if sample is None else sample,
                    "phase": phase,
                    "ms": round(max(0.0, milliseconds), 3),
                }
            )
        else:
            _dropped += 1


class TimingLoginExecutor(BoundedLoginExecutor):
    async def _run(self, operation: Callable[[], IssuedSession]) -> IssuedSession:
        started = perf_counter()
        token = _admission_start.set(started)
        try:
            return await super()._run(operation)
        finally:
            record("executor_total_ms", (perf_counter() - started) * 1000)
            _admission_start.reset(token)


fixture_app.state.login_executor = TimingLoginExecutor(
    fixture_app.state.services.auth,
    max_concurrency=fixture_app.state.settings.argon2_max_concurrency,
)
_original_verify = PasswordManager.verify


def timed_verify(manager: PasswordManager, encoded_hash: str, password: str) -> bool:
    started = perf_counter()
    try:
        return _original_verify(manager, encoded_hash, password)
    finally:
        record("argon2_ms", (perf_counter() - started) * 1000)


PasswordManager.verify = timed_verify  # type: ignore[method-assign, assignment]


@event.listens_for(fixture_app.state.services.database.engine, "before_cursor_execute")
def before_sql(
    connection: Connection,
    cursor: object,
    statement: str,
    parameters: object,
    context: object,
    executemany: bool,
) -> None:
    if statement == "BEGIN IMMEDIATE" and _sample.get():
        connection.info["e2e_timing_begin"] = (_sample.get(), perf_counter())


def finish_begin(connection: Connection) -> None:
    observation = connection.info.pop("e2e_timing_begin", None)
    if observation is not None:
        sample, started = observation
        record("begin_immediate_ms", (perf_counter() - started) * 1000, sample)


@event.listens_for(fixture_app.state.services.database.engine, "after_cursor_execute")
def after_sql(
    connection: Connection,
    cursor: object,
    statement: str,
    parameters: object,
    context: object,
    executemany: bool,
) -> None:
    finish_begin(connection)


@event.listens_for(fixture_app.state.services.database.engine, "handle_error")
def failed_sql(context: ExceptionContext) -> None:
    if context.connection is not None:
        finish_begin(context.connection)


async def sample_loop_lag() -> None:
    global _lag_max
    while True:
        started = perf_counter()
        await asyncio.sleep(0.05)
        _lag_max = max(_lag_max, max(0, perf_counter() - started - 0.05) * 1000)


_fixture_lifespan = fixture_app.router.lifespan_context


@asynccontextmanager
async def timing_lifespan(application: FastAPI) -> AsyncIterator[None]:
    loop = asyncio.get_running_loop()
    original_submit = loop.run_in_executor

    def submit(
        executor: Executor | None, function: Callable[..., _T], *args: Any
    ) -> asyncio.Future[_T]:
        sample = _sample.get()
        if not sample or not _admission_start.get():
            return original_submit(executor, function, *args)
        submitted = perf_counter()
        record("admission_ms", (submitted - _admission_start.get()) * 1000, sample)

        def execute() -> _T:
            started = perf_counter()
            record("pool_queue_ms", (started - submitted) * 1000, sample)
            try:
                return function(*args)
            finally:
                record("worker_ms", (perf_counter() - started) * 1000, sample)

        return original_submit(executor, execute)

    loop.run_in_executor = submit  # type: ignore[method-assign, assignment]
    lag_task = asyncio.create_task(sample_loop_lag())
    try:
        async with _fixture_lifespan(application):
            yield
    finally:
        loop.run_in_executor = original_submit  # type: ignore[method-assign]
        lag_task.cancel()
        with suppress(asyncio.CancelledError):
            await lag_task


fixture_app.router.lifespan_context = timing_lifespan


async def observed_app(scope: Scope, receive: Receive, send: Send) -> None:
    global _sequence, _dropped, _lag_max
    if scope["type"] != "http":
        await fixture_app(scope, receive, send)
        return
    if scope["path"] == "/api/__e2e/auth-timing" and scope["method"] == "GET":
        with _guard:
            observations = list(_events)
            _events.clear()
            observations.append({"sample": 0, "phase": "dropped", "ms": _dropped})
            _dropped = 0
        observations.append({"sample": 0, "phase": "loop_lag_ms", "ms": round(_lag_max, 3)})
        _lag_max = 0
        await JSONResponse({"events": observations}, headers={"Cache-Control": "no-store"})(
            scope, receive, send
        )
        return
    if not scope["path"].startswith("/api/") or _sequence >= 128:
        await fixture_app(scope, receive, send)
        return
    _sequence += 1
    token = _sample.set(_sequence)
    started = perf_counter()
    record("request_start_ms", (started - _epoch) * 1000)
    kind = {"/api/v1/auth/login": 1, "/api/v1/auth/me": 2}.get(scope["path"], 3)
    record("request_kind", kind)

    async def timed_send(message: Message) -> None:
        if message["type"] == "http.response.start":
            record("status", message["status"])
        await send(message)

    try:
        await fixture_app(scope, receive, timed_send)
    finally:
        record("request_total_ms", (perf_counter() - started) * 1000)
        _sample.reset(token)


async def app(scope: Scope, receive: Receive, send: Send) -> None:
    """Contain HTTP exceptions before Uvicorn can log secret-bearing details.

    The harness also discards this diagnostic API's raw stdout/stderr, covering
    import, lifespan and detached-task failures outside this request boundary.
    Numeric errors invalidate the sample even if a response was already sent.
    """
    if scope["type"] != "http":
        await observed_app(scope, receive, send)
        return
    response_started = False

    async def safe_send(message: Message) -> None:
        nonlocal response_started
        if message["type"] == "http.response.start":
            response_started = True
        await send(message)

    try:
        await observed_app(scope, receive, safe_send)
    except Exception:
        record("unhandled_error", 1, 0)
        if not response_started:
            # Never interpolate an exception, request value or SQL into output.
            with suppress(Exception):
                await JSONResponse(
                    {"error": "diagnostic_request_failed"},
                    status_code=500,
                    headers={"Cache-Control": "no-store"},
                )(scope, receive, send)
