"""Source-only isolation gates for the synthetic S03 consumer slice.

These lexical/AST repository gates prevent accidental imports. They are not a
sandbox against malicious same-process code, computed module names or reflection.
"""

from __future__ import annotations

import ast
import hashlib
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PROTECTED_SOURCES = {
    "apps/web/src/features/content/a3Crypto.ts": (
        "d051081e9ca63e4ee1096cd07ecf2086" "e1f270289e895f53b7ae368b7bd7d867"
    ),
    "apps/web/src/features/workspace/noiseNx.ts": (
        "12d14afbb2609016d53cef0e88ca5a70" "b504406eeb29402ec0b208b04d6c4fce"
    ),
    "apps/web/src/features/workspace/wawCryptoContext.ts": (
        "6c5b19e1fc24ce4057850ad572f9ac1a" "05345b57dd2745c64acd9e73d3eb4c7b"
    ),
    "apps/web/src/features/workspace/wawCryptoProfile.ts": (
        "3162ef3d94264b3f7d4ca41cdd9af149" "e599b1b0359c9d19e66c47601456cf24"
    ),
    "packages/agentbox-protocol/src/agentbox_protocol/a3_content.py": (
        "90d667d36ddfe9e40122a284a60e94ad" "fea160515c68fb0e25f1a08b1c4a808f"
    ),
    "packages/agentbox-protocol/src/agentbox_protocol/a3_crypto.py": (
        "000a9a60235498ba0b580f724569634f" "c595ccda713b018efa3582e9a46351b1"
    ),
    "packages/agentbox-protocol/src/agentbox_protocol/noise_nx.py": (
        "9dbdfe4e56e321775ead8aa3ce219ee4" "68cf7dd5337d4b29c63d3e09218aba31"
    ),
    "packages/agentbox-protocol/src/agentbox_protocol/waw_crypto_context.py": (
        "02768d9d45e9097ef014fc0e4d09bf64" "d236c0fd443968d991ef402cccc96cab"
    ),
    "packages/agentbox-protocol/src/agentbox_protocol/waw_crypto_profile.py": (
        "2a1702370fd4a3921cbc43745006a807" "9e31110742d610c6b4703c2fae321d9e"
    ),
    "packages/agentbox-protocol/src/agentbox_protocol/waw_wire.py": (
        "8832cdef60ed6ed6b1c7c47c3bc4c8c9" "3ea26bdf1c3f92c3f46f4c13cae165a9"
    ),
    "packages/agentbox-runtime/src/agentbox_runtime/a3_content_session.py": (
        "912782244421a2d9b7d38b3a0580c770" "6d1af11756ca0dfc8119d9b003160863"
    ),
    "packages/agentbox-runtime/src/agentbox_runtime/kebui_admission.py": (
        "ca713c36104e304a6e6723ab131f962d" "b3251298930d832b99d7f33e9c0c79a0"
    ),
    "packages/agentbox-runtime/src/agentbox_runtime/kebui_admission_journal.py": (
        "f613074d1db4147e800e2cc16417da0e" "d302c495999464e9879cfac84c4f8a7f"
    ),
    "packages/agentbox-runtime/src/agentbox_runtime/kebui_content_admission.py": (
        "6b988fc06e884e35174a62bc1b02704b" "36acde455cdaa2b04468de3aaa1e0775"
    ),
}
PYTHON_ISOLATED = {
    "packages/agentbox-core/src/agentbox_core/kebui_observation.py",
    "packages/agentbox-protocol/src/agentbox_protocol/s03_submit.py",
    "packages/agentbox-runtime/src/agentbox_runtime/kebui_s03_submit.py",
    "packages/agentbox-runtime/src/agentbox_runtime/kebui_admission.py",
    "packages/agentbox-runtime/src/agentbox_runtime/kebui_admission_journal.py",
    "packages/agentbox-runtime/src/agentbox_runtime/kebui_content_admission.py",
}
PYTHON_MARKERS = (
    "kebui_observation",
    "kebui_admission",
    "kebui_content_admission",
    "s03_submit",
)
WEB_ISOLATED = {
    "apps/web/src/features/conversation/conversationObservation.ts",
    "apps/web/src/features/conversation/conversationObservation.test.ts",
    "apps/web/src/features/conversation/s03Submit.ts",
    "apps/web/src/features/conversation/s03Submit.test.ts",
}
WEB_MARKERS = ("conversationObservation", "s03Submit")


def _isolated_consumer(relative: str, text: str, *, web: bool = False) -> bool:
    permitted = WEB_ISOLATED if web else PYTHON_ISOLATED
    markers = WEB_MARKERS if web else PYTHON_MARKERS
    return relative in permitted or not any(marker in text for marker in markers)


def _imports(source: Path) -> set[str]:
    result: set[str] = set()
    for node in ast.walk(ast.parse(source.read_text())):
        if isinstance(node, ast.Call):
            name = (
                node.func.id
                if isinstance(node.func, ast.Name)
                else node.func.attr if isinstance(node.func, ast.Attribute) else ""
            )
            assert name not in {
                "__import__",
                "import_module",
            }, "no dynamic imports in the isolated profile"
            if isinstance(node.func, ast.Name):
                assert node.func.id not in {"eval", "exec", "compile"}, "no generated source"
        if isinstance(node, ast.Import):
            result.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert node.module is not None
            assert node.level <= 1, "no outward package traversal"
            result.add("." * node.level + node.module)
    return result


def test_original_primitives_profiles_and_authorities_are_byte_identical() -> None:
    for relative, expected in PROTECTED_SOURCES.items():
        assert hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() == expected, relative


def test_only_exact_isolated_python_sources_consume_kebui_contracts() -> None:
    assert all((ROOT / relative).is_file() for relative in PYTHON_ISOLATED)
    for directory in ("apps", "packages", "helper", "installer"):
        for source in (ROOT / directory).rglob("*.py"):
            if "node_modules" in source.parts:
                continue
            relative = source.relative_to(ROOT).as_posix()
            assert _isolated_consumer(relative, source.read_text()), relative


def test_only_exact_web_source_and_test_files_consume_synthetic_profile() -> None:
    assert all((ROOT / relative).is_file() for relative in WEB_ISOLATED)
    for directory in ("apps/web/src", "clients/browser-trust/extension/src"):
        for source in (ROOT / directory).rglob("*"):
            if source.suffix not in (".ts", ".tsx", ".js", ".jsx"):
                continue
            relative = source.relative_to(ROOT).as_posix()
            assert _isolated_consumer(relative, source.read_text(), web=True), relative


@pytest.mark.parametrize(
    "injected",
    [
        "import agentbox_protocol.s03_submit",
        "from agentbox_protocol import s03_submit as wire",
        "from agentbox_protocol.s03_submit import *",
        "from . import s03_submit",
        "__import__('agentbox_protocol.s03_submit')",
        "importlib.import_module('agentbox_runtime.kebui_s03_submit')",
        "from agentbox_runtime import kebui_content_admission",
        "from agentbox_core.kebui_observation import parse_scope",
    ],
)
def test_python_production_import_mutations_are_rejected(injected: str) -> None:
    ast.parse(injected)
    assert not _isolated_consumer("apps/api/src/agentbox_api/injected.py", injected)


@pytest.mark.parametrize(
    "injected",
    [
        "import './s03Submit'",
        "import { SyntheticS03TestRoot } from './s03Submit'",
        "import type { SyntheticS03TestRoot } from './s03Submit'",
        "export * from './s03Submit'",
        "export { SyntheticS03TestRoot as root } from './s03Submit'",
        "const wire = import('./s03Submit')",
        "const wire = require('./s03Submit')",
        "import { parseConversationScope } from './conversationObservation'",
    ],
)
def test_web_production_import_mutations_are_rejected(injected: str) -> None:
    assert not _isolated_consumer("apps/web/src/pages/Injected.tsx", injected, web=True)


def _web_imports(text: str) -> set[str]:
    # This profile has only two static imports. Reject dynamic literal/computed
    # import/require alike rather than attempting to execute/resolve expressions.
    assert not re.search(r"\b(?:import|require)\s*\(", text), "no dynamic module loading"
    return set(re.findall(r"(?:\bfrom\s*|\bimport\s*)['\"]([^'\"]+)['\"]", text))


def test_new_web_sender_has_only_reviewed_pure_dependencies() -> None:
    source = ROOT / "apps/web/src/features/conversation/s03Submit.ts"
    text = source.read_text()
    assert _web_imports(text) == {"../workspace/noiseNx", "./conversationObservation"}
    for token in (
        "localStorage",
        "sessionStorage",
        "indexedDB",
        "XMLHttpRequest",
        "WebSocket",
        "fetch(",
    ):
        assert token not in text, token


@pytest.mark.parametrize(
    "injected",
    [
        "import '../../../lib/api'",
        "import { api } from '../../../lib/api'",
        "import type { Api } from '../../../lib/api'",
        "export * from '../../../lib/api'",
        "export { api as source } from '../../../lib/api'",
        "const api = import('../../../lib/api')",
        "const api = import(moduleName)",
        "const api = require('../../../lib/api')",
        "const api = require(moduleName)",
    ],
)
def test_web_outward_import_mutations_are_rejected(injected: str) -> None:
    rejected = False
    try:
        rejected = not _web_imports(injected) <= {
            "../workspace/noiseNx",
            "./conversationObservation",
        }
    except AssertionError:
        rejected = True
    assert rejected


@pytest.mark.parametrize(
    "injected",
    [
        "import subprocess",
        "from subprocess import run",
        "from subprocess import *",
        "__import__('subprocess')",
        "__import__(module_name)",
        "importlib.import_module('subprocess')",
        "importlib.import_module(module_name)",
        "eval(source)",
        "exec(source)",
    ],
)
def test_python_outward_import_mutations_are_rejected(injected: str, tmp_path: Path) -> None:
    source = tmp_path / "isolated.py"
    source.write_text(injected)
    rejected = False
    try:
        rejected = not _imports(source) <= {"agentbox_protocol.s03_submit"}
    except AssertionError:
        rejected = True
    assert rejected


def test_s03_protocol_has_only_exact_metadata_primitive_dependencies() -> None:
    assert _imports(ROOT / "packages/agentbox-protocol/src/agentbox_protocol/s03_submit.py") == {
        "__future__",
        "base64",
        "contextlib",
        "hashlib",
        "re",
        "dataclasses",
        "typing",
        "agentbox_core.kebui_observation",
        ".noise_nx",
    }


def test_s03_runtime_has_only_exact_isolated_composition_dependencies() -> None:
    assert _imports(
        ROOT / "packages/agentbox-runtime/src/agentbox_runtime/kebui_s03_submit.py"
    ) == {
        "__future__",
        "asyncio",
        "json",
        "os",
        "re",
        "threading",
        "time",
        "collections.abc",
        "contextlib",
        "dataclasses",
        "pathlib",
        "typing",
        "agentbox_core.kebui_observation",
        "agentbox_protocol.s03_submit",
        ".kebui_admission",
        ".kebui_admission_journal",
        ".kebui_content_admission",
    }
