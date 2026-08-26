"""Tests for validated configuration and file loading."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

import aae_observability
from aae_observability.config import AuthMode, ConfigFileError


def test_default_configuration_is_valid() -> None:
    config = aae_observability.AaeObservabilityConfig()
    assert config.telemetry.service_name == "aae_observability-agent"
    assert config.governance.fail_closed is True


def test_unknown_fields_are_rejected() -> None:
    with pytest.raises(ValidationError, match="extra_forbidden"):
        aae_observability.TelemetryConfig(unknown_setting=True)


def test_bounds_and_dependent_batch_settings_are_validated() -> None:
    with pytest.raises(ValidationError):
        aae_observability.TelemetryConfig(sampling_ratio=1.1)
    with pytest.raises(ValidationError, match="max_batch_size"):
        aae_observability.TelemetryConfig(buffer_capacity=10, max_batch_size=11)


def test_event_hub_endpoint_must_be_complete() -> None:
    with pytest.raises(ValidationError, match="must be provided together"):
        aae_observability.TelemetryConfig(eventhub_namespace="example.servicebus.windows.net")


def test_connection_string_auth_requires_a_secret() -> None:
    with pytest.raises(ValidationError, match="connection_string is required"):
        aae_observability.TelemetryConfig(auth_mode=AuthMode.CONNECTION_STRING)


def test_connection_string_is_redacted() -> None:
    config = aae_observability.AaeObservabilityConfig(
        telemetry=aae_observability.TelemetryConfig(
            auth_mode=AuthMode.CONNECTION_STRING,
            connection_string="Endpoint=sb://example/;SharedAccessKey=secret",
        )
    )
    assert config.redacted_dict()["telemetry"]["connection_string"] == "**********"
    assert "secret" not in repr(config)


def test_load_toml_configuration(tmp_path: Path) -> None:
    path = tmp_path / "aae.observability.toml"
    path.write_text(
        '[telemetry]\nservice_name = "planner"\nbuffer_capacity = 20\nmax_batch_size = 10\n'
        "[governance]\nfail_closed = true\nevaluation_timeout_ms = 100\n"
    )
    config = aae_observability.load_config(path)
    assert config.telemetry.service_name == "planner"
    assert config.telemetry.max_batch_size == 10
    assert config.governance.evaluation_timeout_ms == 100


def test_load_json_configuration(tmp_path: Path) -> None:
    path = tmp_path / "aae.observability.json"
    path.write_text(json.dumps({"telemetry": {"service_name": "json-agent"}}))
    assert aae_observability.load_config(path).telemetry.service_name == "json-agent"


def test_missing_and_unsupported_files_are_reported(tmp_path: Path) -> None:
    with pytest.raises(ConfigFileError, match="not found"):
        aae_observability.load_config(tmp_path / "missing.toml")
    unsupported = tmp_path / "aae.observability.yaml"
    unsupported.write_text("telemetry: {}")
    with pytest.raises(ConfigFileError, match=r"must use \.toml or \.json"):
        aae_observability.load_config(unsupported)
