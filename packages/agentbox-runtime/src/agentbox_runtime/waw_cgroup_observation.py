"""Fixed Runtime cgroup FD observations for durable lifecycle records."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from collections.abc import Callable
from dataclasses import asdict

from agentbox_runtime.models import RuntimeOperationError
from agentbox_runtime.waw_cgroup_attestation import (
    WAWCgroupAttestation,
    WAWCgroupLimits,
    decode_waw_cgroup_attestation,
    encode_waw_cgroup_attestation,
)
from agentbox_runtime.waw_cgroup_attestation_store import WAWCgroupAttestationStore
from agentbox_runtime.waw_fixed_transport import (
    WAWVerifiedExecutionAuthority,
    _cgroup_event,
    _fd_mount_id,
    _open_relative_directory,
    _read_cgroup_file,
    _verify_delegate_root,
)
from agentbox_runtime.waw_lifecycle import WAWLifecycleIdentity, WAWLifecycleObservation
from agentbox_runtime.waw_manifest_codecs import (
    SCOPED_CGROUP_SERVICE_ROOT_V1,
    cgroup_delegate_root_path,
)


class WAWCgroupObservationFactory:
    def __init__(
        self,
        authority: Callable[[], WAWVerifiedExecutionAuthority],
        store: WAWCgroupAttestationStore,
        *,
        invocation_id: str,
        runtime_epoch: Callable[[], str],
    ) -> None:
        if re.fullmatch(r"[0-9a-f]{32}", invocation_id) is None:
            raise RuntimeOperationError(
                "RUNTIME_UNAVAILABLE",
                "systemd invocation identity is required",
                category="unavailable",
            )
        self._authority = authority
        self._store = store
        self._invocation = invocation_id
        self._runtime_epoch = runtime_epoch

    def __call__(
        self, identity: WAWLifecycleIdentity, observation: WAWLifecycleObservation
    ) -> WAWCgroupAttestation:
        return self._observe(identity, observation, persist_empty=True)

    def observe_recovery(self, identity: WAWLifecycleIdentity) -> WAWCgroupAttestation:
        """Read current FDs without overwriting the old epoch's record.

        STOPPED selects an empty candidate, never proves emptiness: the same
        populated/leaf/ownership/limit checks below remain mandatory. The
        registry persists this candidate through its recovery CAS before
        releasing quarantine.
        """
        return self._observe(
            identity, WAWLifecycleObservation(state="STOPPED"), persist_empty=False
        )

    def _observe(
        self,
        identity: WAWLifecycleIdentity,
        observation: WAWLifecycleObservation,
        *,
        persist_empty: bool,
    ) -> WAWCgroupAttestation:
        authority = self._authority()
        manifest = authority._manifest.cgroup
        name = (
            "ws-"
            + hashlib.sha256(identity.workspace_id.encode("ascii")).hexdigest()
            + "-g"
            + identity.generation
        )
        fds: list[int] = []
        try:
            service = os.open(
                SCOPED_CGROUP_SERVICE_ROOT_V1,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
            )
            fds.append(service)
            delegate = os.open(
                cgroup_delegate_root_path(manifest),
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
            )
            fds.append(delegate)
            mount, filesystem = _verify_delegate_root(delegate, authority)
            workspace = _open_relative_directory(
                delegate, name, path_only=False, expected_uid=os.geteuid()
            )
            fds.append(workspace)
            workload = _open_relative_directory(
                workspace, "workload", path_only=False, expected_uid=os.geteuid()
            )
            fds.append(workload)
            for parent, allowed in ((workspace, {"workload"}), (workload, set())):
                directories = {
                    entry
                    for entry in os.listdir(parent)
                    if stat.S_ISDIR(os.stat(entry, dir_fd=parent, follow_symlinks=False).st_mode)
                }
                if directories != allowed:
                    raise RuntimeOperationError(
                        "RECONCILIATION_REQUIRED",
                        "Unrecorded cgroup leaves remain",
                        category="conflict",
                    )
            populated = str(_cgroup_event(workspace, "populated"))
            frozen = str(_cgroup_event(workload, "frozen"))
            workspace_limits = self._limits(workspace)
            workload_limits = self._limits(workload)
            facts = [os.fstat(fd) for fd in fds]
            if any(
                fact.st_uid != os.geteuid() or fact.st_gid != os.getegid() or fact.st_mode & 0o022
                for fact in facts
            ):
                raise RuntimeOperationError(
                    "RECONCILIATION_REQUIRED", "Cgroup FD ownership changed", category="conflict"
                )

            def device(index: int) -> str:
                return f"{os.major(facts[index].st_dev)}:{os.minor(facts[index].st_dev)}"

            cleanup = (
                "LIVE"
                if observation.state
                in {"RUNNING", "STARTING", "DETACHED", "NEEDS_INTERACTION", "TRUST_REQUIRED"}
                or observation.state == "LOGIN_REQUIRED"
                and populated == "1"
                else "FENCED"
            )
            if cleanup == "LIVE" and populated != "1":
                raise RuntimeOperationError(
                    "RECONCILIATION_REQUIRED",
                    "Running cgroup is not populated",
                    category="conflict",
                )
            if (
                cleanup != "LIVE"
                and populated == "0"
                and observation.state in {"STOPPED", "EXITED"}
            ):
                cleanup = "EMPTY_DURABLE"
            digest = hashlib.sha256(
                json.dumps(
                    {"workspace": asdict(workspace_limits), "workload": asdict(workload_limits)},
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode()
            ).hexdigest()
            record = WAWCgroupAttestation(
                workspace_id=identity.workspace_id,
                project_id=identity.project_id,
                agent_type=identity.agent_type,
                generation=int(identity.generation),
                runtime_epoch=self._runtime_epoch(),
                service_unit="agentbox-runtime.service",
                service_invocation_id=self._invocation,
                service_cgroup_device=device(0),
                service_cgroup_inode=str(facts[0].st_ino),
                service_cgroup_mount_id=_fd_mount_id(service),
                delegated_subgroup=manifest.delegate_subgroup,
                delegate_subgroup_device=device(1),
                delegate_subgroup_inode=str(facts[1].st_ino),
                delegate_subgroup_mount_id=mount,
                cgroup_mount_id=mount,
                cgroup_filesystem_id=filesystem,
                workspace_relative_path=name,
                workspace_device=device(2),
                workspace_inode=str(facts[2].st_ino),
                workload_relative_path=name + "/workload",
                workload_device=device(3),
                workload_inode=str(facts[3].st_ino),
                attachment_leaves=(),
                controller_configuration_digest=digest,
                workspace_limits=workspace_limits,
                workload_limits=workload_limits,
                attachment_limits=workload_limits,
                last_frozen=frozen,
                last_populated=populated,
                cleanup_state=cleanup,
            )
            record = decode_waw_cgroup_attestation(encode_waw_cgroup_attestation(record))
            if (
                str(_cgroup_event(workspace, "populated")) != populated
                or str(_cgroup_event(workload, "frozen")) != frozen
            ):
                raise RuntimeOperationError(
                    "RECONCILIATION_REQUIRED", "Cgroup observation changed", category="conflict"
                )
            if cleanup == "EMPTY_DURABLE" and persist_empty:
                self._store.write(record)
            return record
        finally:
            for fd in reversed(fds):
                os.close(fd)

    @staticmethod
    def _limits(fd: int) -> WAWCgroupLimits:
        quota, period = _read_cgroup_file(fd, "cpu.max").split()
        return WAWCgroupLimits(
            int(_read_cgroup_file(fd, "memory.max").strip()),
            int(_read_cgroup_file(fd, "memory.swap.max").strip()),
            int(quota),
            int(period),
            int(_read_cgroup_file(fd, "pids.max").strip()),
        )
