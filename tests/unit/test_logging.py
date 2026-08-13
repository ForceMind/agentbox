import json
import logging

from agentbox_core.logging import JsonLogFormatter
from agentbox_core.security import redact_text


def test_structured_logging_redacts_sensitive_assignments_and_fields() -> None:
    formatter = JsonLogFormatter()
    record = logging.LogRecord(
        name="agentbox.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="login failed password=canary token:raw-token",
        args=(),
        exc_info=None,
    )
    record.request_id = "req_test"
    record.event = "login_failed"
    record.safe_fields = {"result": "failed", "cookie": "raw-cookie"}

    payload = json.loads(formatter.format(record))
    rendered = json.dumps(payload)

    assert "canary" not in rendered
    assert "raw-token" not in rendered
    assert "raw-cookie" not in rendered
    assert payload["request_id"] == "req_test"
    assert payload["event"] == "login_failed"


def test_bearer_and_standalone_github_tokens_are_fully_redacted() -> None:
    token = "".join(("gh", "p_", "PHASE9FAKETOKEN1234567890123456789012"))
    rendered = redact_text(f"Authorization: Bearer {token} token={token}")

    assert token not in rendered
    assert rendered == "Authorization: [REDACTED] token=[REDACTED]"
