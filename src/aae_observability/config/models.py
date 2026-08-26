"""Validated configuration models for aae_observability."""

from enum import Enum
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator, model_validator


class DropPolicy(str, Enum):
    """Behavior when the telemetry buffer is full."""

    DROP_OLDEST = "drop_oldest"
    DROP_NEW = "drop_new"


class AuthMode(str, Enum):
    """Authentication mode for the Event Hub exporter."""

    DEFAULT_CREDENTIAL = "default_credential"
    MANAGED_IDENTITY = "managed_identity"
    CONNECTION_STRING = "connection_string"


class TelemetryConfig(BaseModel):
    """Validated telemetry and Event Hub settings."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    service_name: str = Field(default="aae_observability-agent", min_length=1, max_length=255)
    service_namespace: str = Field(default="aae_observability", min_length=1, max_length=255)
    environment: str = Field(default="development", min_length=1, max_length=64)
    eventhub_namespace: str | None = None
    eventhub_name: str | None = None
    connection_string: SecretStr | None = Field(default=None, repr=False)
    managed_identity_client_id: str | None = None
    key_vault_url: str | None = None
    connection_string_secret_name: str | None = Field(default=None, repr=False)
    buffer_capacity: int = Field(default=10_000, ge=1, le=10_000_000)
    max_batch_size: int = Field(default=512, ge=1, le=10_000)
    flush_interval_ms: int = Field(default=5_000, ge=100, le=300_000)
    drop_policy: DropPolicy = DropPolicy.DROP_OLDEST
    auth_mode: AuthMode = AuthMode.DEFAULT_CREDENTIAL
    sampling_ratio: float = Field(default=1.0, ge=0.0, le=1.0)
    capture_sensitive_data: bool = False
    sensitive_data_max_length: int = Field(default=2_048, ge=64, le=65_536)

    @field_validator(
        "eventhub_namespace",
        "eventhub_name",
        "managed_identity_client_id",
        "key_vault_url",
        "connection_string_secret_name",
        mode="before",
    )
    @classmethod
    def empty_optional_strings_become_none(cls, value: Any) -> Any:
        """Treat empty optional endpoint values as absent."""
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @model_validator(mode="after")
    def validate_event_hub_and_batch_settings(self) -> Self:
        """Validate dependent Event Hub, auth, buffer, and batch settings."""
        endpoint_fields = (self.eventhub_namespace, self.eventhub_name)
        if any(endpoint_fields) and not all(endpoint_fields):
            raise ValueError("eventhub_namespace and eventhub_name must be provided together")
        has_direct_secret = self.connection_string is not None
        has_key_vault_secret = self.connection_string_secret_name is not None
        if self.auth_mode is AuthMode.CONNECTION_STRING and not (
            has_direct_secret or has_key_vault_secret
        ):
            raise ValueError(
                "connection_string is required when auth_mode is connection_string "
                "unless connection_string_secret_name is configured"
            )
        if has_direct_secret and has_key_vault_secret:
            raise ValueError(
                "connection_string and connection_string_secret_name are mutually exclusive"
            )
        if has_key_vault_secret and self.key_vault_url is None:
            raise ValueError("key_vault_url is required for connection_string_secret_name")
        if self.auth_mode is not AuthMode.CONNECTION_STRING and (
            self.connection_string is not None or self.connection_string_secret_name is not None
        ):
            raise ValueError(
                "connection_string may only be set when auth_mode is connection_string"
            )
        if self.max_batch_size > self.buffer_capacity:
            raise ValueError("max_batch_size must not exceed buffer_capacity")
        return self


class GovernanceConfig(BaseModel):
    """Validated governance policy settings."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    enabled: bool = True
    policy_source: str | None = None
    fail_closed: bool = True
    evaluation_timeout_ms: int = Field(default=50, ge=1, le=30_000)
    audit_enabled: bool = True
    hot_reload_enabled: bool = False
    hot_reload_interval_ms: int = Field(default=1_000, ge=100, le=300_000)

    @field_validator("policy_source", mode="before")
    @classmethod
    def empty_policy_source_becomes_none(cls, value: Any) -> Any:
        """Treat an empty policy source as absent."""
        if isinstance(value, str) and not value.strip():
            return None
        return value


class AaeObservabilityConfig(BaseModel):
    """Top-level configuration document."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    telemetry: TelemetryConfig = Field(default_factory=TelemetryConfig)
    governance: GovernanceConfig = Field(default_factory=GovernanceConfig)

    def redacted_dict(self) -> dict[str, Any]:
        """Return JSON-safe effective configuration with secrets redacted."""
        data = self.model_dump(mode="json")
        connection_string = data["telemetry"].get("connection_string")
        if connection_string is not None:
            data["telemetry"]["connection_string"] = "**********"
        return data
