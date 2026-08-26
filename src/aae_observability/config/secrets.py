"""Optional Azure Key Vault secret resolution for configuration values."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol, runtime_checkable

from pydantic import SecretStr

from aae_observability.config.credentials import TokenCredential
from aae_observability.config.models import TelemetryConfig


class SecretResolutionError(RuntimeError):
    """Raised when a configured secret cannot be resolved."""


@runtime_checkable
class SecretResolver(Protocol):
    """Resolve a named secret without exposing it in diagnostics."""

    def resolve(self, name: str) -> str:
        """Return the secret value."""
        ...


class KeyVaultSecretResolver:
    """Azure Key Vault resolver with an injectable client for isolated testing."""

    def __init__(
        self,
        vault_url: str,
        credential: TokenCredential,
        *,
        client_factory: Callable[..., Any] | None = None,
    ) -> None:
        if not vault_url.strip():
            raise ValueError("vault_url must not be empty")
        if client_factory is None:
            try:
                from azure.keyvault.secrets import SecretClient
            except ImportError as exc:
                raise SecretResolutionError(
                    "Key Vault resolution requires the 'azure-keyvault-secrets' package"
                ) from exc
            client_factory = SecretClient
        self._client = client_factory(vault_url=vault_url, credential=credential)

    def resolve(self, name: str) -> str:
        if not name.strip():
            raise ValueError("secret name must not be empty")
        try:
            secret = self._client.get_secret(name)
            value = getattr(secret, "value", None)
            if not isinstance(value, str) or not value:
                raise SecretResolutionError("Key Vault returned an empty secret")
            return value
        except SecretResolutionError:
            raise
        except Exception as exc:
            raise SecretResolutionError("unable to resolve configured Key Vault secret") from exc


def resolve_telemetry_secrets(
    config: TelemetryConfig,
    credential: TokenCredential | None,
    *,
    resolver: SecretResolver | None = None,
) -> TelemetryConfig:
    """Return a copied telemetry model with its configured connection secret resolved."""
    secret_name = config.connection_string_secret_name
    if secret_name is None:
        return config
    if resolver is None:
        if config.key_vault_url is None or credential is None:
            raise SecretResolutionError(
                "Key Vault URL and a token credential are required for secret resolution"
            )
        resolver = KeyVaultSecretResolver(config.key_vault_url, credential)
    value = resolver.resolve(secret_name)
    return config.model_copy(update={"connection_string": SecretStr(value)})
