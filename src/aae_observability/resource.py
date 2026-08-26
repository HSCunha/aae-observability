"""OpenTelemetry Resource factory with a bootstrap fallback."""

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from aae_observability import semconv
from aae_observability._version import __version__

try:
    from opentelemetry.sdk.resources import Resource as OTelResource
except ImportError:  # pragma: no cover - used only in bootstrap environments
    OTelResource = None  # type: ignore[assignment,misc]


@dataclass(frozen=True, slots=True)
class AaeObservabilityResource:
    """Minimal resource compatible with the OTel ``attributes`` contract."""

    attributes: Mapping[str, Any]


def build_resource(
    *,
    service_name: str,
    service_namespace: str = "aae_observability",
    environment: str = "development",
    service_version: str | None = None,
    agent_name: str | None = None,
    agent_id: str | None = None,
    gen_ai_system: str = "aae_observability",
    extra_attributes: Mapping[str, Any] | None = None,
) -> Any:
    """Create a Resource stamped with service and GenAI identity attributes."""
    if not service_name.strip():
        raise ValueError("service_name must be a non-empty string")

    attributes: dict[str, Any] = {
        semconv.SERVICE_NAME: service_name,
        semconv.SERVICE_NAMESPACE: service_namespace,
        semconv.SERVICE_VERSION: service_version or __version__,
        semconv.DEPLOYMENT_ENVIRONMENT: environment,
        semconv.DEPLOYMENT_ENVIRONMENT_LEGACY: environment,
        semconv.TELEMETRY_SDK_NAME: semconv.AAE_OBSERVABILITY_SDK_NAME,
        semconv.TELEMETRY_SDK_LANGUAGE: "python",
        semconv.TELEMETRY_SDK_VERSION: __version__,
        semconv.GEN_AI_SYSTEM: gen_ai_system,
    }
    if agent_name is not None:
        attributes[semconv.GEN_AI_AGENT_NAME] = agent_name
    if agent_id is not None:
        attributes[semconv.GEN_AI_AGENT_ID] = agent_id
    if extra_attributes:
        attributes.update(extra_attributes)

    if OTelResource is not None:
        return OTelResource.create(attributes)
    return AaeObservabilityResource(MappingProxyType(attributes))


def sdk_available() -> bool:
    """Return whether the OpenTelemetry SDK is available."""
    return OTelResource is not None
