"""Regression checks for the opt-in diagnostic, without fixture DB/bootstrap."""

from __future__ import annotations

import asyncio
import json
import logging
import runpy
import shutil
import subprocess
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any, cast

import h11
import pytest
from agentbox_core.security import PasswordManager
from fastapi import FastAPI
from sqlalchemy import create_engine
from uvicorn._types import ASGI3Application, HTTPScope
from uvicorn.protocols.http.flow_control import FlowControl
from uvicorn.protocols.http.h11_impl import RequestResponseCycle

ROOT = Path(__file__).resolve().parents[2]
CANARY = "SYNTHETIC-DIAGNOSTIC-EXCEPTION-CANARY"
NODE = shutil.which("node")


class MemoryTransport(asyncio.Transport):
    def __init__(self) -> None:
        self.output = bytearray()

    def write(self, data: bytes | bytearray | memoryview[int]) -> None:
        self.output.extend(data)

    def is_closing(self) -> bool:
        return False

    def close(self) -> None:
        pass


@pytest.mark.parametrize("path", ["/api/v1/auth/login", "/outside-api"])
def test_unhandled_http_exception_never_reaches_uvicorn_logs(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], path: str
) -> None:
    fixture = FastAPI()

    @fixture.post(path)
    async def fail() -> None:
        raise RuntimeError(CANARY)

    engine = create_engine("sqlite://")
    fixture.state.services = SimpleNamespace(auth=object(), database=SimpleNamespace(engine=engine))
    fixture.state.settings = SimpleNamespace(argon2_max_concurrency=1)
    module = ModuleType("e2e_app")
    module.__dict__["app"] = fixture
    monkeypatch.setitem(sys.modules, "e2e_app", module)
    for key, value in {
        "AGENTBOX_ENV": "test",
        "AGENTBOX_E2E_AUTH_TIMING": "1",
        "AGENTBOX_BIND_HOST": "127.0.0.1",
        "AGENTBOX_E2E_USERNAME": "synthetic",
        "AGENTBOX_E2E_PASSWORD": "synthetic",
        "AGENTBOX_E2E_PAIR_CODE": "synthetic",
    }.items():
        monkeypatch.setenv(key, value)
    # The diagnostic patches only its own process; restore it in this test process.
    monkeypatch.setattr(PasswordManager, "verify", PasswordManager.verify)
    diagnostic = runpy.run_path(str(ROOT / "tests/e2e_auth_timing_app.py"))

    async def run() -> bytes:
        transport = MemoryTransport()
        connection = h11.Connection(h11.SERVER)
        connection.receive_data(f"POST {path} HTTP/1.1\r\nHost: localhost\r\n\r\n".encode())
        connection.next_event()
        logger = logging.Logger("diagnostic-exception-regression")
        logger.addHandler(logging.StreamHandler(sys.stderr))
        scope = cast(
            HTTPScope,
            {
                "type": "http",
                "asgi": {"version": "3.0", "spec_version": "2.3"},
                "http_version": "1.1",
                "method": "POST",
                "scheme": "http",
                "path": path,
                "raw_path": path.encode(),
                "query_string": b"",
                "root_path": "",
                "headers": [],
                "client": ("127.0.0.1", 1),
                "server": ("127.0.0.1", 2),
                "state": {},
            },
        )
        cycle = RequestResponseCycle(
            scope,
            connection,
            transport,
            FlowControl(transport),
            logger,
            logger,
            False,
            [],
            asyncio.Event(),
            lambda: None,
        )
        await cycle.run_asgi(cast(ASGI3Application, diagnostic["app"]))
        assert cycle.response_complete
        return bytes(transport.output)

    try:
        response = asyncio.run(run())
        output = capsys.readouterr()
        assert CANARY not in output.out + output.err + response.decode()
        assert b"500 Internal Server Error" in response
        assert any(event["phase"] == "unhandled_error" for event in diagnostic["_events"])
    finally:
        engine.dispose()


@pytest.mark.skipif(NODE is None, reason="diagnostic subprocess checks require Node")
def test_diagnostic_api_discards_raw_logs_but_preserves_exit_status() -> None:
    program = r"""
const { spawn } = require("node:child_process");
const { readFileSync } = require("node:fs");
const source = readFileSync("scripts/run-e2e.mjs", "utf8");
const implementation = source.slice(
  source.indexOf("function start("),
  source.indexOf("async function assertCanaryAbsent"),
);
const start = new Function(
  "spawn",
  "repositoryRoot",
  "children",
  implementation + "; return start;",
)(spawn, process.cwd(), []);
const child = start(
  process.execPath,
  [
    "-e",
    "console.log(process.argv[1]); console.error(process.argv[1]); process.exit(7)",
    process.argv[1],
  ],
  process.env,
  true,
);
child.on("exit", (code) => console.log(JSON.stringify({ code })));
"""
    result = subprocess.run(
        [cast(str, NODE), "-e", program, CANARY],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == 0
    assert CANARY not in result.stdout + result.stderr
    assert json.loads(result.stdout) == {"code": 7}


_SPEC_PROBE = r"""
const fs = require("node:fs");
const ts = require("./apps/web/node_modules/typescript");
const scenario = process.argv[1];
const source = fs.readFileSync("apps/web/diagnostics/auth-timing.spec.ts", "utf8");
const code = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
}).outputText;
const cases = [],
  results = [],
  handlers = {};
let clock = 0,
  metricsCalls = 0;
const summaries = [
  { sample: 0, phase: "dropped", ms: 0 },
  { sample: 0, phase: "loop_lag_ms", ms: 1 },
];
const events = [
  "request_start_ms",
  "request_kind",
  "request_total_ms",
  "status",
  "executor_total_ms",
  "admission_ms",
  "pool_queue_ms",
  "worker_ms",
  "argon2_ms",
  "begin_immediate_ms",
].map((phase) => ({ sample: 7, phase, ms: phase === "status" ? 200 : 1 }));
let measured = [...events, ...summaries];
if (scenario === "empty") measured = [];
if (scenario.startsWith("missing:"))
  measured = measured.filter((event) => event.phase !== scenario.slice(8));
if (scenario === "wrong-status")
  measured.find((event) => event.phase === "status").ms = 401;
if (scenario === "wrong-sample")
  measured.find((event) => event.phase === "argon2_ms").sample = 8;
if (scenario === "error") measured.push({ sample: 0, phase: "unhandled_error", ms: 1 });
if (scenario === "dropped") measured.find((event) => event.phase === "dropped").ms = 1;
const request = { method: () => "POST", url: () => "http://127.0.0.1/api/v1/auth/login" };
const page = {
  on: (event, callback) => {
    handlers[event] = callback;
  },
  goto: async () => {},
  getByLabel: () => ({ fill: async () => {} }),
  getByRole: () => ({
    click: async () => {
      clock += 4000;
      handlers.request(request);
      handlers.response({ request: () => request, status: () => 200 });
      handlers.requestfinished(request);
    },
  }),
  request: {
    get: async () => ({
      status: () => 200,
      json: async () => ({ events: metricsCalls++ === 0 ? summaries : measured }),
    }),
  },
};
const expect = () => ({
  toBeVisible: async () => {
    clock += 4000;
  },
});
const mocks = {
  "@playwright/test": { expect, test: (title, callback) => cases.push(callback) },
  "node:fs/promises": {
    appendFile: async (path, text) => results.push(JSON.parse(text)),
  },
};
const environment = {
  env: {
    AGENTBOX_E2E_USERNAME: "synthetic",
    AGENTBOX_E2E_PASSWORD: "synthetic",
    AGENTBOX_E2E_TIMING_RESULTS: "unused",
    AGENTBOX_E2E_AUTH_TIMING: "1",
  },
};
new Function("require", "exports", "process", "performance", "console", code)(
  (name) => mocks[name],
  {},
  environment,
  { now: () => clock },
  { log: () => {} },
);
cases[0]({ page }, { project: { name: "desktop" } })
  .then(() => console.log(JSON.stringify(results[0])))
  .catch(() => (process.exitCode = 1));
"""


def run_spec_probe(scenario: str) -> dict[str, Any]:
    if NODE is None or not (ROOT / "apps/web/node_modules/typescript").exists():
        pytest.skip("diagnostic spec execution requires installed web dependencies and Node")
    result = subprocess.run(
        [NODE, "-e", _SPEC_PROBE, scenario],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == 0
    return cast(dict[str, Any], json.loads(result.stdout))


def test_actual_spec_distinguishes_total_visibility_from_assertion_timeout() -> None:
    result = run_spec_probe("complete")
    assert result["passed"] == result["assertion_within_5s"] == 1
    assert result["visible_ms"] == 8000
    assert result["ui_within_5s"] == 0


@pytest.mark.parametrize(
    "scenario",
    ["empty", "wrong-status", "wrong-sample", "error", "dropped"]
    + [
        f"missing:{phase}"
        for phase in (
            "request_start_ms",
            "request_kind",
            "request_total_ms",
            "status",
            "executor_total_ms",
            "admission_ms",
            "pool_queue_ms",
            "worker_ms",
            "argon2_ms",
            "begin_immediate_ms",
            "dropped",
            "loop_lag_ms",
        )
    ],
)
def test_actual_spec_rejects_incomplete_or_failed_diagnostics(scenario: str) -> None:
    result = run_spec_probe(scenario)
    assert result["passed"] == 0
    assert result["measurement_error"] == 1
