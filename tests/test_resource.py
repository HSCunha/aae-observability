"""Tests for the Resource factory."""

import pytest

from aae_observability import build_resource, semconv


def attributes(resource: object) -> dict[str, object]:
    return dict(resource.attributes)


def test_resource_contains_service_and_genai_attributes() -> None:
    resource = build_resource(
        service_name="agent-service",
        service_namespace="teva.ai",
        environment="test",
        agent_name="planner",
        agent_id="agent-1",
    )
    attrs = attributes(resource)
    assert attrs[semconv.SERVICE_NAME] == "agent-service"
    assert attrs[semconv.SERVICE_NAMESPACE] == "teva.ai"
    assert attrs[semconv.DEPLOYMENT_ENVIRONMENT] == "test"
    assert attrs[semconv.GEN_AI_AGENT_NAME] == "planner"
    assert attrs[semconv.GEN_AI_AGENT_ID] == "agent-1"
    assert attrs[semconv.GEN_AI_SYSTEM] == "aae_observability"


def test_extra_attributes_take_precedence() -> None:
    resource = build_resource(
        service_name="agent-service",
        extra_attributes={semconv.SERVICE_NAMESPACE: "custom", "custom.key": "value"},
    )
    attrs = attributes(resource)
    assert attrs[semconv.SERVICE_NAMESPACE] == "custom"
    assert attrs["custom.key"] == "value"


def test_empty_service_name_is_rejected() -> None:
    with pytest.raises(ValueError, match="service_name"):
        build_resource(service_name="  ")
