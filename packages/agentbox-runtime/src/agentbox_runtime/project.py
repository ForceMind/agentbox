"""Minimal, read-only project references for project-scoped Runtime actions."""

from __future__ import annotations

import os
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from agentbox_runtime.models import RuntimeOperationError

MAX_PROJECT_ID_LENGTH = 80


def validate_project_id(project_id: str) -> str:
    """Accept one bounded path component; never accept a caller-supplied path."""
    if not isinstance(project_id, str):
        raise RuntimeOperationError(
            "CLAUDE_PROJECT_INVALID", "Project identifier is invalid", category="validation"
        )
    normalized = unicodedata.normalize("NFC", project_id)
    if (
        normalized != project_id
        or not (1 <= len(project_id) <= MAX_PROJECT_ID_LENGTH)
        or project_id in {".", ".."}
        or project_id != project_id.strip()
        or project_id.startswith(".")
        or "/" in project_id
        or "\\" in project_id
        or any(unicodedata.category(character).startswith("C") for character in project_id)
    ):
        raise RuntimeOperationError(
            "CLAUDE_PROJECT_INVALID", "Project identifier is invalid", category="validation"
        )
    # Project IDs remain readable slugs. Unicode letters/numbers and spaces are
    # supported, while shell punctuation is rejected even though no shell exists.
    if any(
        not (character.isalnum() or character in {"-", "_", ".", " "}) for character in project_id
    ):
        raise RuntimeOperationError(
            "CLAUDE_PROJECT_INVALID", "Project identifier is invalid", category="validation"
        )
    return project_id


@dataclass(frozen=True)
class ConfiguredProject:
    project_id: str
    display_name: str
    path: Path


class ProjectRegistry:
    """Enumerate only immediate, non-symlink children of one configured root."""

    def __init__(self, root: Path) -> None:
        if not root.is_absolute():
            root = (Path.cwd() / root).absolute()
        self._root = root

    @property
    def root(self) -> Path:
        return self._root

    def list_projects(self) -> tuple[ConfiguredProject, ...]:
        root = self._resolved_root(required=False)
        if root is None:
            return ()
        projects: list[ConfiguredProject] = []
        try:
            entries = tuple(root.iterdir())
        except OSError:
            return ()
        for entry in entries:
            try:
                project_id = validate_project_id(entry.name)
                if entry.is_symlink() or not entry.is_dir():
                    continue
                resolved = entry.resolve(strict=True)
                if resolved.parent != root or not os.access(resolved, os.R_OK | os.X_OK):
                    continue
            except (OSError, RuntimeError, RuntimeOperationError):
                continue
            projects.append(ConfiguredProject(project_id, project_id, resolved))
        return tuple(sorted(projects, key=lambda project: project.project_id.casefold()))

    def resolve(self, project_id: str) -> ConfiguredProject:
        validated = validate_project_id(project_id)
        root = self._resolved_root(required=True)
        assert root is not None
        candidate = root / validated
        try:
            if candidate.is_symlink():
                raise RuntimeOperationError(
                    "CLAUDE_PROJECT_SYMLINK_FORBIDDEN",
                    "Project symlinks are not managed",
                    category="validation",
                )
            resolved = candidate.resolve(strict=True)
        except RuntimeOperationError:
            raise
        except (OSError, RuntimeError) as exc:
            raise RuntimeOperationError(
                "CLAUDE_PROJECT_NOT_FOUND", "Project is unavailable", category="unavailable"
            ) from exc
        if resolved == root or resolved.parent != root or not resolved.is_dir():
            raise RuntimeOperationError(
                "CLAUDE_PROJECT_OUTSIDE_ROOT",
                "Project is outside the configured root",
                category="validation",
            )
        if not os.access(resolved, os.R_OK | os.X_OK):
            raise RuntimeOperationError(
                "CLAUDE_PROJECT_INACCESSIBLE", "Project is inaccessible", category="forbidden"
            )
        return ConfiguredProject(validated, validated, resolved)

    def _resolved_root(self, *, required: bool) -> Path | None:
        try:
            if self._root.is_symlink():
                raise RuntimeOperationError(
                    "CLAUDE_PROJECT_ROOT_INVALID",
                    "Configured project root cannot be a symlink",
                    category="validation",
                )
            root = self._root.resolve(strict=True)
            if not root.is_dir():
                raise OSError("not a directory")
            return root
        except RuntimeOperationError:
            if required:
                raise
            return None
        except (OSError, RuntimeError) as exc:
            if required:
                raise RuntimeOperationError(
                    "CLAUDE_PROJECT_ROOT_UNAVAILABLE",
                    "Configured project root is unavailable",
                    category="unavailable",
                ) from exc
            return None
