"""Synthetic thread barriers for shared login/reauthentication admission."""

from __future__ import annotations

import asyncio
import gc
import threading
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any, Literal, cast

import pytest
from agentbox_api.auth import BoundedLoginExecutor
from agentbox_core.services import AuthenticatedSession, AuthService, IssuedSession

Method = Literal["login", "reauthenticate"]
CALLER_CONTEXT: ContextVar[str] = ContextVar("auth_executor_test_context", default="unset")
AUTHENTICATED = cast(AuthenticatedSession, object())


@dataclass
class Job:
    entered: threading.Event = field(default_factory=threading.Event)
    release: threading.Event = field(default_factory=threading.Event)
    finished: threading.Event = field(default_factory=threading.Event)
    result: IssuedSession = field(default_factory=lambda: cast(IssuedSession, object()))
    error: Exception | None = None


class SyntheticAuthService:
    def __init__(self, jobs: dict[str, Job]) -> None:
        self.jobs = jobs
        self.lock = threading.Lock()
        self.active = 0
        self.peak = 0
        self.calls: list[tuple[Method, str, int, str]] = []

    def _run(self, method: Method, key: str) -> IssuedSession:
        job = self.jobs[key]
        with self.lock:
            self.active += 1
            self.peak = max(self.peak, self.active)
            self.calls.append((method, key, threading.get_ident(), CALLER_CONTEXT.get()))
        job.entered.set()
        try:
            assert job.release.wait(5), "test did not release synthetic authentication worker"
            if job.error is not None:
                raise job.error
            return job.result
        finally:
            with self.lock:
                self.active -= 1
            job.finished.set()

    def login(
        self,
        *,
        username: str,
        password: str,
        source_identifier: str,
        request_id: str | None,
        client_label: str | None,
    ) -> IssuedSession:
        assert (username, source_identifier, request_id, client_label) == (
            "synthetic-user",
            "synthetic-source",
            "synthetic-request",
            "synthetic-client",
        )
        return self._run("login", password)

    def reauthenticate(
        self,
        authenticated: AuthenticatedSession,
        *,
        password: str,
        source_identifier: str,
        request_id: str | None,
    ) -> IssuedSession:
        assert authenticated is AUTHENTICATED
        assert (source_identifier, request_id) == ("synthetic-source", "synthetic-request")
        return self._run("reauthenticate", password)


class ObservedSemaphore(asyncio.Semaphore):
    """Signal admission attempts without relying on scheduler delays or sleeps."""

    def __init__(self, capacity: int) -> None:
        super().__init__(capacity)
        self.attempts: asyncio.Queue[None] = asyncio.Queue()
        self.releases: asyncio.Queue[None] = asyncio.Queue()
        self.acquired_count = 0
        self.released_count = 0
        self.on_release: Callable[[], None] | None = None

    async def acquire(self) -> Literal[True]:
        self.attempts.put_nowait(None)
        acquired = await super().acquire()
        self.acquired_count += 1
        return acquired

    def release(self) -> None:
        super().release()
        self.released_count += 1
        self.releases.put_nowait(None)
        if self.on_release is not None:
            self.on_release()

    async def wait_attempts(self, count: int) -> None:
        for _ in range(count):
            await asyncio.wait_for(self.attempts.get(), timeout=5)

    async def wait_finished(self) -> None:
        while self.acquired_count != self.released_count:
            await asyncio.wait_for(self.releases.get(), timeout=5)


@dataclass
class Harness:
    jobs: dict[str, Job]
    service: SyntheticAuthService
    executor: BoundedLoginExecutor
    semaphore: ObservedSemaphore
    tasks: list[asyncio.Task[IssuedSession]] = field(default_factory=list)

    def start(self, method: Method, key: str) -> asyncio.Task[IssuedSession]:
        if method == "login":
            coroutine = self.executor.login(
                username="synthetic-user",
                password=key,
                source_identifier="synthetic-source",
                request_id="synthetic-request",
                client_label="synthetic-client",
            )
        else:
            coroutine = self.executor.reauthenticate(
                AUTHENTICATED,
                password=key,
                source_identifier="synthetic-source",
                request_id="synthetic-request",
            )
        task = asyncio.create_task(coroutine)
        self.tasks.append(task)
        return task


@asynccontextmanager
async def harness(capacity: int, count: int = 3) -> AsyncIterator[Harness]:
    jobs = {str(index): Job() for index in range(count)}
    service = SyntheticAuthService(jobs)
    executor = BoundedLoginExecutor(cast(AuthService, service), max_concurrency=capacity)
    semaphore = ObservedSemaphore(capacity)
    executor._semaphore = semaphore
    state = Harness(jobs, service, executor, semaphore)
    try:
        yield state
    finally:
        semaphore.on_release = None
        for job in jobs.values():
            job.release.set()
        await asyncio.wait_for(asyncio.gather(*state.tasks, return_exceptions=True), timeout=5)
        await semaphore.wait_finished()


async def wait_thread(event: threading.Event) -> None:
    assert await asyncio.wait_for(asyncio.to_thread(event.wait, 5), timeout=6)


@pytest.mark.anyio
@pytest.mark.parametrize("capacity", [1, 2, 4])
async def test_login_and_reauthentication_share_bounded_thread_capacity(capacity: int) -> None:
    async with harness(capacity, capacity + 2) as state:
        for index in range(capacity + 2):
            state.start("login" if index % 2 == 0 else "reauthenticate", str(index))
        await state.semaphore.wait_attempts(capacity + 2)
        for index in range(capacity):
            await wait_thread(state.jobs[str(index)].entered)
        assert state.semaphore.acquired_count == capacity
        assert len(state.service.calls) == capacity
        assert all(
            not state.jobs[str(index)].entered.is_set() for index in range(capacity, capacity + 2)
        )

        for job in state.jobs.values():
            job.release.set()
        results = await asyncio.wait_for(asyncio.gather(*state.tasks), timeout=5)
        assert results == [job.result for job in state.jobs.values()]
        assert state.service.peak == capacity
        assert len(state.service.calls) == capacity + 2
        assert all(call[2] != threading.get_ident() for call in state.service.calls)


@pytest.mark.anyio
@pytest.mark.parametrize("method", ["login", "reauthenticate"])
@pytest.mark.parametrize("fails", [False, True])
async def test_running_caller_cancel_keeps_capacity_until_actual_worker_finishes(
    method: Method, fails: bool
) -> None:
    loop = asyncio.get_running_loop()
    errors: list[dict[str, Any]] = []
    previous_handler = loop.get_exception_handler()
    loop.set_exception_handler(lambda _loop, context: errors.append(context))
    try:
        async with harness(1) as state:
            if fails:
                state.jobs["0"].error = RuntimeError("synthetic detached worker failure")
            first = state.start(method, "0")
            await state.semaphore.wait_attempts(1)
            await wait_thread(state.jobs["0"].entered)
            first.cancel()
            with pytest.raises(asyncio.CancelledError):
                await asyncio.wait_for(first, timeout=1)
            assert not state.jobs["0"].finished.is_set()

            other_method: Method = "reauthenticate" if method == "login" else "login"
            second = state.start(other_method, "1")
            await state.semaphore.wait_attempts(1)
            assert state.semaphore.acquired_count == 1
            assert not state.jobs["1"].entered.is_set()
            state.jobs["0"].release.set()
            await wait_thread(state.jobs["1"].entered)
            assert state.jobs["0"].finished.is_set()
            state.jobs["1"].release.set()
            assert await asyncio.wait_for(second, timeout=5) is state.jobs["1"].result
            assert state.service.peak == 1
        gc.collect()
        assert errors == []
    finally:
        loop.set_exception_handler(previous_handler)


@pytest.mark.anyio
@pytest.mark.parametrize("cancel_on_wakeup", [False, True])
async def test_cancelled_waiter_neither_submits_work_nor_loses_reserved_capacity(
    cancel_on_wakeup: bool,
) -> None:
    async with harness(1) as state:
        first = state.start("login", "0")
        await state.semaphore.wait_attempts(1)
        await wait_thread(state.jobs["0"].entered)
        waiting = state.start("reauthenticate", "1")
        following = state.start("login", "2")
        await state.semaphore.wait_attempts(2)
        if cancel_on_wakeup:
            # Cancel after release reserves a permit for this waiter, but before
            # it resumes acquire. The next waiter must inherit that permit.
            def cancel_waiter() -> None:
                waiting.cancel()

            state.semaphore.on_release = cancel_waiter
            state.jobs["0"].release.set()
        else:
            waiting.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(waiting, timeout=1)
        state.semaphore.on_release = None
        assert not state.jobs["1"].entered.is_set()
        state.jobs["0"].release.set()
        assert await asyncio.wait_for(first, timeout=5) is state.jobs["0"].result
        await wait_thread(state.jobs["2"].entered)
        state.jobs["2"].release.set()
        assert await asyncio.wait_for(following, timeout=5) is state.jobs["2"].result
        assert [call[1] for call in state.service.calls] == ["0", "2"]
        assert state.service.peak == 1


@pytest.mark.anyio
@pytest.mark.parametrize("method", ["login", "reauthenticate"])
async def test_worker_error_propagates_unchanged_and_releases_capacity(method: Method) -> None:
    async with harness(1) as state:
        failure = RuntimeError("synthetic authentication failure")
        state.jobs["0"].error = failure
        first = state.start(method, "0")
        await wait_thread(state.jobs["0"].entered)
        state.jobs["0"].release.set()
        with pytest.raises(RuntimeError) as raised:
            await asyncio.wait_for(first, timeout=5)
        assert raised.value is failure
        second = state.start(method, "1")
        await wait_thread(state.jobs["1"].entered)
        state.jobs["1"].release.set()
        assert await asyncio.wait_for(second, timeout=5) is state.jobs["1"].result
        assert state.service.peak == 1


@pytest.mark.anyio
@pytest.mark.parametrize("method", ["login", "reauthenticate"])
async def test_caller_context_is_copied_to_the_worker(method: Method) -> None:
    async with harness(1) as state:
        token = CALLER_CONTEXT.set("synthetic-request-context")
        try:
            pending = state.start(method, "0")
        finally:
            CALLER_CONTEXT.reset(token)
        await wait_thread(state.jobs["0"].entered)
        state.jobs["0"].release.set()
        await asyncio.wait_for(pending, timeout=5)
        assert state.service.calls[0][3] == "synthetic-request-context"
        assert CALLER_CONTEXT.get() == "unset"


@pytest.mark.anyio
async def test_submission_failure_releases_capacity_without_starting_auth_work(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async with harness(1) as state:
        failure = RuntimeError("synthetic executor submission failure")

        def fail_submission(*_args: object, **_kwargs: object) -> None:
            raise failure

        with monkeypatch.context() as patch:
            patch.setattr(asyncio.get_running_loop(), "run_in_executor", fail_submission)
            first = state.start("login", "0")
            with pytest.raises(RuntimeError) as raised:
                await asyncio.wait_for(first, timeout=5)
            assert raised.value is failure
        assert state.service.calls == []
        second = state.start("reauthenticate", "1")
        await wait_thread(state.jobs["1"].entered)
        state.jobs["1"].release.set()
        assert await asyncio.wait_for(second, timeout=5) is state.jobs["1"].result
