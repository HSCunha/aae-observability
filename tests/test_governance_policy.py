from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

import aae_observability


def snap(*, agent="planner", tool=None, roles=(), context=None, attrs=None):
    return aae_observability.ActionSnapshot(
        aae_observability.AgentCall(agent_name=agent, tool_name=tool, attributes=attrs or {}),
        aae_observability.Identity(principal_id="u1", roles=roles),
        context or {},
    )


def policy(**kwargs):
    return aae_observability.PolicyDocument.model_validate(
        {"apiVersion": "aae-observability/v1", "kind": "Policy", **kwargs}
    )


def test_first_match_priority_and_default():
    p = policy(
        metadata={"name": "test"},
        default_action="deny",
        rules=[
            {
                "id": "later",
                "priority": 20,
                "condition": {"field": "call.agent_name", "eq": "planner"},
                "action": "allow",
            },
            {
                "id": "first",
                "priority": 10,
                "condition": {"field": "identity.roles", "contains": "blocked"},
                "action": "deny",
                "reason": "blocked role",
            },
        ],
    )
    e = aae_observability.LocalPolicyEngine(p)
    r = e.evaluate(snap(roles=("blocked",)))
    assert (
        r.verdict is aae_observability.Verdict.DENY
        and r.rule_id == "first"
        and r.reason == "blocked role"
    )
    assert e.evaluate(snap(agent="other")).verdict is aae_observability.Verdict.DENY


def test_all_any_not_and_operators():
    condition = {
        "all": [
            {"field": "call.tool_name", "in": ["delete", "drop"]},
            {
                "any": [
                    {"field": "identity.roles", "not_in": ["admin"]},
                    {"not": {"field": "context.approved", "eq": True}},
                ]
            },
            {"field": "context.risk", "ge": 7},
        ]
    }
    p = policy(
        default_action="allow",
        rules=[{"id": "protect", "condition": condition, "action": "require_approval"}],
    )
    e = aae_observability.LocalPolicyEngine(p)
    assert (
        e.evaluate(
            snap(tool="delete", roles=("user",), context={"risk": 8, "approved": False})
        ).verdict
        is aae_observability.Verdict.REQUIRE_APPROVAL
    )
    assert (
        e.evaluate(snap(tool="read", context={"risk": 8})).verdict
        is aae_observability.Verdict.ALLOW
    )


def test_matches_exists_and_nested_mapping():
    p = policy(
        default_action="deny",
        rules=[
            {
                "id": "match",
                "condition": {
                    "all": [
                        {"field": "call.agent_name", "matches": "plan.*"},
                        {"field": "context.region", "exists": True},
                        {"field": "context.region", "eq": "eu"},
                    ]
                },
                "action": "allow",
            }
        ],
    )
    assert aae_observability.LocalPolicyEngine(p).evaluate(snap(context={"region": "eu"})).allowed


def test_invalid_conditions_rejected_at_compile():
    with pytest.raises(ValueError, match="supported operator"):
        aae_observability.LocalPolicyEngine(
            policy(
                rules=[
                    {
                        "id": "bad",
                        "condition": {"field": "call.agent_name", "execute": "x"},
                        "action": "allow",
                    }
                ]
            )
        )
    with pytest.raises(ValueError, match="condition path"):
        aae_observability.LocalPolicyEngine(
            policy(
                rules=[
                    {
                        "id": "bad",
                        "condition": {"field": "system.secret", "eq": "x"},
                        "action": "allow",
                    }
                ]
            )
        )


def test_duplicate_ids_and_unknown_fields_rejected():
    with pytest.raises(ValidationError, match="unique"):
        policy(rules=[{"id": "x", "action": "allow"}, {"id": "x", "action": "deny"}])
    with pytest.raises(ValidationError):
        policy(extra="bad")


def test_disabled_rules_not_compiled():
    e = aae_observability.LocalPolicyEngine(
        policy(
            default_action="deny",
            rules=[{"id": "off", "enabled": False, "condition": {}, "action": "allow"}],
        )
    )
    assert (
        e.compiled_rule_count == 0 and e.evaluate(snap()).verdict is aae_observability.Verdict.DENY
    )


def test_yaml_and_json_loading(tmp_path: Path):
    y = tmp_path / "policy.yaml"
    y.write_text(
        "apiVersion: aae-observability/v1\n"
        "kind: Policy\n"
        "metadata:\n  name: demo\n"
        "default_action: deny\n"
        "rules:\n  - id: allow-search\n"
        "    condition:\n      field: call.tool_name\n"
        "      eq: search\n    action: allow\n"
    )
    p = aae_observability.load_policy(y)
    assert (
        p.metadata["name"] == "demo"
        and aae_observability.LocalPolicyEngine.from_file(str(y))
        .evaluate(snap(tool="search"))
        .allowed
    )
    j = tmp_path / "policy.json"
    j.write_text('{"apiVersion":"acs/v1","kind":"Policy","default_action":"deny","rules":[]}')
    assert aae_observability.load_policy(j).apiVersion == "acs/v1"


def test_policy_file_errors(tmp_path: Path):
    with pytest.raises(aae_observability.PolicyFileError, match="not found"):
        aae_observability.load_policy(tmp_path / "missing.yaml")
    bad = tmp_path / "policy.txt"
    bad.write_text("{}")
    with pytest.raises(aae_observability.PolicyFileError, match="must use"):
        aae_observability.load_policy(bad)


def test_acs_adapter_request_and_response():
    seen = {}

    def client(request: Any, timeout: int):
        seen.update(request=request, timeout=timeout)
        return {
            "verdict": "redact",
            "reason": "pii",
            "rule_id": "acs-1",
            "metadata": {"source": "acs"},
        }

    result = aae_observability.ACSPolicyEngine(client, timeout_ms=25).evaluate(
        snap(tool="search", roles=("user",), context={"region": "eu"})
    )
    assert (
        result.verdict is aae_observability.Verdict.REDACT
        and result.rule_id == "acs-1"
        and seen["timeout"] == 25
        and seen["request"]["identity"]["roles"] == ["user"]
    )


def test_acs_invalid_response_fails_closed_to_caller():
    with pytest.raises(ValueError, match="invalid verdict"):
        aae_observability.ACSPolicyEngine(lambda request, timeout: {"verdict": "unknown"}).evaluate(
            snap()
        )
