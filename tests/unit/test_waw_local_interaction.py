from __future__ import annotations

import os
import pty
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict
from pathlib import Path
from typing import Any, cast

import pytest
from agentbox_core.waw import AgentType
from agentbox_runtime import waw_local_interaction as subject
from agentbox_runtime.waw_local_interaction import (
    WAWLocalInteractionAction,
    WAWLocalInteractionCoordinator,
    WAWLocalInteractionError,
    WAWLocalInteractionHandler,
    WAWLocalInteractionRequest,
    WAWLocalInteractionResult,
    WAWLocalInteractionStatus,
    WAWLocalProfileBinding,
    WAWLocalTTYSession,
)
from agentbox_runtime.waw_process_profile import INTERACTIVE_PROFILE_CONSTANTS_V1

HOST = "wri_" + "1" * 32
PROJECT = "prj_" + "2" * 32


def _binding(agent_type: AgentType = AgentType.CLAUDE) -> WAWLocalProfileBinding:
    profile = INTERACTIVE_PROFILE_CONSTANTS_V1[agent_type.value]
    return WAWLocalProfileBinding(
        agent_type,
        HOST,
        "3",
        cast(str, profile["profile_id"]),
        Path(cast(str, profile["home"])),
    )


@contextmanager
def _tty(monkeypatch: pytest.MonkeyPatch) -> Iterator[int]:
    master, slave = pty.openpty()
    process_group = os.getpgrp()
    session = os.getsid(0)
    monkeypatch.setattr(subject, "_tcgetpgrp", lambda _fd: process_group)
    monkeypatch.setattr(subject, "_getsid", lambda _pid: session)
    try:
        yield slave
    finally:
        os.close(master)
        os.close(slave)


class _Handler(WAWLocalInteractionHandler):
    """Synthetic nominal handler with no terminal scan or automatic yes API."""

    def __init__(self) -> None:
        self.interactions = 0
        self.held_fds: tuple[int, int] | None = None

    def interact(
        self, request: WAWLocalInteractionRequest, tty: WAWLocalTTYSession
    ) -> WAWLocalInteractionResult:
        self.interactions += 1
        assert not tty.closed
        assert os.isatty(tty.input_fd)
        assert os.isatty(tty.output_fd)
        self.held_fds = (tty.input_fd, tty.output_fd)
        return WAWLocalInteractionResult(
            request.action,
            request.binding,
            tty.tty_id,
            request.project_id,
            WAWLocalInteractionStatus.COMPLETED,
        )


@pytest.mark.parametrize("agent_type", list(AgentType))
def test_login_uses_real_held_tty_and_exact_process_profile(
    agent_type: AgentType, monkeypatch: pytest.MonkeyPatch
) -> None:
    binding = _binding(agent_type)
    request = WAWLocalInteractionRequest(WAWLocalInteractionAction.LOGIN, binding)
    handler = _Handler()
    with _tty(monkeypatch) as terminal:
        result = WAWLocalInteractionCoordinator().perform(
            request, handler, input_fd=terminal, output_fd=terminal
        )
    assert result.status is WAWLocalInteractionStatus.COMPLETED
    assert result.binding == binding
    assert result.project_id is None
    assert handler.interactions == 1
    assert handler.held_fds is not None
    for descriptor in handler.held_fds:
        with pytest.raises(OSError):
            os.fstat(descriptor)


@pytest.mark.parametrize("agent_type", list(AgentType))
def test_project_trust_is_typed_and_has_no_terminal_output(
    agent_type: AgentType, monkeypatch: pytest.MonkeyPatch
) -> None:
    binding = _binding(agent_type)
    request = WAWLocalInteractionRequest(WAWLocalInteractionAction.TRUST, binding, PROJECT)
    with _tty(monkeypatch) as terminal:
        result = WAWLocalInteractionCoordinator().perform(
            request, _Handler(), input_fd=terminal, output_fd=terminal
        )
    assert result.action is WAWLocalInteractionAction.TRUST
    assert result.project_id == PROJECT
    assert result.binding.agent_type is agent_type
    assert not ({"output", "terminal", "prompt", "confirmation"} & asdict(result).keys())


def test_pipe_is_rejected_before_handler() -> None:
    read_fd, write_fd = os.pipe()
    handler = _Handler()
    try:
        with pytest.raises(WAWLocalInteractionError, match="local TTY unavailable"):
            WAWLocalInteractionCoordinator().perform(
                WAWLocalInteractionRequest(WAWLocalInteractionAction.LOGIN, _binding()),
                handler,
                input_fd=read_fd,
                output_fd=write_fd,
            )
    finally:
        os.close(read_fd)
        os.close(write_fd)
    assert handler.interactions == 0


def test_different_tty_devices_are_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    with (
        _tty(monkeypatch) as first,
        _tty(monkeypatch) as second,
        pytest.raises(WAWLocalInteractionError, match="local TTY unavailable"),
    ):
        WAWLocalInteractionCoordinator().perform(
            WAWLocalInteractionRequest(WAWLocalInteractionAction.LOGIN, _binding()),
            _Handler(),
            input_fd=first,
            output_fd=second,
        )


def test_tty_session_is_opaque_and_structural_handler_is_rejected() -> None:
    with pytest.raises(TypeError, match="created by open"):
        WAWLocalTTYSession(object(), _binding(), "ltty_" + "a" * 32, 0, 1, (1, 1, 1), 1, 1)

    class StructuralFake:
        def interact(self, request: object, tty: object) -> object:
            raise AssertionError((request, tty))

    with pytest.raises(TypeError, match="inherit"):
        WAWLocalInteractionCoordinator().perform(
            WAWLocalInteractionRequest(WAWLocalInteractionAction.LOGIN, _binding()),
            cast(WAWLocalInteractionHandler, StructuralFake()),
        )


def test_handler_exception_is_normalized_without_private_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FailingHandler(WAWLocalInteractionHandler):
        def interact(
            self, request: WAWLocalInteractionRequest, tty: WAWLocalTTYSession
        ) -> WAWLocalInteractionResult:
            del request, tty
            raise RuntimeError("private vendor output")

    with (
        _tty(monkeypatch) as terminal,
        pytest.raises(WAWLocalInteractionError) as raised,
    ):
        WAWLocalInteractionCoordinator().perform(
            WAWLocalInteractionRequest(WAWLocalInteractionAction.LOGIN, _binding()),
            FailingHandler(),
            input_fd=terminal,
            output_fd=terminal,
        )
    assert str(raised.value) == "local interaction failed"
    assert raised.value.__cause__ is None


def test_login_and_trust_request_shapes_are_closed() -> None:
    binding = _binding()
    with pytest.raises(ValueError, match="LOGIN cannot carry"):
        WAWLocalInteractionRequest(WAWLocalInteractionAction.LOGIN, binding, PROJECT)
    with pytest.raises(ValueError, match="TRUST requires"):
        WAWLocalInteractionRequest(WAWLocalInteractionAction.TRUST, binding)
    with pytest.raises(ValueError):
        WAWLocalInteractionRequest(cast(WAWLocalInteractionAction, "YES"), binding, PROJECT)


def test_handler_surface_has_no_auto_confirm_or_terminal_scanning_methods() -> None:
    public = {name for name in dir(_Handler()) if not name.startswith("_")}
    assert public == {"held_fds", "interact", "interactions"}


def test_background_tty_in_same_session_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    master, slave = pty.openpty()
    process_group = os.getpgrp()
    session = os.getsid(0)
    monkeypatch.setattr(subject, "_tcgetpgrp", lambda _fd: process_group + 1)
    monkeypatch.setattr(subject, "_getsid", lambda _pid: session)
    try:
        with pytest.raises(WAWLocalInteractionError, match="local TTY unavailable"):
            WAWLocalTTYSession.open(_binding(), input_fd=slave, output_fd=slave)
    finally:
        os.close(master)
        os.close(slave)


def test_foreground_identity_is_read_back_before_handler(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    master, slave = pty.openpty()
    process_group = os.getpgrp()
    session = os.getsid(0)
    calls = 0

    def changed_after_open(_fd: int) -> int:
        nonlocal calls
        calls += 1
        return process_group if calls <= 2 else process_group + 1

    monkeypatch.setattr(subject, "_tcgetpgrp", changed_after_open)
    monkeypatch.setattr(subject, "_getsid", lambda _pid: session)
    handler = _Handler()
    try:
        with pytest.raises(WAWLocalInteractionError, match="local TTY unavailable"):
            WAWLocalInteractionCoordinator().perform(
                WAWLocalInteractionRequest(WAWLocalInteractionAction.LOGIN, _binding()),
                handler,
                input_fd=slave,
                output_fd=slave,
            )
    finally:
        os.close(master)
        os.close(slave)
    assert handler.interactions == 0


@pytest.mark.parametrize(
    "failure_stage",
    ["second_dup", "set_inheritable", "fstat", "isatty", "tcgetpgrp", "getsid"],
)
def test_every_tty_factory_failure_closes_each_successful_dup(
    monkeypatch: pytest.MonkeyPatch, failure_stage: str
) -> None:
    master, slave = pty.openpty()
    duplicated: list[int] = []
    real_dup = os.dup
    dup_calls = 0

    def tracked_dup(fd: int) -> int:
        nonlocal dup_calls
        dup_calls += 1
        if failure_stage == "second_dup" and dup_calls == 2:
            raise OSError("synthetic")
        result = real_dup(fd)
        duplicated.append(result)
        return result

    monkeypatch.setattr(subject, "_dup", tracked_dup)
    monkeypatch.setattr(subject, "_tcgetpgrp", lambda _fd: os.getpgrp())
    monkeypatch.setattr(subject, "_getsid", os.getsid)
    if failure_stage == "set_inheritable":
        monkeypatch.setattr(
            subject,
            "_set_inheritable",
            lambda _fd, _value: (_ for _ in ()).throw(OSError()),
        )
    elif failure_stage == "fstat":
        monkeypatch.setattr(subject, "_fstat", lambda _fd: (_ for _ in ()).throw(OSError()))
    elif failure_stage == "isatty":
        monkeypatch.setattr(subject, "_isatty", lambda _fd: (_ for _ in ()).throw(OSError()))
    elif failure_stage == "tcgetpgrp":
        monkeypatch.setattr(subject, "_tcgetpgrp", lambda _fd: (_ for _ in ()).throw(OSError()))
    elif failure_stage == "getsid":
        monkeypatch.setattr(subject, "_getsid", lambda _pid: (_ for _ in ()).throw(OSError()))
    try:
        with pytest.raises(WAWLocalInteractionError, match="local TTY unavailable"):
            WAWLocalTTYSession.open(_binding(), input_fd=slave, output_fd=slave)
    finally:
        os.close(master)
        os.close(slave)
    assert duplicated
    for descriptor in duplicated:
        with pytest.raises(OSError):
            os.fstat(descriptor)


@pytest.mark.parametrize(
    "changes",
    [
        {"runtime_host_installation_revision": "0"},
        {"profile_id": "wlp_claude_fixture"},
        {"home": Path("/wrong/home")},
        {"agent_type": "claude"},
    ],
)
def test_profile_binding_rejects_noncanonical_process_profile(changes: dict[str, Any]) -> None:
    profile = INTERACTIVE_PROFILE_CONSTANTS_V1["claude"]
    values: dict[str, Any] = {
        "agent_type": AgentType.CLAUDE,
        "runtime_host_installation_id": HOST,
        "runtime_host_installation_revision": "3",
        "profile_id": profile["profile_id"],
        "home": Path(cast(str, profile["home"])),
    }
    values.update(changes)
    with pytest.raises(ValueError):
        WAWLocalProfileBinding(**values)
