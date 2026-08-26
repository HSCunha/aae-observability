"""Configuration public API."""

from aae_observability.config.credentials import (
    CredentialConfigurationError,
    TokenCredential,
    build_azure_credential,
)
from aae_observability.config.layered import (
    EnvironmentConfigError,
    environment_overrides,
    load_layered_config,
)
from aae_observability.config.loader import ConfigFileError, load_config
from aae_observability.config.models import (
    AaeObservabilityConfig,
    AuthMode,
    DropPolicy,
    GovernanceConfig,
    TelemetryConfig,
)
from aae_observability.config.reload import (
    ReloadEvent,
    ReloadSnapshot,
    RuntimeConfigReloader,
    build_layered_reloader,
)
from aae_observability.config.secrets import (
    KeyVaultSecretResolver,
    SecretResolutionError,
    SecretResolver,
    resolve_telemetry_secrets,
)

__all__ = [
    "AaeObservabilityConfig",
    "AuthMode",
    "ConfigFileError",
    "CredentialConfigurationError",
    "DropPolicy",
    "EnvironmentConfigError",
    "GovernanceConfig",
    "KeyVaultSecretResolver",
    "ReloadEvent",
    "ReloadSnapshot",
    "RuntimeConfigReloader",
    "SecretResolutionError",
    "SecretResolver",
    "TelemetryConfig",
    "TokenCredential",
    "build_azure_credential",
    "build_layered_reloader",
    "environment_overrides",
    "load_config",
    "load_layered_config",
    "resolve_telemetry_secrets",
]
