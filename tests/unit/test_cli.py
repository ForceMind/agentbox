import json

import pytest
from agentbox_cli.main import main
from agentbox_core import __version__


def test_cli_version(capsys: pytest.CaptureFixture[str]) -> None:
    # argparse's version action intentionally exits after printing.
    with pytest.raises(SystemExit) as exc_info:
        main(["--version"])

    assert exc_info.value.code == 0
    assert capsys.readouterr().out.strip() == __version__


def test_cli_status_json_is_an_explicit_placeholder(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["status", "--json"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["command"] == "status"
    assert payload["data"]["status"] == "not_implemented"
