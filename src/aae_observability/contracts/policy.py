"""Governance policy engine contracts and bootstrap implementations."""

from abc import ABC, abstractmethod
from typing import Protocol, runtime_checkable

from aae_observability.contracts.snapshot import ActionSnapshot
from aae_observability.types import PolicyResult, Verdict


@runtime_checkable
class PolicyEngine(Protocol):
    """Structural contract for a synchronous governance decision authority."""

    def evaluate(self, snapshot: ActionSnapshot) -> PolicyResult:
        """Evaluate a complete action snapshot and return a policy result."""
        ...


class BasePolicyEngine(ABC):
    """Inheritance-based convenience contract for policy engines."""

    @abstractmethod
    def evaluate(self, snapshot: ActionSnapshot) -> PolicyResult:
        """Evaluate a complete action snapshot and return a policy result."""
        raise NotImplementedError


class AllowAllPolicyEngine(BasePolicyEngine):
    """Development-only engine that allows every action."""

    def evaluate(self, snapshot: ActionSnapshot) -> PolicyResult:
        del snapshot
        return PolicyResult(Verdict.ALLOW, reason="allow-all development policy")


class DenyAllPolicyEngine(BasePolicyEngine):
    """Fail-closed engine that denies every action."""

    def evaluate(self, snapshot: ActionSnapshot) -> PolicyResult:
        del snapshot
        return PolicyResult(Verdict.DENY, reason="deny-all policy")
