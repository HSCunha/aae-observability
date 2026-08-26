"""Validated declarative governance policy models."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from aae_observability.types import Verdict


class PolicyRule(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    id: str = Field(min_length=1, max_length=200)
    description: str = ""
    condition: dict[str, Any] = Field(default_factory=dict)
    action: Verdict
    reason: str = ""
    priority: int = Field(default=100, ge=0, le=1_000_000)
    enabled: bool = True


class PolicyDocument(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    apiVersion: Literal["aae-observability/v1", "acs/v1"] = "aae-observability/v1"
    kind: Literal["Policy"] = "Policy"
    metadata: dict[str, Any] = Field(default_factory=dict)
    default_action: Verdict = Verdict.DENY
    rules: tuple[PolicyRule, ...] = ()

    @field_validator("rules")
    @classmethod
    def unique_rule_ids(cls, value: tuple[PolicyRule, ...]) -> tuple[PolicyRule, ...]:
        ids = [rule.id for rule in value]
        if len(ids) != len(set(ids)):
            raise ValueError("policy rule ids must be unique")
        return value
