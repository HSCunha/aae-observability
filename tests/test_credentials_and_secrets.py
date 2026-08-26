import sys
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest

import aae_observability
from aae_observability.config import AuthMode


class FakeCredential:
    def get_token(self, *scopes: str, **kwargs: Any) -> object:
        return object()


class FakeSecretClient:
    def __init__(self, *, vault_url: str, credential: object) -> None:
        self.vault_url = vault_url
        self.credential = credential

    def get_secret(self, name: str) -> object:
        assert name == "eventhub-connection"
        return SimpleNamespace(value="Endpoint=sb://safe/;SharedAccessKey=private")


def test_connection_string_mode_does_not_build_token_credential() -> None:
    config = aae_observability.TelemetryConfig(
        auth_mode=AuthMode.CONNECTION_STRING,
        connection_string="Endpoint=sb://safe/;SharedAccessKey=private",
    )
    assert aae_observability.build_azure_credential(config) is None


def test_default_credential_factory(monkeypatch: pytest.MonkeyPatch) -> None:
    created: dict[str, object] = {}

    class Default:
        def __init__(self, **kwargs: object) -> None:
            created.update(kwargs)

        def get_token(self, *scopes: str, **kwargs: Any) -> object:
            return object()

    class Managed(Default):
        pass

    azure = ModuleType("azure")
    identity = ModuleType("azure.identity")
    identity.DefaultAzureCredential = Default  # type: ignore[attr-defined]
    identity.ManagedIdentityCredential = Managed  # type: ignore[attr-defined]
    azure.identity = identity  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "azure", azure)
    monkeypatch.setitem(sys.modules, "azure.identity", identity)
    config = aae_observability.TelemetryConfig(managed_identity_client_id="client-id")
    assert isinstance(aae_observability.build_azure_credential(config), Default)
    assert created == {"managed_identity_client_id": "client-id"}


def test_managed_identity_factory(monkeypatch: pytest.MonkeyPatch) -> None:
    created: dict[str, object] = {}

    class Managed:
        def __init__(self, **kwargs: object) -> None:
            created.update(kwargs)

        def get_token(self, *scopes: str, **kwargs: Any) -> object:
            return object()

    azure = ModuleType("azure")
    identity = ModuleType("azure.identity")
    identity.DefaultAzureCredential = Managed  # type: ignore[attr-defined]
    identity.ManagedIdentityCredential = Managed  # type: ignore[attr-defined]
    azure.identity = identity  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "azure", azure)
    monkeypatch.setitem(sys.modules, "azure.identity", identity)
    config = aae_observability.TelemetryConfig(
        auth_mode=AuthMode.MANAGED_IDENTITY,
        managed_identity_client_id="managed-client",
    )
    assert isinstance(aae_observability.build_azure_credential(config), Managed)
    assert created == {"client_id": "managed-client"}


def test_key_vault_resolver_and_secret_safe_error() -> None:
    resolver = aae_observability.KeyVaultSecretResolver(
        "https://vault.vault.azure.net",
        FakeCredential(),
        client_factory=FakeSecretClient,
    )
    assert resolver.resolve("eventhub-connection").startswith("Endpoint=sb://")

    class Broken:
        def __init__(self, **kwargs: object) -> None:
            pass

        def get_secret(self, name: str) -> object:
            raise RuntimeError("private secret content")

    broken = aae_observability.KeyVaultSecretResolver(
        "https://vault.vault.azure.net", FakeCredential(), client_factory=Broken
    )
    with pytest.raises(aae_observability.SecretResolutionError) as caught:
        broken.resolve("eventhub-connection")
    assert "private secret content" not in str(caught.value)


def test_resolve_telemetry_secret_keeps_value_redacted() -> None:
    class Resolver:
        def resolve(self, name: str) -> str:
            assert name == "eventhub-connection"
            return "Endpoint=sb://safe/;SharedAccessKey=private"

    config = aae_observability.TelemetryConfig(
        auth_mode=AuthMode.CONNECTION_STRING,
        key_vault_url="https://vault.vault.azure.net",
        connection_string_secret_name="eventhub-connection",
    )
    resolved = aae_observability.resolve_telemetry_secrets(
        config, FakeCredential(), resolver=Resolver()
    )
    assert resolved.connection_string is not None
    assert resolved.connection_string.get_secret_value().endswith("private")
    assert "private" not in repr(resolved)


def test_secret_configuration_validation() -> None:
    with pytest.raises(Exception, match="key_vault_url"):
        aae_observability.TelemetryConfig(
            auth_mode=AuthMode.CONNECTION_STRING,
            connection_string_secret_name="eventhub-connection",
        )
    with pytest.raises(Exception, match="mutually exclusive"):
        aae_observability.TelemetryConfig(
            auth_mode=AuthMode.CONNECTION_STRING,
            connection_string="Endpoint=sb://safe/;SharedAccessKey=private",
            key_vault_url="https://vault.vault.azure.net",
            connection_string_secret_name="eventhub-connection",
        )


def test_credential_and_key_vault_environment_injection() -> None:
    config = aae_observability.load_layered_config(
        environ={
            "AAE_OBSERVABILITY_AUTH_MODE": "connection_string",
            "AAE_OBSERVABILITY_MANAGED_IDENTITY_CLIENT_ID": "client-id",
            "AAE_OBSERVABILITY_KEY_VAULT_URL": "https://vault.vault.azure.net",
            "AAE_OBSERVABILITY_CONNECTION_STRING_SECRET_NAME": "eventhub-connection",
        }
    )
    assert config.telemetry.managed_identity_client_id == "client-id"
    assert config.telemetry.connection_string_secret_name == "eventhub-connection"
