import json
import logging

from agentbox_core.logging import JsonLogFormatter


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
