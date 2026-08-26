# Package Rename Impact Map

## Release

- Baseline: 0.6.1
- Target: 0.6.2
- Distribution: `agov` to `aae-observability`
- Import root: `agov` to `aae_observability`
- CLI: `agov` to `aae-observability`
- Compatibility policy: clean rename, with no legacy import shim

## Updated surfaces

1. **Repository and source layout**
   - Repository root renamed to `aae-observability`.
   - Source root renamed to `src/aae_observability`.
   - All internal and external imports point to `aae_observability`.

2. **Packaging and build metadata**
   - PEP 621 distribution name, Hatch wheel package, MyPy target, Pytest coverage source,
     project URLs, console entry point, CI wheel smoke test, and build paths updated.

3. **Public Python API**
   - `AgovConfig` renamed to `AaeObservabilityConfig`.
   - Decorator and framework marker attributes use the `__aae_observability_*__` prefix.
   - Package metadata and version updated to 0.6.2.

4. **Configuration**
   - Environment variables use `AAE_OBSERVABILITY_*`.
   - Standard compatible `OTEL_*` variables are unchanged.
   - Example configuration filenames and documentation are renamed.

5. **Observability identities**
   - Tracer and meter scope names use `aae-observability`.
   - Package-owned attributes, events, and metrics use the `aae.observability.*` namespace.
   - The telemetry SDK name is `aae-observability`.

6. **Governance contracts**
   - Native policy schema changed from `agov/v1` to `aae-observability/v1`.
   - External `acs/v1` compatibility remains available.
   - Audit schema changed to `aae-observability.audit/v1`.

7. **Extension and runtime integration**
   - Framework adapter entry-point group, logger names, reloader thread name, mock markers,
     and test integration environment variables updated.

8. **Tests and automation**
   - Test imports, fixtures, assertions, mock targets, CLI expectations, telemetry names,
     policy samples, and live Event Hub variable names updated.
   - CI installs and imports the renamed wheel in a clean virtual environment.

9. **Documentation**
   - README, implementation plan, contribution guidance, release notes, examples,
     installation commands, and migration instructions updated.

## Consumer actions

Consumers must update installation manifests, Python imports, CLI invocations,
environment variables, policy schemas, plugin entry points, dashboards, Splunk searches,
alerts, mocks, and any literal telemetry filters that use the former package identity.
