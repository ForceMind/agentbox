"""Deterministic test-only crash injection at named lifecycle boundaries."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


class InjectedCrash(BaseException):
    """Model abrupt process loss that bypasses normal Exception rollback."""


@dataclass
class FailureInjector:
    point: str
    observed: list[str] = field(default_factory=list)

    def trigger(self, point: str) -> None:
        self.observed.append(point)
        if point == self.point:
            raise InjectedCrash(f"injected crash at {point}")

    def after(self, point: str, operation: Callable[..., Any]) -> Callable[..., Any]:
        def wrapped(*args: Any, **kwargs: Any) -> Any:
            result = operation(*args, **kwargs)
            self.trigger(point)
            return result

        return wrapped
