"""Compiled local policy engine."""

from __future__ import annotations

from dataclasses import dataclass

from aae_observability.contracts import ActionSnapshot, BasePolicyEngine
from aae_observability.governance.conditions import Predicate, compile_condition
from aae_observability.governance.models import PolicyDocument, PolicyRule
from aae_observability.types import PolicyResult


@dataclass(frozen=True, slots=True)
class CompiledRule:
    rule: PolicyRule
    predicate: Predicate


class LocalPolicyEngine(BasePolicyEngine):
    """Deterministic first-match policy engine with compiled predicates."""

    def __init__(self, policy: PolicyDocument) -> None:
        self.policy = policy
        self._compiled = tuple(
            CompiledRule(rule, compile_condition(rule.condition))
            for rule in sorted(
                (r for r in policy.rules if r.enabled), key=lambda r: (r.priority, r.id)
            )
        )

    @property
    def compiled_rule_count(self) -> int:
        return len(self._compiled)

    def evaluate(self, snapshot: ActionSnapshot) -> PolicyResult:
        for compiled in self._compiled:
            if compiled.predicate(snapshot):
                rule = compiled.rule
                return PolicyResult(
                    rule.action,
                    rule.reason or rule.description,
                    rule.id,
                    {"priority": rule.priority, "policy": self.policy.metadata.get("name")},
                )
        return PolicyResult(
            self.policy.default_action,
            "policy default action",
            metadata={"policy": self.policy.metadata.get("name")},
        )

    @classmethod
    def from_file(cls, path: str) -> LocalPolicyEngine:
        from aae_observability.governance.loader import load_policy

        return cls(load_policy(path))
