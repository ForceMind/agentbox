"""Validated AgentBox release versions and deterministic precedence."""

from __future__ import annotations

import re
from typing import TypeGuard

_CORE = r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)"
_IDENTIFIER = r"[0-9A-Za-z][0-9A-Za-z-]*"
VERSION_PATTERN = re.compile(
    rf"(?P<core>{_CORE})"
    rf"(?:(?:rc(?P<rc>[1-9][0-9]*))|-(?P<prerelease>{_IDENTIFIER}(?:\.{_IDENTIFIER})*))?"
    rf"(?:\+(?P<build>{_IDENTIFIER}(?:\.{_IDENTIFIER})*))?"
)

PrereleaseIdentifier = tuple[int, int | str]
VersionPrecedence = tuple[int, int, int, int, tuple[PrereleaseIdentifier, ...]]


def version_precedence(version: str) -> VersionPrecedence:
    """Return SemVer-like precedence while normalizing PEP 440 ``rcN``.

    Build metadata is validated but intentionally excluded. Numeric prerelease
    identifiers sort numerically and below non-numeric identifiers.
    """
    match = VERSION_PATTERN.fullmatch(version)
    if match is None:
        raise ValueError("release version is invalid")
    major, minor, patch = (int(item) for item in match.group("core").split("."))
    rc_number = match.group("rc")
    prerelease = match.group("prerelease")
    if rc_number is not None:
        raw_identifiers = ("rc", rc_number)
    elif prerelease is not None:
        raw_identifiers = tuple(prerelease.split("."))
    else:
        return major, minor, patch, 1, ()

    identifiers: list[PrereleaseIdentifier] = []
    for identifier in raw_identifiers:
        if identifier.isdigit():
            if len(identifier) > 1 and identifier.startswith("0"):
                raise ValueError("numeric prerelease identifier has a leading zero")
            identifiers.append((0, int(identifier)))
        else:
            identifiers.append((1, identifier))
    return major, minor, patch, 0, tuple(identifiers)


def valid_version(version: object) -> TypeGuard[str]:
    if not isinstance(version, str):
        return False
    try:
        version_precedence(version)
    except ValueError:
        return False
    return True
