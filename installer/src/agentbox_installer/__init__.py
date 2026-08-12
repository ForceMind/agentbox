"""Safe, fixture-first AgentBox installation and lifecycle tooling."""

from agentbox_installer.platform import PlatformFacts, PlatformSupport, detect_platform

__all__ = ["PlatformFacts", "PlatformSupport", "detect_platform"]
