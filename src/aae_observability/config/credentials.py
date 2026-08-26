"""Azure credential construction without eager authentication or secret logging."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from aae_observability.config.models import AuthMode, TelemetryConfig


class CredentialConfigurationError(RuntimeError):
    """Raised when an Azure credential cannot be constructed safely."""


@runtime_checkable
class TokenCredential(Protocol):
    """Minimal structural contract implemented by Azure token credentials."""

    def get_token(self, *scopes: str, **kwargs: Any) -> Any:
        """Acquire an access token for the requested scopes."""
        ...


def build_azure_credential(config: TelemetryConfig) -> TokenCredential | None:
    """Build the configured Azure credential, or return None for connection strings.

    Credential construction is lazy with respect to authentication. No token request is
    performed here, allowing applications to configure cleanly before Azure access occurs.
    """
    if config.auth_mode is AuthMode.CONNECTION_STRING:
        return None
    try:
        from azure.identity import DefaultAzureCredential, ManagedIdentityCredential
    except ImportError as exc:
        raise CredentialConfigurationError(
            "Azure credential authentication requires the 'azure-identity' package"
        ) from exc

    client_id = config.managed_identity_client_id
    if config.auth_mode is AuthMode.MANAGED_IDENTITY:
        return (
            ManagedIdentityCredential(client_id=client_id)
            if client_id
            else ManagedIdentityCredential()
        )
    kwargs: dict[str, Any] = {}
    if client_id:
        kwargs["managed_identity_client_id"] = client_id
    return DefaultAzureCredential(**kwargs)
