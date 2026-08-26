"""Layered runtime configuration resolution for aae_observability."""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from pydantic import ValidationError

from aae_observability.config.loader import load_config
from aae_observability.config.models import (
    AaeObservabilityConfig,
    GovernanceConfig,
    TelemetryConfig,
)


class EnvironmentConfigError(ValueError):
    """Raised when an environment configuration value cannot be parsed."""


_TELEMETRY_ENV: dict[str, tuple[str, Any]] = {
    "AAE_OBSERVABILITY_SERVICE_NAME": ("service_name", str),
    "AAE_OBSERVABILITY_SERVICE_NAMESPACE": ("service_namespace", str),
    "AAE_OBSERVABILITY_ENVIRONMENT": ("environment", str),
    "AAE_OBSERVABILITY_EVENTHUB_NAMESPACE": ("eventhub_namespace", str),
    "AAE_OBSERVABILITY_EVENTHUB_NAME": ("eventhub_name", str),
    "AAE_OBSERVABILITY_EVENTHUB_CONNECTION_STRING": ("connection_string", str),
    "AAE_OBSERVABILITY_MANAGED_IDENTITY_CLIENT_ID": ("managed_identity_client_id", str),
    "AAE_OBSERVABILITY_KEY_VAULT_URL": ("key_vault_url", str),
    "AAE_OBSERVABILITY_CONNECTION_STRING_SECRET_NAME": ("connection_string_secret_name", str),
    "AAE_OBSERVABILITY_BUFFER_CAPACITY": ("buffer_capacity", int),
    "AAE_OBSERVABILITY_MAX_BATCH_SIZE": ("max_batch_size", int),
    "AAE_OBSERVABILITY_FLUSH_INTERVAL_MS": ("flush_interval_ms", int),
    "AAE_OBSERVABILITY_DROP_POLICY": ("drop_policy", str),
    "AAE_OBSERVABILITY_AUTH_MODE": ("auth_mode", str),
    "AAE_OBSERVABILITY_SAMPLING_RATIO": ("sampling_ratio", float),
    "AAE_OBSERVABILITY_CAPTURE_SENSITIVE_DATA": ("capture_sensitive_data", "bool"),
    "AAE_OBSERVABILITY_SENSITIVE_DATA_MAX_LENGTH": ("sensitive_data_max_length", int),
    "OTEL_SERVICE_NAME": ("service_name", str),
    "OTEL_EXPORTER_OTLP_TIMEOUT": ("flush_interval_ms", "seconds_to_ms"),
}
_GOVERNANCE_ENV: dict[str, tuple[str, Any]] = {
    "AAE_OBSERVABILITY_GOVERNANCE_ENABLED": ("enabled", "bool"),
    "AAE_OBSERVABILITY_POLICY_SOURCE": ("policy_source", str),
    "AAE_OBSERVABILITY_FAIL_CLOSED": ("fail_closed", "bool"),
    "AAE_OBSERVABILITY_EVALUATION_TIMEOUT_MS": ("evaluation_timeout_ms", int),
    "AAE_OBSERVABILITY_AUDIT_ENABLED": ("audit_enabled", "bool"),
    "AAE_OBSERVABILITY_HOT_RELOAD_ENABLED": ("hot_reload_enabled", "bool"),
    "AAE_OBSERVABILITY_HOT_RELOAD_INTERVAL_MS": ("hot_reload_interval_ms", int),
}


def _convert(name: str, value: str, converter: Any) -> Any:
    try:
        if converter == "bool":
            normalized = value.strip().lower()
            if normalized in {"1", "true", "yes", "on"}:
                return True
            if normalized in {"0", "false", "no", "off"}:
                return False
            raise ValueError("expected true/false, 1/0, yes/no, or on/off")
        if converter == "seconds_to_ms":
            return int(float(value) * 1_000)
        return converter(value)
    except (TypeError, ValueError) as exc:
        raise EnvironmentConfigError(f"invalid value for {name}: {exc}") from exc


def _eventhub_from_otlp_endpoint(endpoint: str) -> dict[str, str]:
    parsed = urlparse(endpoint)
    if parsed.scheme not in {"sb", "amqps", "https"} or not parsed.hostname:
        raise EnvironmentConfigError(
            "OTEL_EXPORTER_OTLP_ENDPOINT must identify an Event Hub namespace and hub"
        )
    path = parsed.path.strip("/")
    if not path:
        raise EnvironmentConfigError(
            "OTEL_EXPORTER_OTLP_ENDPOINT must include the Event Hub name in its path"
        )
    return {"eventhub_namespace": parsed.hostname, "eventhub_name": path.split("/")[0]}


def environment_overrides(environ: Mapping[str, str] | None = None) -> dict[str, dict[str, Any]]:
    """Return validated raw overrides from AAE_OBSERVABILITY and compatible OTEL variables."""
    source = os.environ if environ is None else environ
    telemetry: dict[str, Any] = {}
    governance: dict[str, Any] = {}
    endpoint = source.get("OTEL_EXPORTER_OTLP_ENDPOINT")
    if endpoint:
        parsed = urlparse(endpoint)
        # Standard HTTP OTLP Collector endpoints are intentionally ignored. Only
        # Event Hub-shaped endpoints are adapted into collector-less settings.
        if parsed.scheme in {"sb", "amqps"} or (
            parsed.scheme == "https" and (parsed.hostname or "").endswith(".servicebus.windows.net")
        ):
            telemetry.update(_eventhub_from_otlp_endpoint(endpoint))
    for env_name, (field, converter) in _TELEMETRY_ENV.items():
        if env_name in source and source[env_name] != "":
            telemetry[field] = _convert(env_name, source[env_name], converter)
    for env_name, (field, converter) in _GOVERNANCE_ENV.items():
        if env_name in source and source[env_name] != "":
            governance[field] = _convert(env_name, source[env_name], converter)
    return {"telemetry": telemetry, "governance": governance}


def _explicit_values(model: TelemetryConfig | GovernanceConfig | None) -> dict[str, Any]:
    if model is None:
        return {}
    return model.model_dump(include=model.model_fields_set)


def load_layered_config(
    config_file: str | Path | None = None,
    *,
    telemetry: TelemetryConfig | None = None,
    governance: GovernanceConfig | None = None,
    environ: Mapping[str, str] | None = None,
) -> AaeObservabilityConfig:
    """Resolve explicit values, environment, file, and defaults in precedence order.

    Precedence, highest first: explicitly set model fields, environment variables,
    configuration file values, then model defaults.
    """
    file_config = load_config(config_file) if config_file is not None else AaeObservabilityConfig()
    payload = file_config.model_dump()
    env = environment_overrides(environ)
    payload["telemetry"].update(env["telemetry"])
    payload["governance"].update(env["governance"])
    payload["telemetry"].update(_explicit_values(telemetry))
    payload["governance"].update(_explicit_values(governance))
    try:
        return AaeObservabilityConfig.model_validate(payload)
    except ValidationError:
        raise
