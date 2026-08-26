# Migration to aae-observability 0.6.2

Release 0.6.2 replaces the former AGOV package identity with **aae-observability**.
This is an intentional clean rename. The former `agov` import namespace and CLI are not shipped.

## Installation

```bash
pip uninstall agov
pip install aae-observability==0.6.2
```

## Python imports

```python
# Before
import agov

# After
import aae_observability
```

Replace `agov.` with `aae_observability.` in imports, decorators, type references,
mock targets, and plugin implementations.

## Public configuration type

`AgovConfig` is now `AaeObservabilityConfig`.

## CLI

```bash
# Before
agov version

# After
aae-observability version
```

## Environment variables

Replace the `AGOV_` prefix with `AAE_OBSERVABILITY_`. Standard `OTEL_*` compatibility
variables remain unchanged.

## Runtime identifiers

The rename also changes package-owned telemetry scopes, custom attributes, metrics,
events, audit schema identifiers, policy schema identifiers, decorator markers, plugin
entry-point group, logger names, and worker thread names. Update dashboards, alerts,
Splunk searches, policy documents, and integrations that match those literal values.

Policy documents now use:

```yaml
apiVersion: aae-observability/v1
kind: Policy
```

The compatible external `acs/v1` policy version remains supported.
