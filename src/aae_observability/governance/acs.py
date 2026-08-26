"""Adapter for an external Agent Control Service decision authority."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from aae_observability.contracts import ActionSnapshot, BasePolicyEngine
from aae_observability.types import PolicyResult, Verdict

ACSDecisionClient = Callable[[Mapping[str, Any], int], Mapping[str, Any]]


class ACSPolicyEngine(BasePolicyEngine):
    def __init__(self, client: ACSDecisionClient, *, timeout_ms: int = 50) -> None:
        if timeout_ms < 1:
            raise ValueError("timeout_ms must be positive")
        self._client = client
        self.timeout_ms = timeout_ms

    def evaluate(self, snapshot: ActionSnapshot) -> PolicyResult:
        request = {
            "call": {
                "agent_name": snapshot.call.agent_name,
                "agent_id": snapshot.call.agent_id,
                "tool_name": snapshot.call.tool_name,
                "operation": getattr(snapshot.call.operation, "value", snapshot.call.operation),
                "run_id": snapshot.call.run_id,
            },
            "identity": {
                "principal_id": snapshot.identity.principal_id,
                "principal_type": snapshot.identity.principal_type,
                "tenant_id": snapshot.identity.tenant_id,
                "roles": list(snapshot.identity.roles),
            },
            "context": dict(snapshot.context),
        }
        response = self._client(request, self.timeout_ms)
        if not isinstance(response, Mapping):
            raise ValueError("ACS client returned a non-mapping response")
        try:
            verdict = Verdict(str(response["verdict"]).lower())
        except (KeyError, ValueError) as exc:
            raise ValueError("ACS response contains an invalid verdict") from exc
        return PolicyResult(
            verdict,
            str(response.get("reason", "")),
            str(response["rule_id"]) if response.get("rule_id") is not None else None,
            dict(response.get("metadata") or {}),
        )
