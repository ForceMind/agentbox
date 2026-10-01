"""Fixed Runtime cgroup FD observations for durable lifecycle records."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from collections.abc import Callable
from dataclasses import asdict, replace

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
    _open_scoped_workspace_root,
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
            delegate = (
                _open_scoped_workspace_root(authority)
                if not persist_empty
                else os.open(
                    cgroup_delegate_root_path(manifest),
                    os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                )
            )
            fds.append(delegate)
            mount, filesystem = _verify_delegate_root(delegate, authority)
            try:
                workspace = _open_relative_directory(
                    delegate, name, path_only=False, expected_uid=os.geteuid()
                )
            except FileNotFoundError:
                if persist_empty:
                    raise
                return self._observe_absence(identity, service, delegate, name, mount, filesystem)
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

    def _observe_absence(
        self,
        identity: WAWLifecycleIdentity,
        service: int,
        delegate: int,
        name: str,
        mount: str,
        filesystem: str,
    ) -> WAWCgroupAttestation:
        """Prove absence under the verified current scoped cgroup mount.

        Only an ENOENT for the exact generated Workspace component qualifies.
        Service/delegate FDs are real; nonexistent Workspace/workload physical
        identities use explicit absence markers. Limits are retained policy
        metadata, not measurements of a nonexistent group.
        """
        old = self._store.read(
            workspace_id=identity.workspace_id, generation=int(identity.generation)
        )
        if old is None or (
            old.project_id != identity.project_id
            or old.agent_type != identity.agent_type
            or old.workspace_relative_path != name
            or old.workload_relative_path != name + "/workload"
            or int(old.runtime_epoch) > int(self._runtime_epoch())
        ):
            raise RuntimeOperationError(
                "RECONCILIATION_REQUIRED", "Absence provenance changed", category="conflict"
            )
        facts = [os.fstat(service), os.fstat(delegate)]
        if any(
            fact.st_uid != os.geteuid() or fact.st_gid != os.getegid() or fact.st_mode & 0o022
            for fact in facts
        ):
            raise RuntimeOperationError(
                "RECONCILIATION_REQUIRED", "Absence FD ownership changed", category="conflict"
            )
        for _ in range(2):
            try:
                os.stat(name, dir_fd=delegate, follow_symlinks=False)
            except FileNotFoundError:
                pass
            else:
                raise RuntimeOperationError(
                    "RECONCILIATION_REQUIRED", "Workspace reappeared", category="conflict"
                )
            if _verify_delegate_root(delegate, self._authority()) != (mount, filesystem):
                raise RuntimeOperationError(
                    "RECONCILIATION_REQUIRED", "Absence mount changed", category="conflict"
                )
        record = replace(
            old,
            runtime_epoch=self._runtime_epoch(),
            service_invocation_id=self._invocation,
            service_cgroup_device=f"{os.major(facts[0].st_dev)}:{os.minor(facts[0].st_dev)}",
            service_cgroup_inode=str(facts[0].st_ino),
            service_cgroup_mount_id=_fd_mount_id(service),
            delegate_subgroup_device=f"{os.major(facts[1].st_dev)}:{os.minor(facts[1].st_dev)}",
            delegate_subgroup_inode=str(facts[1].st_ino),
            delegate_subgroup_mount_id=mount,
            cgroup_mount_id=mount,
            cgroup_filesystem_id=filesystem,
            workspace_device="absent",
            workspace_inode="absent",
            workload_device="absent",
            workload_inode="absent",
            workspace_presence="absent",
            attachment_leaves=(),
            last_frozen="0",
            last_populated="0",
            cleanup_state="EMPTY_DURABLE",
        )
        return decode_waw_cgroup_attestation(encode_waw_cgroup_attestation(record))

    def finalize_recovery(self, record: WAWCgroupAttestation) -> None:
        """Remove only the durably empty, exact observed old generation.

        No kill, adoption or recursive deletion. Kernel busy/nonempty failures
        retain quarantine; an interrupted deletion is handled by fresh absence
        observation on the next start attempt.
        """
        record = decode_waw_cgroup_attestation(encode_waw_cgroup_attestation(record))
        name = (
            "ws-"
            + hashlib.sha256(record.workspace_id.encode()).hexdigest()
            + "-g"
            + str(record.generation)
        )
        if (
            record.runtime_epoch != self._runtime_epoch()
            or record.service_invocation_id != self._invocation
            or record.workspace_relative_path != name
            or record.workload_relative_path != name + "/workload"
            or record.cleanup_state != "EMPTY_DURABLE"
            or record.last_populated != "0"
            or record.attachment_leaves
            or self._store.read(workspace_id=record.workspace_id, generation=record.generation)
            != record
        ):
            raise RuntimeOperationError(
                "RECONCILIATION_REQUIRED", "Cleanup record changed", category="conflict"
            )
        if record.workspace_presence == "absent":
            return
        fds: list[int] = []
        try:
            delegate = os.open(
                cgroup_delegate_root_path(self._authority()._manifest.cgroup),
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
            )
            fds.append(delegate)
            mount, filesystem = _verify_delegate_root(delegate, self._authority())
            workspace = _open_relative_directory(
                delegate, name, path_only=False, expected_uid=os.geteuid()
            )
            fds.append(workspace)
            try:
                workload = _open_relative_directory(
                    workspace, "workload", path_only=False, expected_uid=os.geteuid()
                )
            except FileNotFoundError:
                workload = None
            if workload is not None:
                fds.append(workload)
            identities = [
                (delegate, record.delegate_subgroup_device, record.delegate_subgroup_inode),
                (workspace, record.workspace_device, record.workspace_inode),
            ]
            if workload is not None:
                identities.append((workload, record.workload_device, record.workload_inode))
            for fd, device, inode in identities:
                fact = os.fstat(fd)
                if (
                    f"{os.major(fact.st_dev)}:{os.minor(fact.st_dev)}" != device
                    or str(fact.st_ino) != inode
                    or fact.st_uid != os.geteuid()
                    or fact.st_gid != os.getegid()
                    or fact.st_mode & 0o022
                    or _fd_mount_id(fd) != mount
                ):
                    raise RuntimeOperationError(
                        "RECONCILIATION_REQUIRED", "Cleanup FD changed", category="conflict"
                    )
            if mount != record.cgroup_mount_id or filesystem != record.cgroup_filesystem_id:
                raise RuntimeOperationError(
                    "RECONCILIATION_REQUIRED", "Cleanup mount changed", category="conflict"
                )
            if self._limits(workspace) != record.workspace_limits or (
                workload is not None and self._limits(workload) != record.workload_limits
            ):
                raise RuntimeOperationError(
                    "RECONCILIATION_REQUIRED", "Cleanup limits changed", category="conflict"
                )
            hierarchy = [(workspace, {"workload"} if workload is not None else set())]
            if workload is not None:
                hierarchy.append((workload, set()))
            for parent, allowed in hierarchy:
                directories = {
                    entry
                    for entry in os.listdir(parent)
                    if stat.S_ISDIR(os.stat(entry, dir_fd=parent, follow_symlinks=False).st_mode)
                }
                if directories != allowed or _cgroup_event(workspace, "populated") != 0:
                    raise RuntimeOperationError(
                        "RECONCILIATION_REQUIRED", "Cleanup is not empty", category="conflict"
                    )
            removals = []
            if workload is not None:
                removals.append((workspace, "workload", record.workload_inode))
            removals.append((delegate, name, record.workspace_inode))
            for parent, child, inode in removals:
                if str(os.stat(child, dir_fd=parent, follow_symlinks=False).st_ino) != inode:
                    raise RuntimeOperationError(
                        "RECONCILIATION_REQUIRED", "Cleanup path changed", category="conflict"
                    )
                os.rmdir(child, dir_fd=parent)
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
