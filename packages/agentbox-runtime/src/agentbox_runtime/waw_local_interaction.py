"""Nominal local-TTY seam for official vendor login and Project Trust.

There is no browser/API transport, prompt text, terminal capture/parser, or
automatic-confirm option. The coordinator duplicates and holds real local TTY
descriptors, verifies their device and session identity, and then invokes only
a nominal trusted handler under the exact interactive process-profile binding.
"""

from __future__ import annotations

import hashlib
import os
import re
import stat
from abc import ABC, abstractmethod
from contextlib import suppress
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from types import TracebackType

from agentbox_core.waw import (
    AgentType,
    validate_project_id,
    validate_runtime_host_installation_id,
)

from agentbox_runtime.waw_process_profile import INTERACTIVE_PROFILE_CONSTANTS_V1

_DECIMAL = re.compile(r"\A[1-9][0-9]{0,19}\Z")
_TTY_ID = re.compile(r"\Altty_[0-9a-f]{32}\Z")
_MAX_U64 = 2**64 - 1
_TTY_TOKEN = object()

_dup = os.dup
_close = os.close
_fstat = os.fstat
_isatty = os.isatty
_set_inheritable = os.set_inheritable
_tcgetpgrp = os.tcgetpgrp
_getpgrp = os.getpgrp
_getsid = os.getsid


class WAWLocalInteractionError(RuntimeError):
    """Fixed local-interaction failure without handler or terminal details."""


class WAWLocalInteractionAction(StrEnum):
    LOGIN = "LOGIN"
    TRUST = "TRUST"


class WAWLocalInteractionStatus(StrEnum):
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"


@dataclass(frozen=True)
class WAWLocalProfileBinding:
    """Exact process-profile identity shared by login/trust and launch."""

    agent_type: AgentType
    runtime_host_installation_id: str
    runtime_host_installation_revision: str
    profile_id: str
    home: Path

    def __post_init__(self) -> None:
        if type(self.agent_type) is not AgentType:
            raise ValueError("local profile agent_type is invalid")
        validate_runtime_host_installation_id(self.runtime_host_installation_id)
        if (
            type(self.runtime_host_installation_revision) is not str
            or _DECIMAL.fullmatch(self.runtime_host_installation_revision) is None
            or int(self.runtime_host_installation_revision) > _MAX_U64
        ):
            raise ValueError("local profile Runtime installation revision is invalid")
        expected = INTERACTIVE_PROFILE_CONSTANTS_V1[self.agent_type.value]
        if self.profile_id != expected["profile_id"]:
            raise ValueError("local profile_id does not match interactive profile")
        if (
            not isinstance(self.home, Path)
            or str(self.home) != expected["home"]
            or not self.home.is_absolute()
        ):
            raise ValueError("local profile HOME does not match interactive profile")


@dataclass(frozen=True)
class WAWLocalInteractionRequest:
    action: WAWLocalInteractionAction
    binding: WAWLocalProfileBinding
    project_id: str | None = None

    def __post_init__(self) -> None:
        if type(self.action) is not WAWLocalInteractionAction:
            raise ValueError("local interaction action is invalid")
        if type(self.binding) is not WAWLocalProfileBinding:
            raise ValueError("local interaction binding is invalid")
        self.binding.__post_init__()
        if self.action is WAWLocalInteractionAction.LOGIN:
            if self.project_id is not None:
                raise ValueError("LOGIN cannot carry a Project")
        elif self.project_id is None:
            raise ValueError("TRUST requires a Project")
        else:
            validate_project_id(self.project_id)


@dataclass(frozen=True)
class WAWLocalInteractionResult:
    """Metadata-only completion; vendor output and terminal content are absent."""

    action: WAWLocalInteractionAction
    binding: WAWLocalProfileBinding
    tty_id: str
    project_id: str | None
    status: WAWLocalInteractionStatus

    def __post_init__(self) -> None:
        if type(self.action) is not WAWLocalInteractionAction:
            raise ValueError("local interaction result action is invalid")
        if type(self.binding) is not WAWLocalProfileBinding:
            raise ValueError("local interaction result binding is invalid")
        self.binding.__post_init__()
        if type(self.tty_id) is not str or _TTY_ID.fullmatch(self.tty_id) is None:
            raise ValueError("local interaction result TTY identity is invalid")
        if type(self.status) is not WAWLocalInteractionStatus:
            raise ValueError("local interaction status is invalid")
        if self.action is WAWLocalInteractionAction.LOGIN:
            if self.project_id is not None:
                raise ValueError("LOGIN result cannot carry a Project")
        elif self.project_id is None:
            raise ValueError("TRUST result requires a Project")
        else:
            validate_project_id(self.project_id)


class WAWLocalTTYSession:
    """Opaque nominal capability owning validated local input/output TTY FDs."""

    def __init__(
        self,
        token: object,
        binding: WAWLocalProfileBinding,
        tty_id: str,
        input_fd: int,
        output_fd: int,
        tty_identity: tuple[int, int, int],
        process_group: int,
        session_id: int,
    ) -> None:
        if token is not _TTY_TOKEN:
            raise TypeError("WAWLocalTTYSession must be created by open")
        self._binding = binding
        self._tty_id = tty_id
        self._input_fd = input_fd
        self._output_fd = output_fd
        self._tty_identity = tty_identity
        self._process_group = process_group
        self._session_id = session_id
        self._closed = False

    @classmethod
    def open(
        cls,
        binding: WAWLocalProfileBinding,
        *,
        input_fd: int,
        output_fd: int,
    ) -> WAWLocalTTYSession:
        if type(binding) is not WAWLocalProfileBinding:
            raise WAWLocalInteractionError("local TTY unavailable")
        binding.__post_init__()
        if any(type(value) is not int or value < 0 for value in (input_fd, output_fd)):
            raise WAWLocalInteractionError("local TTY unavailable")
        held: list[int] = []
        try:
            held.append(_dup(input_fd))
            held.append(_dup(output_fd))
            for descriptor in held:
                _set_inheritable(descriptor, False)
            tty_identity, process_group, session_id = _read_tty_state(held[0], held[1])
            digest = hashlib.sha256(
                f"{tty_identity[0]}:{tty_identity[1]}:{tty_identity[2]}:"
                f"{process_group}:{session_id}".encode("ascii")
            ).hexdigest()[:32]
            session = cls(
                _TTY_TOKEN,
                binding,
                f"ltty_{digest}",
                held[0],
                held[1],
                tty_identity,
                process_group,
                session_id,
            )
            held.clear()
            return session
        except WAWLocalInteractionError:
            raise
        except (OSError, OverflowError, ValueError):
            raise WAWLocalInteractionError("local TTY unavailable") from None
        finally:
            for descriptor in held:
                _close(descriptor)

    @property
    def binding(self) -> WAWLocalProfileBinding:
        return self._binding

    @property
    def tty_id(self) -> str:
        return self._tty_id

    @property
    def input_fd(self) -> int:
        self._require_open()
        return self._input_fd

    @property
    def output_fd(self) -> int:
        self._require_open()
        return self._output_fd

    @property
    def closed(self) -> bool:
        return self._closed

    def revalidate(self) -> None:
        """Read back device and foreground-session identity immediately before use."""

        self._require_open()
        try:
            identity, process_group, session_id = _read_tty_state(self._input_fd, self._output_fd)
        except WAWLocalInteractionError:
            raise
        if (
            identity != self._tty_identity
            or process_group != self._process_group
            or session_id != self._session_id
        ):
            raise WAWLocalInteractionError("local TTY unavailable")

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        with suppress(OSError):
            _close(self._input_fd)
        with suppress(OSError):
            _close(self._output_fd)

    def __enter__(self) -> WAWLocalTTYSession:
        self._require_open()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def _require_open(self) -> None:
        if self._closed:
            raise WAWLocalInteractionError("local TTY unavailable")


def _tty_identity(details: os.stat_result) -> tuple[int, int, int]:
    return details.st_dev, details.st_ino, details.st_rdev


def _read_tty_state(input_fd: int, output_fd: int) -> tuple[tuple[int, int, int], int, int]:
    try:
        input_stat, output_stat = _fstat(input_fd), _fstat(output_fd)
        if (
            not _isatty(input_fd)
            or not _isatty(output_fd)
            or not stat.S_ISCHR(input_stat.st_mode)
            or not stat.S_ISCHR(output_stat.st_mode)
            or _tty_identity(input_stat) != _tty_identity(output_stat)
        ):
            raise WAWLocalInteractionError("local TTY unavailable")
        input_pgrp, output_pgrp, process_group = (
            _tcgetpgrp(input_fd),
            _tcgetpgrp(output_fd),
            _getpgrp(),
        )
        session_id = _getsid(0)
        if (
            process_group <= 0
            or input_pgrp != process_group
            or output_pgrp != process_group
            or _getsid(process_group) != session_id
        ):
            raise WAWLocalInteractionError("local TTY unavailable")
        return _tty_identity(input_stat), process_group, session_id
    except WAWLocalInteractionError:
        raise
    except (OSError, OverflowError, ValueError):
        raise WAWLocalInteractionError("local TTY unavailable") from None


class WAWLocalInteractionHandler(ABC):
    """Nominal trusted adapter for an official vendor interactive UI.

    Implementations receive only held TTY descriptors and a typed action. They
    must not synthesize input, submit confirmation, parse the screen, or return
    terminal bytes.
    """

    @abstractmethod
    def interact(
        self, request: WAWLocalInteractionRequest, tty: WAWLocalTTYSession
    ) -> WAWLocalInteractionResult:
        """Perform one local interaction without capture or automatic input."""


class WAWLocalInteractionCoordinator:
    """Create the TTY capability and normalize every adapter-side failure."""

    def perform(
        self,
        request: WAWLocalInteractionRequest,
        handler: WAWLocalInteractionHandler,
        *,
        input_fd: int = 0,
        output_fd: int = 1,
    ) -> WAWLocalInteractionResult:
        if type(request) is not WAWLocalInteractionRequest:
            raise TypeError("request must be WAWLocalInteractionRequest")
        request.__post_init__()
        if not isinstance(handler, WAWLocalInteractionHandler):
            raise TypeError("handler must inherit WAWLocalInteractionHandler")
        with WAWLocalTTYSession.open(
            request.binding, input_fd=input_fd, output_fd=output_fd
        ) as tty:
            tty.revalidate()
            try:
                result = handler.interact(request, tty)
            except Exception:
                raise WAWLocalInteractionError("local interaction failed") from None
            try:
                if type(result) is not WAWLocalInteractionResult:
                    raise ValueError
                result.__post_init__()
            except (TypeError, ValueError):
                raise WAWLocalInteractionError("local interaction failed") from None
            if (
                result.action is not request.action
                or result.binding != request.binding
                or result.tty_id != tty.tty_id
                or result.project_id != request.project_id
            ):
                raise WAWLocalInteractionError("local interaction failed")
            return result


__all__ = [
    "WAWLocalInteractionAction",
    "WAWLocalInteractionCoordinator",
    "WAWLocalInteractionError",
    "WAWLocalInteractionHandler",
    "WAWLocalInteractionRequest",
    "WAWLocalInteractionResult",
    "WAWLocalInteractionStatus",
    "WAWLocalProfileBinding",
    "WAWLocalTTYSession",
]
