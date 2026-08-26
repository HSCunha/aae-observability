"""Semantic-convention attribute names used by aae_observability."""

from typing import Final

SERVICE_NAME: Final = "service.name"
SERVICE_NAMESPACE: Final = "service.namespace"
SERVICE_VERSION: Final = "service.version"
DEPLOYMENT_ENVIRONMENT: Final = "deployment.environment.name"
DEPLOYMENT_ENVIRONMENT_LEGACY: Final = "deployment.environment"
TELEMETRY_SDK_NAME: Final = "telemetry.sdk.name"
TELEMETRY_SDK_LANGUAGE: Final = "telemetry.sdk.language"
TELEMETRY_SDK_VERSION: Final = "telemetry.sdk.version"
GEN_AI_SYSTEM: Final = "gen_ai.system"
GEN_AI_AGENT_NAME: Final = "gen_ai.agent.name"
GEN_AI_AGENT_ID: Final = "gen_ai.agent.id"
GEN_AI_OPERATION_NAME: Final = "gen_ai.operation.name"
GEN_AI_TOOL_NAME: Final = "gen_ai.tool.name"
AAE_OBSERVABILITY_SDK_NAME: Final = "aae-observability"
