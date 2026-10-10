"""Pure, synthetic K2 metadata validation; no production conversation admission."""

from __future__ import annotations

import ast
import copy
import json
import traceback
from collections import UserDict
from dataclasses import FrozenInstanceError, asdict, fields, is_dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any

import pytest
from agentbox_core import kebui_observation
from agentbox_core.kebui_observation import (
    ConversationObservation,
    ConversationScope,
    KebuiObservationError,
    ObservationStatus,
    parse_observation,
    parse_scope,
)
from agentbox_core.waw import AgentType

ROOT = Path(__file__).resolve().parents[2]
VECTORS = json.loads((ROOT / "tests/fixtures/kebui_observation/v1.json").read_text())
SCOPE_FIELDS = (
    "owner_scope",
    "auth_epoch",
    "project_id",
    "project_revision",
    "binding_revision",
    "binding_digest",
    "host_id",
    "host_revision",
    "runtime_epoch",
    "api_authority_epoch",
    "agent_type",
    "execution_kind",
    "conversation_id",
    "conversation_revision",
    "generation",
    "turn_id",
)
COUNTER_FIELDS = (
    "auth_epoch",
    "project_revision",
    "binding_revision",
    "host_revision",
    "runtime_epoch",
    "api_authority_epoch",
    "conversation_revision",
    "generation",
)


def observation() -> dict[str, Any]:
    return copy.deepcopy(VECTORS["base"])


@pytest.mark.parametrize("vector", VECTORS["valid"], ids=lambda item: item["name"])
def test_shared_valid_vectors(vector: dict[str, Any]) -> None:
    value = vector["value"]
    parsed = parse_observation(value)
    assert isinstance(parsed, ConversationObservation)
    assert isinstance(parsed.scope, ConversationScope)
    assert isinstance(parsed.scope.agent_type, AgentType)
    assert isinstance(parsed.status, ObservationStatus)
    assert asdict(parsed) == value
    assert asdict(parse_scope(value["scope"])) == value["scope"]


@pytest.mark.parametrize("mutation", VECTORS["invalid_mutations"], ids=lambda item: item["name"])
def test_shared_invalid_vectors(mutation: dict[str, Any]) -> None:
    value = observation()
    target = value
    for key in mutation["path"][:-1]:
        target = target[key]
    key = mutation["path"][-1]
    if mutation["op"] == "delete":
        del target[key]
    else:
        assert mutation["op"] == "set"
        target[key] = mutation["value"]
    with pytest.raises(KebuiObservationError):
        parse_observation(value)
    if mutation["path"][0] == "scope":
        with pytest.raises(KebuiObservationError):
            parse_scope(value.get("scope"))


@pytest.mark.parametrize("field", SCOPE_FIELDS)
@pytest.mark.parametrize("invalid", [None, True, False, 1, 1.0, [], {}, (), b"1"])
def test_each_scope_field_requires_plain_string(field: str, invalid: object) -> None:
    value = observation()
    value["scope"][field] = invalid
    with pytest.raises(KebuiObservationError):
        parse_scope(value["scope"])
    with pytest.raises(KebuiObservationError):
        parse_observation(value)


@pytest.mark.parametrize("field", ("revision", "status"))
@pytest.mark.parametrize("invalid", [None, True, False, 1, 1.0, [], {}, (), b"1"])
def test_each_observation_scalar_requires_plain_string(field: str, invalid: object) -> None:
    value = observation()
    value[field] = invalid
    with pytest.raises(KebuiObservationError):
        parse_observation(value)


@pytest.mark.parametrize("field", SCOPE_FIELDS)
def test_each_scope_field_is_required(field: str) -> None:
    scope = observation()["scope"]
    del scope[field]
    with pytest.raises(KebuiObservationError):
        parse_scope(scope)


@pytest.mark.parametrize("field", ("scope", "revision", "status"))
def test_each_observation_field_is_required(field: str) -> None:
    value = observation()
    del value[field]
    with pytest.raises(KebuiObservationError):
        parse_observation(value)


@pytest.mark.parametrize("field", COUNTER_FIELDS + ("revision",))
@pytest.mark.parametrize(
    "invalid",
    [
        "0",
        "00",
        "01",
        "+1",
        "-1",
        " 1",
        "1 ",
        "1\n",
        "1\x00",
        "1.0",
        "1e1",
        "\u0661",
        "\uff11",
        "18446744073709551616",
        "9" * 10_000,
    ],
)
def test_counter_rejects_noncanonical_or_out_of_range(field: str, invalid: str) -> None:
    value = observation()
    target = value if field == "revision" else value["scope"]
    target[field] = invalid
    with pytest.raises(KebuiObservationError):
        parse_observation(value)


@pytest.mark.parametrize("counter", ["1", "9007199254740993", "18446744073709551615"])
def test_counter_boundaries_remain_exact_strings(counter: str) -> None:
    value = observation()
    for field in COUNTER_FIELDS:
        value["scope"][field] = counter
    value["revision"] = counter
    result = asdict(parse_observation(value))
    assert result == value
    assert type(result["revision"]) is str
    assert all(type(result["scope"][field]) is str for field in COUNTER_FIELDS)


@pytest.mark.parametrize("invalid", [None, True, 1, 1.0, "{}", b"{}", [], (), set()])
def test_parsers_do_not_decode_or_coerce_nonobjects(invalid: object) -> None:
    with pytest.raises(KebuiObservationError):
        parse_scope(invalid)
    with pytest.raises(KebuiObservationError):
        parse_observation(invalid)


class DictSubclass(dict[str, object]):
    def __len__(self) -> int:
        raise AssertionError("custom object behavior was executed")


class StringSubclass(str):
    def __str__(self) -> str:
        raise AssertionError("custom string behavior was executed")


@pytest.mark.parametrize("wrapper", [DictSubclass, UserDict, MappingProxyType])
def test_only_plain_dict_is_admitted(wrapper: Any) -> None:
    value = observation()
    with pytest.raises(KebuiObservationError):
        parse_scope(wrapper(value["scope"]))
    with pytest.raises(KebuiObservationError):
        parse_observation(wrapper(value))
    value["scope"] = wrapper(value["scope"])
    with pytest.raises(KebuiObservationError):
        parse_observation(value)


@pytest.mark.parametrize("field", SCOPE_FIELDS + ("revision", "status"))
def test_string_subclasses_are_not_decoded_metadata(field: str) -> None:
    value = observation()
    target = value if field in ("revision", "status") else value["scope"]
    target[field] = StringSubclass(target[field])
    with pytest.raises(KebuiObservationError):
        parse_observation(value)


@pytest.mark.parametrize("field", SCOPE_FIELDS)
def test_scope_keys_must_be_plain_strings(field: str) -> None:
    scope = observation()["scope"]
    scope[StringSubclass(field)] = scope.pop(field)
    with pytest.raises(KebuiObservationError):
        parse_scope(scope)


@pytest.mark.parametrize("field", ("scope", "revision", "status"))
def test_observation_keys_must_be_plain_strings(field: str) -> None:
    value = observation()
    value[StringSubclass(field)] = value.pop(field)
    with pytest.raises(KebuiObservationError):
        parse_observation(value)


@pytest.mark.parametrize(
    "extra",
    [
        "body",
        "prompt",
        "output",
        "title",
        "summary",
        "tool_arguments",
        "approval",
        "vendor_handle",
        "workspace_id",
        "attachment_id",
        "__proto__",
        "constructor",
        17,
    ],
)
def test_no_seventeenth_scope_field_or_fourth_observation_field(extra: object) -> None:
    value = observation()
    value["scope"][extra] = "synthetic-content-canary"
    with pytest.raises(KebuiObservationError):
        parse_scope(value["scope"])
    with pytest.raises(KebuiObservationError):
        parse_observation(value)
    value = observation()
    value[extra] = "synthetic-content-canary"  # type: ignore[index]
    with pytest.raises(KebuiObservationError):
        parse_observation(value)


def test_output_is_copied_frozen_and_has_exact_metadata_fields() -> None:
    value = observation()
    before = copy.deepcopy(value)
    parsed = parse_observation(value)
    same = parse_observation(value)
    scope = parse_scope(value["scope"])
    assert is_dataclass(parsed) and is_dataclass(scope)
    assert len(fields(scope)) == 16
    assert {field.name for field in fields(scope)} == set(SCOPE_FIELDS)
    assert {field.name for field in fields(parsed)} == {"scope", "revision", "status"}
    assert parsed == same and parsed is not same
    assert parsed.scope == scope and parsed.scope is not scope
    assert parsed.scope is not same.scope
    assert hash(parsed) == hash(same)
    assert value == before
    value["scope"]["owner_scope"] = "f" * 64
    value["scope"].clear()
    value.clear()
    assert asdict(parsed) == before
    assert asdict(scope) == before["scope"]
    with pytest.raises(FrozenInstanceError):
        parsed.status = ObservationStatus.FAILED  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        parsed.scope.generation = "100"  # type: ignore[misc]
    assert not hasattr(parsed, "__dict__")
    assert not hasattr(scope, "__dict__")


@pytest.mark.parametrize("field", SCOPE_FIELDS + ("revision", "status"))
def test_errors_never_echo_rejected_values(field: str) -> None:
    value = observation()
    target = value if field in ("revision", "status") else value["scope"]
    target[field] = "synthetic-private-canary-<script>\nnot metadata"
    with pytest.raises(KebuiObservationError) as error:
        parse_observation(value)
    assert str(error.value) in {"invalid observation", "invalid observation scope"}
    assert "synthetic-private-canary" not in repr(error.value)
    assert "synthetic-private-canary" not in "".join(traceback.format_exception(error.value))


def test_unknown_keys_and_arbitrary_objects_are_not_formatted() -> None:
    class Unprintable:
        def __repr__(self) -> str:
            raise AssertionError("input was formatted")

        def __str__(self) -> str:
            raise AssertionError("input was formatted")

    value = observation()
    del value["scope"]["owner_scope"]
    value["scope"][Unprintable()] = Unprintable()
    with pytest.raises(KebuiObservationError):
        parse_observation(value)
    for field in SCOPE_FIELDS:
        value = observation()
        value["scope"][field] = Unprintable()
        with pytest.raises(KebuiObservationError):
            parse_observation(value)


def test_recursive_input_is_not_traversed() -> None:
    value = observation()
    value["scope"] = value
    with pytest.raises(KebuiObservationError):
        parse_observation(value)
    value = observation()
    value["scope"]["generation"] = value["scope"]
    with pytest.raises(KebuiObservationError):
        parse_scope(value["scope"])


@pytest.mark.parametrize("field", SCOPE_FIELDS + ("revision", "status"))
def test_oversized_metadata_string_fails_closed(field: str) -> None:
    value = observation()
    target = value if field in ("revision", "status") else value["scope"]
    target[field] = "9" * 10_000
    with pytest.raises(KebuiObservationError):
        parse_observation(value)


def test_no_production_import_and_only_pure_declared_dependencies() -> None:
    module = ROOT / "packages/agentbox-core/src/agentbox_core/kebui_observation.py"
    assert Path(kebui_observation.__file__).resolve() == module.resolve()
    tree = ast.parse(module.read_text())
    imports: set[str | None] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.add(node.module)
            if node.module == "agentbox_core.waw":
                assert {alias.name for alias in node.names} == {
                    "AgentType",
                    "WAWDomainError",
                    "validate_binding_digest",
                    "validate_positive_u64",
                    "validate_project_id",
                    "validate_runtime_host_installation_id",
                }
    assert imports <= {"__future__", "dataclasses", "enum", "re", "typing", "agentbox_core.waw"}
    # Only these isolated metadata consumers may reuse the pure scope validator.
    # None may acquire a production consumer, including via the journal module.
    isolated = {
        module,
        ROOT / "packages/agentbox-runtime/src/agentbox_runtime/kebui_admission.py",
        ROOT / "packages/agentbox-runtime/src/agentbox_runtime/kebui_admission_journal.py",
    }
    assert all(source.is_file() for source in isolated)
    forbidden = ("kebui_observation", "kebui_admission", "kebui_admission_journal")
    for directory in ("apps", "packages", "helper", "installer"):
        for source in (ROOT / directory).rglob("*.py"):
            if source in isolated or "node_modules" in source.parts:
                continue
            text = source.read_text()
            assert all(token not in text for token in forbidden), source.relative_to(ROOT)
