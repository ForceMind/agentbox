"""Minimal marker interface for future capability-aware Runtime Adapters."""

from typing import Protocol, runtime_checkable


@runtime_checkable
class RuntimeAdapter(Protocol):
    """Marker contract only; operational methods are intentionally deferred."""

    @property
    def runtime_name(self) -> str:
        """Return the stable AgentBox Runtime name."""
        ...
