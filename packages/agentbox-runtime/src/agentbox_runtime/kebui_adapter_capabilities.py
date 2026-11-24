"""Read-only, pinned K2 operation research; no executable adapter or authority.

The three evidence domains intentionally cannot promote one another. This module
has no vendor dependency, probe, transport, process, content, or credential input.
Every assessment denies execution, including exact matches to researched sources.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Literal


class CapabilityState(StrEnum):
    SUPPORTED = "supported"
    UNSUPPORTED = "unsupported"
    UNKNOWN = "unknown"
    STALE = "stale"


class EvidenceDomain(StrEnum):
    SOURCE_RESEARCH = "source_research"
    SOFTWARE_QUALIFICATION = "software_qualification"
    HOST_QUALIFICATION = "host_qualification"


class AdapterOperation(StrEnum):
    OPEN_SESSION = "open_session"
    START_TURN = "start_turn"
    OBSERVE_OUTPUT = "observe_output"
    RESPOND_APPROVAL = "respond_approval"
    RESPOND_QUESTION = "respond_question"
    INTERRUPT_TURN = "interrupt_turn"
    READ_HISTORY = "read_history"
    RESUME_SESSION = "resume_session"
    STEER_TURN = "steer_turn"
    FORK_THREAD = "fork_thread"
    ROLLBACK_THREAD = "rollback_thread"
    QUEUE_TURN = "queue_turn"


class AckMeaning(StrEnum):
    PROTOCOL_REPLY_ONLY = "protocol_reply_only"
    LOCAL_WRITE_ONLY = "local_write_only"
    OBSERVATION_ONLY = "observation_only"
    NOT_ESTABLISHED = "not_established"


class TerminalRule(StrEnum):
    MATCHED_TURN_EVENT_REQUIRED = "matched_turn_event_required"
    CORRELATED_RESULT_REQUIRED = "correlated_result_required"
    NOT_TURN_TERMINAL = "not_turn_terminal"
    NOT_ESTABLISHED = "not_established"


class RecoveryRule(StrEnum):
    NO_AUTOMATIC_REPLAY = "no_automatic_replay"
    FRESH_AUTHORIZED_READ = "fresh_authorized_read"
    NEVER_REPLAY_RESPONSE = "never_replay_response"
    OUT_OF_PROFILE = "out_of_profile"


class FindingCode(StrEnum):
    PINNED_SOURCE_SURFACE = "pinned_source_surface"
    SOURCE_NOT_ESTABLISHED = "source_not_established"
    SOFTWARE_NOT_QUALIFIED = "software_not_qualified"
    HOST_NOT_QUALIFIED = "host_not_qualified"
    OUT_OF_PROFILE = "out_of_profile"
    UNKNOWN_AGENT = "unknown_agent"
    UNKNOWN_OPERATION = "unknown_operation"
    MISSING_IDENTITY = "missing_identity"
    IDENTITY_MISMATCH = "identity_mismatch"
    APPROVAL_DEADLINE_UNQUALIFIED = "approval_deadline_unqualified"


class CapabilityContractError(ValueError):
    """Bounded error that never includes caller-supplied values."""


@dataclass(frozen=True, slots=True)
class SourceAnchor:
    path: str
    symbol: str
    git_blob_oid: str


@dataclass(frozen=True, slots=True)
class OperationContract:
    operation: AdapterOperation
    native_surface: str | None
    input_requirements: tuple[str, ...]
    acknowledgment: AckMeaning
    terminal: TerminalRule
    recovery: RecoveryRule
    research_state: CapabilityState
    initial_k2_scope: bool
    source_anchors: tuple[SourceAnchor, ...]
    unresolved_requirements: tuple[str, ...]

    @property
    def acknowledgment_proves_terminal(self) -> Literal[False]:
        return False


@dataclass(frozen=True, slots=True)
class AdapterProfile:
    agent: str
    profile_id: str
    executable_version: str
    source_repository: str
    source_revision: str
    sdk_version: str | None
    operations: tuple[OperationContract, ...]


_LABEL = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+-]{0,79}\Z", re.ASCII)
_COMMIT = re.compile(r"[0-9a-f]{40}\Z", re.ASCII)


@dataclass(frozen=True, slots=True)
class AdapterSelection:
    """Untrusted identity hints for comparison, never installation/host evidence."""

    agent: str
    profile_id: str | None = None
    executable_version: str | None = None
    source_revision: str | None = None
    sdk_version: str | None = None

    def __post_init__(self) -> None:
        for value in (self.agent, self.profile_id, self.executable_version, self.sdk_version):
            if value is not None and (type(value) is not str or _LABEL.fullmatch(value) is None):
                raise CapabilityContractError("invalid_adapter_selection")
        if self.agent is None or (
            self.source_revision is not None
            and (
                type(self.source_revision) is not str
                or _COMMIT.fullmatch(self.source_revision) is None
            )
        ):
            raise CapabilityContractError("invalid_adapter_selection")


@dataclass(frozen=True, slots=True)
class EvidenceFinding:
    domain: EvidenceDomain
    state: CapabilityState
    code: FindingCode


@dataclass(frozen=True, slots=True)
class CapabilityAssessment:
    state: CapabilityState
    identity_state: CapabilityState
    profile: AdapterProfile | None
    contract: OperationContract | None
    source_research: EvidenceFinding
    software_qualification: EvidenceFinding
    host_qualification: EvidenceFinding
    blockers: tuple[FindingCode, ...]

    @property
    def execution_allowed(self) -> Literal[False]:
        """A descriptor cannot become a dispatch permit, even for a known method."""
        return False


_CODEX_TURN = SourceAnchor(
    "codex-rs/app-server-protocol/src/protocol/v2/turn.rs",
    "TurnStartParams; TurnStartResponse; TurnInterruptParams; TurnCompletedNotification",
    "f938d179e697fa116666d6673ec249805f6f614e",
)
_CODEX_THREAD = SourceAnchor(
    "codex-rs/app-server-protocol/src/protocol/v2/thread.rs",
    "ThreadStartParams; ThreadResumeParams; ThreadReadParams; ThreadForkParams",
    "2e166d5506b10996e2da286feb6082d6b8711340",
)
_CODEX_ITEM = SourceAnchor(
    "codex-rs/app-server-protocol/src/protocol/v2/item.rs",
    "AgentMessageDeltaNotification; CommandExecutionRequestApprovalParams; "
    "ToolRequestUserInputParams",
    "04f68a3351c765d6c2be8d492b1a3cded43a22bb",
)
_CODEX_METHODS = SourceAnchor(
    "codex-rs/app-server-protocol/src/protocol/common.rs",
    "ClientRequest; ServerRequest; ServerNotification",
    "c37c4956f1c3cbf21f293ca2aa41a6fec209bcfa",
)
_CLAUDE_CLIENT = SourceAnchor(
    "src/claude_agent_sdk/client.py",
    "ClaudeSDKClient.connect; query; receive_messages; receive_response; interrupt",
    "a9c11f0cd93cb7420510e58c12dec5fda6af7bbd",
)
_CLAUDE_QUERY = SourceAnchor(
    "src/claude_agent_sdk/_internal/query.py",
    "Query._handle_control_request; _send_control_request; interrupt; "
    "wait_for_result_and_end_input",
    "6019124aadd73b10d0822120a4b6392c70cea450",
)
_CLAUDE_TYPES = SourceAnchor(
    "src/claude_agent_sdk/types.py",
    "ResultMessage; StreamEvent; ClaudeAgentOptions; PermissionResultAllow; PermissionResultDeny",
    "882cc8040c9549a12cd21cc4195455056703a07a",
)
_CLAUDE_SESSIONS = SourceAnchor(
    "src/claude_agent_sdk/_internal/sessions.py",
    "get_session_messages; get_session_messages_from_store",
    "ed4f30aa4ee484808c84d171fc5bd03e6c289fb6",
)

_OWNED_EXECUTION = (
    "exact_runtime_owner_and_generation",
    "formal_project_and_workspace_binding",
    "single_writer_across_tui_and_structured_channels",
    "authenticated_content_source",
)
_APPROVAL_REQUIREMENTS = (
    "exact_pending_request_and_revision",
    "qualified_source_deadline_capped_at_60_seconds",
    "current_owner_and_one_shot_response",
    "explicit_decline_without_terminal_input_fallback",
)


def _contract(
    operation: AdapterOperation,
    native_surface: str | None,
    inputs: tuple[str, ...],
    acknowledgment: AckMeaning,
    terminal: TerminalRule,
    recovery: RecoveryRule,
    anchors: tuple[SourceAnchor, ...],
    requirements: tuple[str, ...],
    *,
    initial_k2_scope: bool = True,
) -> OperationContract:
    return OperationContract(
        operation=operation,
        native_surface=native_surface,
        input_requirements=inputs,
        acknowledgment=acknowledgment,
        terminal=terminal,
        recovery=recovery,
        research_state=(
            CapabilityState.SUPPORTED if native_surface is not None else CapabilityState.UNKNOWN
        ),
        initial_k2_scope=initial_k2_scope,
        source_anchors=anchors,
        unresolved_requirements=requirements,
    )


_CODEX_OPERATIONS = (
    _contract(
        AdapterOperation.OPEN_SESSION,
        "thread/start",
        ("runtime_resolved_workspace", "fixed_model_and_permission_policy"),
        AckMeaning.PROTOCOL_REPLY_ONLY,
        TerminalRule.NOT_TURN_TERMINAL,
        RecoveryRule.NO_AUTOMATIC_REPLAY,
        (_CODEX_THREAD, _CODEX_METHODS),
        _OWNED_EXECUTION,
    ),
    _contract(
        AdapterOperation.START_TURN,
        "turn/start",
        ("threadId", "input", "runtime_proven_no_active_turn"),
        AckMeaning.PROTOCOL_REPLY_ONLY,
        TerminalRule.MATCHED_TURN_EVENT_REQUIRED,
        RecoveryRule.NO_AUTOMATIC_REPLAY,
        (_CODEX_TURN, _CODEX_METHODS),
        (*_OWNED_EXECUTION, "durable_acceptance_and_dispatch_fence", "busy_must_not_become_steer"),
    ),
    _contract(
        AdapterOperation.OBSERVE_OUTPUT,
        "item/agentMessage/delta; item/completed; turn/completed",
        ("threadId", "turnId", "itemId_when_present"),
        AckMeaning.OBSERVATION_ONLY,
        TerminalRule.MATCHED_TURN_EVENT_REQUIRED,
        RecoveryRule.FRESH_AUTHORIZED_READ,
        (_CODEX_ITEM, _CODEX_TURN, _CODEX_METHODS),
        ("authenticated_current_source", "content_stays_out_of_metadata", "event_gap_detection"),
    ),
    _contract(
        AdapterOperation.RESPOND_APPROVAL,
        "item/commandExecution/requestApproval; item/fileChange/requestApproval",
        ("rpc_request_id", "threadId", "turnId", "itemId", "native_decision"),
        AckMeaning.LOCAL_WRITE_ONLY,
        TerminalRule.NOT_TURN_TERMINAL,
        RecoveryRule.NEVER_REPLAY_RESPONSE,
        (_CODEX_ITEM, _CODEX_METHODS),
        _APPROVAL_REQUIREMENTS,
    ),
    _contract(
        AdapterOperation.RESPOND_QUESTION,
        "item/tool/requestUserInput",
        ("rpc_request_id", "threadId", "turnId", "itemId", "question_ids_and_answers"),
        AckMeaning.LOCAL_WRITE_ONLY,
        TerminalRule.NOT_TURN_TERMINAL,
        RecoveryRule.OUT_OF_PROFILE,
        (_CODEX_ITEM, _CODEX_METHODS),
        ("separate_question_schema_and_content_policy",),
        initial_k2_scope=False,
    ),
    _contract(
        AdapterOperation.INTERRUPT_TURN,
        "turn/interrupt",
        ("threadId", "turnId", "runtime_owner_and_generation"),
        AckMeaning.PROTOCOL_REPLY_ONLY,
        TerminalRule.MATCHED_TURN_EVENT_REQUIRED,
        RecoveryRule.NO_AUTOMATIC_REPLAY,
        (_CODEX_TURN, _CODEX_METHODS),
        ("exact_live_turn_guard", "positive_terminal_event", "no_process_exit_inference"),
    ),
    _contract(
        AdapterOperation.READ_HISTORY,
        "thread/read; thread/turns/list; thread/items/list",
        ("threadId", "bounded_authorized_pagination"),
        AckMeaning.OBSERVATION_ONLY,
        TerminalRule.NOT_TURN_TERMINAL,
        RecoveryRule.FRESH_AUTHORIZED_READ,
        (_CODEX_THREAD, _CODEX_METHODS),
        ("content_read_authorization", "bounded_retention", "history_is_not_live_terminal_proof"),
    ),
    _contract(
        AdapterOperation.RESUME_SESSION,
        "thread/resume",
        ("threadId", "runtime_owned_workspace_and_execution"),
        AckMeaning.PROTOCOL_REPLY_ONLY,
        TerminalRule.NOT_TURN_TERMINAL,
        RecoveryRule.NO_AUTOMATIC_REPLAY,
        (_CODEX_THREAD, _CODEX_METHODS),
        (*_OWNED_EXECUTION, "unknown_delivery_never_resubmits_prompt"),
    ),
    _contract(
        AdapterOperation.STEER_TURN,
        "turn/steer",
        ("threadId", "expectedTurnId", "input"),
        AckMeaning.PROTOCOL_REPLY_ONLY,
        TerminalRule.MATCHED_TURN_EVENT_REQUIRED,
        RecoveryRule.OUT_OF_PROFILE,
        (_CODEX_TURN, _CODEX_METHODS),
        ("explicit_future_steer_contract",),
        initial_k2_scope=False,
    ),
    _contract(
        AdapterOperation.FORK_THREAD,
        "thread/fork",
        ("threadId", "qualified_fork_point"),
        AckMeaning.PROTOCOL_REPLY_ONLY,
        TerminalRule.NOT_TURN_TERMINAL,
        RecoveryRule.OUT_OF_PROFILE,
        (_CODEX_THREAD, _CODEX_METHODS),
        ("conversation_workspace_checkpoint_consistency",),
        initial_k2_scope=False,
    ),
    _contract(
        AdapterOperation.ROLLBACK_THREAD,
        None,
        ("qualified_conversation_and_workspace_checkpoint",),
        AckMeaning.NOT_ESTABLISHED,
        TerminalRule.NOT_ESTABLISHED,
        RecoveryRule.OUT_OF_PROFILE,
        (_CODEX_METHODS,),
        ("fixed_vendor_rollback_surface_not_established",),
        initial_k2_scope=False,
    ),
    _contract(
        AdapterOperation.QUEUE_TURN,
        None,
        ("explicit_durable_task_identity",),
        AckMeaning.NOT_ESTABLISHED,
        TerminalRule.NOT_ESTABLISHED,
        RecoveryRule.OUT_OF_PROFILE,
        (),
        ("separate_k3_task_and_queue_contract",),
        initial_k2_scope=False,
    ),
)

_CLAUDE_OPERATIONS = (
    _contract(
        AdapterOperation.OPEN_SESSION,
        "ClaudeSDKClient.connect",
        ("runtime_resolved_workspace", "fixed_options", "no_initial_prompt"),
        AckMeaning.PROTOCOL_REPLY_ONLY,
        TerminalRule.NOT_TURN_TERMINAL,
        RecoveryRule.NO_AUTOMATIC_REPLAY,
        (_CLAUDE_CLIENT, _CLAUDE_QUERY),
        _OWNED_EXECUTION,
    ),
    _contract(
        AdapterOperation.START_TURN,
        "ClaudeSDKClient.query",
        ("session_id", "prompt", "runtime_proven_no_active_turn"),
        AckMeaning.LOCAL_WRITE_ONLY,
        TerminalRule.CORRELATED_RESULT_REQUIRED,
        RecoveryRule.NO_AUTOMATIC_REPLAY,
        (_CLAUDE_CLIENT, _CLAUDE_TYPES),
        (*_OWNED_EXECUTION, "vendor_ack_not_established", "exact_prompt_result_correlation"),
    ),
    _contract(
        AdapterOperation.OBSERVE_OUTPUT,
        "ClaudeSDKClient.receive_messages; StreamEvent; ResultMessage",
        ("session_id", "qualified_prompt_origin_and_message_identity"),
        AckMeaning.OBSERVATION_ONLY,
        TerminalRule.CORRELATED_RESULT_REQUIRED,
        RecoveryRule.FRESH_AUTHORIZED_READ,
        (_CLAUDE_CLIENT, _CLAUDE_TYPES, _CLAUDE_QUERY),
        (
            "authenticated_current_source",
            "content_stays_out_of_metadata",
            "partial_events_require_include_partial_messages",
            "result_is_not_entire_run_end",
            "success_subtype_is_not_success_proof",
        ),
    ),
    _contract(
        AdapterOperation.RESPOND_APPROVAL,
        "can_use_tool; control_response",
        ("control_request_id", "tool_use_id_when_present", "allow_or_deny"),
        AckMeaning.LOCAL_WRITE_ONLY,
        TerminalRule.NOT_TURN_TERMINAL,
        RecoveryRule.NEVER_REPLAY_RESPONSE,
        (_CLAUDE_QUERY, _CLAUDE_TYPES),
        (*_APPROVAL_REQUIREMENTS, "control_wait_timeout_is_not_approval_deadline"),
    ),
    _contract(
        AdapterOperation.RESPOND_QUESTION,
        None,
        ("qualified_question_identity_and_answers",),
        AckMeaning.NOT_ESTABLISHED,
        TerminalRule.NOT_ESTABLISHED,
        RecoveryRule.OUT_OF_PROFILE,
        (_CLAUDE_TYPES,),
        ("separate_question_schema_and_content_policy",),
        initial_k2_scope=False,
    ),
    _contract(
        AdapterOperation.INTERRUPT_TURN,
        "ClaudeSDKClient.interrupt",
        ("runtime_owned_session", "runtime_owner_and_generation"),
        AckMeaning.PROTOCOL_REPLY_ONLY,
        TerminalRule.CORRELATED_RESULT_REQUIRED,
        RecoveryRule.NO_AUTOMATIC_REPLAY,
        (_CLAUDE_CLIENT, _CLAUDE_QUERY, _CLAUDE_TYPES),
        (
            "native_control_has_no_turn_id",
            "exact_live_turn_guard",
            "qualified_cancel_reason_and_prompt_correlation",
            "background_task_lifetime_separate",
        ),
    ),
    _contract(
        AdapterOperation.READ_HISTORY,
        "get_session_messages",
        ("session_id", "runtime_resolved_project_directory", "bounded_limit_and_offset"),
        AckMeaning.OBSERVATION_ONLY,
        TerminalRule.NOT_TURN_TERMINAL,
        RecoveryRule.FRESH_AUTHORIZED_READ,
        (_CLAUDE_SESSIONS,),
        (
            "no_cross_project_home_scan",
            "content_read_authorization",
            "empty_history_is_not_absence_or_cancellation_proof",
            "bounded_retention",
        ),
    ),
    _contract(
        AdapterOperation.RESUME_SESSION,
        "ClaudeAgentOptions.resume; ClaudeSDKClient.connect",
        ("resume_session_id", "runtime_owned_workspace_and_execution"),
        AckMeaning.PROTOCOL_REPLY_ONLY,
        TerminalRule.NOT_TURN_TERMINAL,
        RecoveryRule.NO_AUTOMATIC_REPLAY,
        (_CLAUDE_TYPES, _CLAUDE_CLIENT),
        (*_OWNED_EXECUTION, "unknown_delivery_never_resubmits_prompt"),
    ),
    _contract(
        AdapterOperation.STEER_TURN,
        None,
        ("exact_active_turn", "prompt"),
        AckMeaning.NOT_ESTABLISHED,
        TerminalRule.NOT_ESTABLISHED,
        RecoveryRule.OUT_OF_PROFILE,
        (_CLAUDE_CLIENT,),
        ("query_is_not_qualified_exact_turn_steer",),
        initial_k2_scope=False,
    ),
    _contract(
        AdapterOperation.FORK_THREAD,
        "ClaudeAgentOptions.resume; ClaudeAgentOptions.fork_session; resume_session_at",
        ("resume_session_id", "qualified_message_uuid"),
        AckMeaning.PROTOCOL_REPLY_ONLY,
        TerminalRule.NOT_TURN_TERMINAL,
        RecoveryRule.OUT_OF_PROFILE,
        (_CLAUDE_TYPES, _CLAUDE_CLIENT),
        ("conversation_workspace_checkpoint_consistency",),
        initial_k2_scope=False,
    ),
    _contract(
        AdapterOperation.ROLLBACK_THREAD,
        None,
        ("qualified_conversation_and_workspace_checkpoint",),
        AckMeaning.NOT_ESTABLISHED,
        TerminalRule.NOT_ESTABLISHED,
        RecoveryRule.OUT_OF_PROFILE,
        (_CLAUDE_CLIENT, _CLAUDE_TYPES),
        ("file_rewind_is_not_conversation_and_workspace_rollback",),
        initial_k2_scope=False,
    ),
    _contract(
        AdapterOperation.QUEUE_TURN,
        None,
        ("explicit_durable_task_identity",),
        AckMeaning.NOT_ESTABLISHED,
        TerminalRule.NOT_ESTABLISHED,
        RecoveryRule.OUT_OF_PROFILE,
        (),
        ("separate_k3_task_and_queue_contract",),
        initial_k2_scope=False,
    ),
)

_PROFILES = (
    AdapterProfile(
        agent="codex",
        profile_id="kebui-codex-app-server-research-v1",
        executable_version="0.159.3",
        source_repository="https://github.com/openai/codex",
        source_revision="01fc69f4026735edfdf6789820549727a4867b11",
        sdk_version=None,
        operations=_CODEX_OPERATIONS,
    ),
    AdapterProfile(
        agent="claude",
        profile_id="kebui-claude-sdk-research-v1",
        executable_version="2.1.286",
        source_repository="https://github.com/anthropics/claude-agent-sdk-python",
        source_revision="1ef6d8c71bb0e44a6b33fe61497864f21e17fdb7",
        sdk_version="0.2.163",
        operations=_CLAUDE_OPERATIONS,
    ),
)


def fixed_profiles() -> tuple[AdapterProfile, ...]:
    """Return immutable research records, without discovering installed agents."""
    return _PROFILES


def _identity_state(selection: AdapterSelection, profile: AdapterProfile) -> CapabilityState:
    pairs = (
        (selection.profile_id, profile.profile_id),
        (selection.executable_version, profile.executable_version),
        (selection.source_revision, profile.source_revision),
        (selection.sdk_version, profile.sdk_version),
    )
    # A known contradiction wins over missing hints. No semver range or upgrade fallback.
    if any(actual is not None and actual != expected for actual, expected in pairs):
        return CapabilityState.STALE
    if any(actual is None and expected is not None for actual, expected in pairs):
        return CapabilityState.UNKNOWN
    return CapabilityState.SUPPORTED


def assess_capability(
    selection: AdapterSelection, operation: AdapterOperation | str
) -> CapabilityAssessment:
    """Compare hints to a fixed research profile and return a permanently denied assessment.

    ``supported`` in the identity/source fields means only an exact pin match or
    a source-level method. No caller-provided qualification, host, secret, content,
    executable path, or arbitrary command can upgrade the result.
    """
    if type(selection) is not AdapterSelection:
        raise CapabilityContractError("invalid_adapter_selection")
    if not isinstance(operation, AdapterOperation) and (
        type(operation) is not str or _LABEL.fullmatch(operation) is None
    ):
        raise CapabilityContractError("invalid_adapter_operation")
    try:
        known_operation = AdapterOperation(operation)
    except ValueError:
        known_operation = None
    profile = next((item for item in _PROFILES if item.agent == selection.agent), None)
    contract = (
        next((item for item in profile.operations if item.operation == known_operation), None)
        if profile is not None
        else None
    )
    identity_state = (
        _identity_state(selection, profile) if profile is not None else CapabilityState.UNKNOWN
    )
    source_state = contract.research_state if contract is not None else CapabilityState.UNKNOWN
    software_state = (
        CapabilityState.UNSUPPORTED
        if known_operation is None or (contract is not None and not contract.initial_k2_scope)
        else CapabilityState.UNKNOWN
    )
    blockers: list[FindingCode] = []
    if known_operation is None:
        blockers.append(FindingCode.UNKNOWN_OPERATION)
    if profile is None:
        blockers.append(FindingCode.UNKNOWN_AGENT)
    elif identity_state is CapabilityState.STALE:
        blockers.append(FindingCode.IDENTITY_MISMATCH)
    elif identity_state is CapabilityState.UNKNOWN:
        blockers.append(FindingCode.MISSING_IDENTITY)
    if source_state is CapabilityState.UNKNOWN:
        blockers.append(FindingCode.SOURCE_NOT_ESTABLISHED)
    software_code = (
        FindingCode.OUT_OF_PROFILE
        if software_state is CapabilityState.UNSUPPORTED
        else FindingCode.SOFTWARE_NOT_QUALIFIED
    )
    blockers.extend((software_code, FindingCode.HOST_NOT_QUALIFIED))
    approval_blocked = (
        contract is not None and contract.operation is AdapterOperation.RESPOND_APPROVAL
    )
    if approval_blocked:
        blockers.append(FindingCode.APPROVAL_DEADLINE_UNQUALIFIED)
    if software_state is CapabilityState.UNSUPPORTED or approval_blocked:
        state = CapabilityState.UNSUPPORTED
    elif identity_state is CapabilityState.STALE:
        state = CapabilityState.STALE
    else:
        state = CapabilityState.UNKNOWN
    return CapabilityAssessment(
        state=state,
        identity_state=identity_state,
        profile=profile,
        contract=contract,
        source_research=EvidenceFinding(
            EvidenceDomain.SOURCE_RESEARCH,
            source_state,
            (
                FindingCode.PINNED_SOURCE_SURFACE
                if source_state is CapabilityState.SUPPORTED
                else FindingCode.SOURCE_NOT_ESTABLISHED
            ),
        ),
        software_qualification=EvidenceFinding(
            EvidenceDomain.SOFTWARE_QUALIFICATION, software_state, software_code
        ),
        host_qualification=EvidenceFinding(
            EvidenceDomain.HOST_QUALIFICATION,
            CapabilityState.UNKNOWN,
            FindingCode.HOST_NOT_QUALIFIED,
        ),
        blockers=tuple(blockers),
    )
