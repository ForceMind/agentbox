from __future__ import annotations

import pytest
from agentbox_core.waw import workspace_id
from agentbox_core.waw_recovery import (
    RecoveryDecision,
    RecoveryError,
    RecoveryIdentity,
    ResumeHint,
    classify_resume,
)


def identity(*, runtime_epoch: int = 4, generation: int = 2) -> RecoveryIdentity:
    return RecoveryIdentity(
        workspace_id=workspace_id("prj_" + "2" * 32, "claude"),
        project_id="prj_" + "2" * 32,
        agent_type="claude",
        generation=generation,
        binding_revision=1,
        binding_digest="a" * 64,
        runtime_host_installation_id="wri_" + "3" * 32,
        runtime_host_installation_revision=1,
        runtime_epoch=runtime_epoch,
        api_authority_epoch=1,
        attachment_id="att_" + "4" * 32,
        lease_number=1,
        session_id="ses_1",
        auth_epoch=1,
    )


@pytest.mark.parametrize("hint", [ResumeHint(None, None), ResumeHint(0, None)])
def test_fresh_resume_hints_are_accepted(hint: ResumeHint) -> None:
    assert hint.validate(current_runtime_epoch=4) == hint
    assert (
        classify_resume(expected=identity(), actual=identity(), hint=hint)
        is RecoveryDecision.FRESH_ATTACHMENT
    )


def test_same_generation_and_runtime_replays_only_positive_cursor() -> None:
    assert (
        classify_resume(expected=identity(), actual=identity(), hint=ResumeHint(8, 4))
        is RecoveryDecision.REPLAY
    )


def test_api_restart_allows_fresh_attachment_for_same_workspace_generation() -> None:
    candidate = identity()
    candidate = RecoveryIdentity(
        **{
            **candidate.__dict__,
            "attachment_id": "att_" + "5" * 32,
            "lease_number": 2,
        }
    )
    assert (
        classify_resume(expected=identity(), actual=candidate, hint=ResumeHint(None, None))
        is RecoveryDecision.FRESH_ATTACHMENT
    )


@pytest.mark.parametrize("hint", [ResumeHint(8, None), ResumeHint(0, 4), ResumeHint(8, 3)])
def test_resume_hint_closed_set_rejects_ambiguous_combinations(hint: ResumeHint) -> None:
    with pytest.raises(RecoveryError) as error:
        hint.validate(current_runtime_epoch=4)
    assert error.value.code == "RESUME_HINT_INVALID"


@pytest.mark.parametrize("epoch", [0, 2**64, 2**100])
def test_resume_hint_rejects_invalid_current_epoch(epoch: int) -> None:
    with pytest.raises(RecoveryError):
        ResumeHint(1, 1).validate(current_runtime_epoch=epoch)


def test_runtime_epoch_change_fails_closed_without_gap() -> None:
    with pytest.raises(RecoveryError) as error:
        classify_resume(
            expected=identity(runtime_epoch=4),
            actual=identity(runtime_epoch=5),
            hint=ResumeHint(8, 4),
        )
    assert error.value.code == "RECONCILIATION_REQUIRED"


def test_api_epoch_change_cannot_replay_with_old_attachment() -> None:
    candidate = identity()
    candidate = RecoveryIdentity(**{**candidate.__dict__, "api_authority_epoch": 2})
    with pytest.raises(RecoveryError) as error:
        classify_resume(expected=identity(), actual=candidate, hint=ResumeHint(8, 4))
    assert error.value.code == "RECONCILIATION_REQUIRED"


def test_api_epoch_change_allows_only_fresh_new_attachment() -> None:
    candidate = identity()
    candidate = RecoveryIdentity(
        **{
            **candidate.__dict__,
            "api_authority_epoch": 2,
            "attachment_id": "att_" + "5" * 32,
            "lease_number": 2,
        }
    )
    assert (
        classify_resume(expected=identity(), actual=candidate, hint=ResumeHint(None, None))
        is RecoveryDecision.FRESH_ATTACHMENT
    )


@pytest.mark.parametrize("field", ["session_id", "auth_epoch"])
def test_session_or_auth_change_is_stale(field: str) -> None:
    candidate = identity()
    values = {**candidate.__dict__, field: "ses_2" if field == "session_id" else 2}
    candidate = RecoveryIdentity(**values)
    with pytest.raises(RecoveryError) as error:
        classify_resume(expected=identity(), actual=candidate, hint=ResumeHint(None, None))
    assert error.value.code == "RECOVERY_IDENTITY_STALE"


def test_generation_or_binding_change_requires_reconciliation() -> None:
    with pytest.raises(RecoveryError) as error:
        classify_resume(
            expected=identity(), actual=identity(generation=3), hint=ResumeHint(None, None)
        )
    assert error.value.code == "RECONCILIATION_REQUIRED"
