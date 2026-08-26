# aae-observability

## Release 0.6.3

Release 0.6.3 hardens the package for publication to TestPyPI and PyPI. It adds Trusted Publishing automation, artifact validation, clean-wheel smoke tests, modern license metadata, provenance attestations, and a controlled publishing runbook.

```python
import aae_observability

aae_observability.configure()


@aae_observability.instrument(agent_name="planner")
def run_agent(value: str) -> str:
    return value
```

See `PUBLISHING.md` for one-time PyPI configuration and the TestPyPI-to-PyPI promotion process.

### Release 0.5.2

Release 0.5.2 adds thread-safe hot reload for configuration and governance policy sources.
Fully validated candidates are applied as atomic generations, while invalid updates preserve the
last known-good runtime state.

```python
aae_observability.configure(
    config_file="aae_observability.toml",
    governance=aae_observability.GovernanceConfig(
        hot_reload_enabled=True,
        hot_reload_interval_ms=1000,
    ),
)
```

The watcher monitors the configuration file and the configured local policy source. Each new
invocation reads the active generation, while in-flight invocations retain the immutable settings
with which they started. `aae_observability.shutdown()` stops the watcher before closing telemetry resources.

Reload events contain outcome, generation, changed source names, timestamp, and sanitized error
type only. File contents, configuration values, policy values, and exception text are excluded.

### Release 0.5.1

Release 0.5.1 adds Azure credential and optional Key Vault secret injection.

```python
config = aae_observability.TelemetryConfig(
    auth_mode="managed_identity",
    managed_identity_client_id="<user-assigned-client-id>",
)
credential = aae_observability.build_azure_credential(config)
```

`DefaultAzureCredential` supports local development and Azure-hosted workloads, while
`ManagedIdentityCredential` provides an explicit production identity path. Connection-string
authentication remains available for development and compatibility scenarios.

Install the optional Key Vault integration with `pip install "aae-observability[keyvault]"` and resolve a
configured connection-string secret without placing its value in source or configuration files.
Resolved values remain wrapped in Pydantic `SecretStr` and are not included in model repr output.

### Release 0.5.0

Release 0.5.0 adds layered runtime configuration with deterministic precedence:

1. Explicit fields supplied to `aae_observability.configure()`
2. `AAE_OBSERVABILITY_*` and compatible `OTEL_*` environment variables
3. TOML or JSON configuration file
4. Validated package defaults

```python
aae_observability.configure(
    config_file="aae_observability.toml",
    telemetry=aae_observability.TelemetryConfig(service_name="planner"),
)
```

Event Hub namespace/name, buffering, batch size, flush interval, sampling, and policy
source can now be injected without changing application code. Standard HTTP OTLP Collector
endpoints are ignored by the Event Hub compatibility adapter; `sb://`, `amqps://`, and Azure
Service Bus HTTPS endpoints are recognized.


