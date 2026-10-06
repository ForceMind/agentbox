"""Failure-only, fixed traceback classification for the same-process test driver."""

from types import CodeType, TracebackType

from agentbox_core.a3_native_io import NativeChannel
from agentbox_protocol.a3_content import ContentError

CHECKER_TIMEOUT_SITES = (
    "unknown",
    "idle-readiness",
    "receive-wait-deadline-check",
    "pre-recv-deadline-check",
    "post-decode-deadline-check",
)
_CHECK = NativeChannel._check.__code__
_WAIT = NativeChannel._wait.__code__
_IDLE = NativeChannel.wait_readable.__code__
_RECEIVE = NativeChannel.receive.__code__


def _classify(error: BaseException, checker_code: CodeType) -> str:
    if (
        type(error) is not ContentError
        or len(error.args) != 1
        or type(error.args[0]) is not str
        or error.args[0] != "PATCH_TIMEOUT"
    ):
        return "unknown"
    # Keep only code objects and relative line numbers, never frames/tracebacks.
    chain: list[tuple[CodeType, int]] = []
    cursor: object = error.__traceback__
    for _ in range(8):
        if cursor is None:
            break
        if type(cursor) is not TracebackType:
            return "unknown"
        code = cursor.tb_frame.f_code
        chain.append((code, cursor.tb_lineno - code.co_firstlineno))
        cursor = cursor.tb_next
    if cursor is not None:
        return "unknown"
    # Each allowed source line has exactly one relevant call or timeout raise.
    # A changed/extra guard, codec, cleanup or wrapper frame stays unknown.
    patterns = (
        ("idle-readiness", ((checker_code, 4), (_IDLE, 3), (_WAIT, 2), (_CHECK, 14))),
        ("idle-readiness", ((checker_code, 4), (_IDLE, 4), (_CHECK, 14))),
        (
            "receive-wait-deadline-check",
            ((checker_code, 5), (_RECEIVE, 8), (_WAIT, 2), (_CHECK, 14)),
        ),
        ("pre-recv-deadline-check", ((checker_code, 5), (_RECEIVE, 9), (_CHECK, 14))),
        ("post-decode-deadline-check", ((checker_code, 5), (_RECEIVE, 20), (_CHECK, 14))),
    )
    for label, expected in patterns:
        if len(chain) == len(expected) and all(
            actual_code is wanted_code and actual_line == wanted_line
            for (actual_code, actual_line), (wanted_code, wanted_line) in zip(
                chain, expected, strict=True
            )
        ):
            return label
    return "unknown"


def classify_checker_timeout(error: BaseException, checker_code: CodeType) -> str:
    """Classify only the complete fixed checker chain; diagnostics never escape."""
    try:
        return _classify(error, checker_code)
    except BaseException:
        return "unknown"
