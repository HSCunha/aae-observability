from pathlib import Path

import pytest

import aae_observability


def test_precedence_explicit_env_file_defaults(tmp_path: Path) -> None:
    path = tmp_path / "aae.observability.toml"
    path.write_text(
        '[telemetry]\nservice_name="file"\nbuffer_capacity=100\nmax_batch_size=50\n'
        '[governance]\npolicy_source="file.yaml"\n'
    )
    config = aae_observability.load_layered_config(
        path,
        telemetry=aae_observability.TelemetryConfig(service_name="explicit"),
        environ={
            "AAE_OBSERVABILITY_SERVICE_NAME": "env",
            "AAE_OBSERVABILITY_BUFFER_CAPACITY": "200",
        },
    )
    assert config.telemetry.service_name == "explicit"
    assert config.telemetry.buffer_capacity == 200
    assert config.telemetry.max_batch_size == 50
    assert config.governance.policy_source == "file.yaml"
    assert config.telemetry.flush_interval_ms == 5_000


def test_eventhub_and_runtime_values_from_environment() -> None:
    config = aae_observability.load_layered_config(
        environ={
            "AAE_OBSERVABILITY_EVENTHUB_NAMESPACE": "ns.servicebus.windows.net",
            "AAE_OBSERVABILITY_EVENTHUB_NAME": "telemetry",
            "AAE_OBSERVABILITY_MAX_BATCH_SIZE": "128",
            "AAE_OBSERVABILITY_FLUSH_INTERVAL_MS": "2500",
            "AAE_OBSERVABILITY_POLICY_SOURCE": "policies/prod.yaml",
        }
    )
    assert config.telemetry.eventhub_namespace == "ns.servicebus.windows.net"
    assert config.telemetry.eventhub_name == "telemetry"
    assert config.telemetry.max_batch_size == 128
    assert config.telemetry.flush_interval_ms == 2_500
    assert config.governance.policy_source == "policies/prod.yaml"


def test_otel_endpoint_and_timeout_compatibility() -> None:
    config = aae_observability.load_layered_config(
        environ={
            "OTEL_EXPORTER_OTLP_ENDPOINT": "sb://ns.servicebus.windows.net/agent-telemetry",
            "OTEL_EXPORTER_OTLP_TIMEOUT": "3.5",
            "OTEL_SERVICE_NAME": "maf-agent",
        }
    )
    assert config.telemetry.eventhub_namespace == "ns.servicebus.windows.net"
    assert config.telemetry.eventhub_name == "agent-telemetry"
    assert config.telemetry.flush_interval_ms == 3_500
    assert config.telemetry.service_name == "maf-agent"


def test_invalid_environment_value_is_safe() -> None:
    with pytest.raises(
        aae_observability.EnvironmentConfigError, match="AAE_OBSERVABILITY_BUFFER_CAPACITY"
    ):
        aae_observability.load_layered_config(environ={"AAE_OBSERVABILITY_BUFFER_CAPACITY": "many"})


def test_configure_uses_layered_configuration(tmp_path: Path) -> None:
    path = tmp_path / "aae.observability.json"
    path.write_text('{"telemetry":{"service_name":"file-agent"}}')
    aae_observability.configure(
        config_file=str(path), environ={"AAE_OBSERVABILITY_SERVICE_NAME": "env-agent"}
    )
    from aae_observability.api import _STATE

    assert _STATE.telemetry is not None
    assert _STATE.telemetry.service_name == "env-agent"
    aae_observability.shutdown()
