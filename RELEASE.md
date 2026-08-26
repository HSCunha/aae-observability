# Release Notes

This changelog follows Keep a Changelog principles and Semantic Versioning.

## [Unreleased]

### Planned
- Release 0.5.0: enterprise control-plane and runtime kill-switch integration.

## [0.4.3] - 2026-08-26

### Added
- Thread-safe `JsonLinesGovernanceAuditSink` with schema `aae_observability.audit/v1`.
- Bounded audit-file rotation and retention.
- Explicit audit flush, idempotent close, and exporter statistics.
- `CompositeGovernanceAuditSink` with destination failure isolation.
- `GovernanceReport` and immutable operational report snapshots.
- Bounded policy and rule cardinality controls.
- Public `get_governance_report()` API.
- Concurrency, rotation, lifecycle, reporting, and failure-isolation tests.

### Changed
- `aae_observability.shutdown()` flushes and closes configured audit sinks.
- Every configuration creates an internal operational governance report.
- Updated package version from `0.4.2` to `0.4.3`.

### Security
- Durable records exclude payloads, policy reasons, claims, credentials, and exception text.
- Audit exporter failure never changes the policy decision.
- Bounded rotation prevents unrestricted audit-file growth.

## [0.4.2] - 2026-08-26

### Added
- Governance decision, duration, error, and timeout metrics.
- Privacy-safe audit record and audit sink contracts.
- In-memory audit sink and outcome tests.

### Changed
- `aae_observability.configure()` accepts `governance_audit_sink`.
- Updated package version from `0.4.1` to `0.4.2`.

### Security
- Audit and metric records exclude invocation payloads, policy reasons, claims, and exception text.

## [0.4.1] - 2026-08-26

### Added
- Pre-invocation `ActionSnapshot` policy evaluation and enforcement.
- Enforcement for functions, coroutines, synchronous generators, and asynchronous generators.
- Synchronous and asynchronous policy-engine support.
- `GovernanceDeniedError`, `GovernanceEvaluationError`, and `GovernanceTimeoutError`.
- Fail-open and fail-closed evaluation behavior.
- Caller-bounded synchronous policy timeouts using non-waiting executor cleanup.
- Tests proving denied callables never execute application code.

### Changed
- Only `Verdict.ALLOW` continues wrapped execution.
- Updated package version from `0.4.0` to `0.4.1`.

### Security
- Governance exceptions exclude policy payloads and underlying exception text.

## [0.4.0] - 2026-08-26

### Added
- Validated `aae_observability/v1` and compatible `acs/v1` policy document models.
- YAML and JSON policy loading.
- Safe declarative condition compiler without Python `eval`.
- Logical and comparison operators across call, identity, and context snapshots.
- Priority-ordered, first-match local policy engine with compiled-rule caching.
- External ACS decision-authority adapter with timeout propagation and response validation.
- `aae_observability policy validate` CLI with normalized output.
- Governance schema, condition, loader, engine, ACS, and CLI tests.

### Changed
- Added PyYAML as a runtime dependency.
- Updated package version from `0.3.0` to `0.4.0`.

### Security
- Policy conditions are declarative and never executed with `eval`.
- Condition paths are restricted to `call`, `identity`, and `context`.
- Invalid paths and operators fail during compilation rather than at runtime.
- ACS requests omit raw function arguments and sensitive payloads.

### Roadmap note
- Releases 0.3.1, 0.3.2, and 0.3.3 remain planned and are not included in 0.4.0.

## [0.3.0] - 2026-08-25

### Added
- Typed span, metric, and log envelopes.
- Bounded FIFO buffer with atomic draining and overflow policies.
- Non-blocking contention drops and immutable buffer statistics.
- Buffered telemetry sink and buffer self-metrics.
- Concurrent producer, overflow, closure, and flush tests.

### Changed
- `aae_observability.configure()` creates a bounded buffered sink by default.
- Updated package version from `0.2.3` to `0.3.0`.

### Security
- Producers never wait for the internal buffer lock.
- Buffer self-metrics contain counts and ratios only.

## [0.2.3] - 2026-08-25

### Added
- Duck-typed Microsoft Agent Framework, LangChain, and multi-agent adapters.
- Ordered adapter registry, generic fallback, and third-party entry-point discovery.
- Optional extras `aae_observability[maf]`, `aae_observability[langchain]`, and `aae_observability[all]`.
- Native-instrumentation marker support to avoid duplicate spans.
- Run, trace, token, handoff, and correlation normalization tests.

### Changed
- Default configuration builds adapters in specific-to-generic order.
- Optional framework packages are not required for core imports.
- Updated package version from `0.2.2` to `0.2.3`.

### Security
- Plugin failures are isolated by default.
- Adapters inspect metadata without capturing message payloads.

## [0.2.2] - 2026-08-25

### Added
- Public `OperationType` model for `agent.run`, `llm.chat`, `tool.call`, `retrieval.query`, and `agent.handoff`.
- Formal operation-aware span naming and nested hierarchy support.
- OpenTelemetry counters for invocations, errors, cancellations, and token usage.
- OpenTelemetry histogram for operation duration and up/down counter for active operations.
- Low-cardinality metric dimensions limited to operation, framework, and outcome.
- Adapter-supplied input and output token-usage metrics.
- Parent-based trace-ID ratio sampling when `aae_observability` owns the tracer provider.
- Optional application-supplied `MeterProvider`.
- Sensitive-input and sensitive-output span events behind explicit configuration opt-in.
- Configurable sensitive-data serialization length and application redaction function.
- Duplicate decorator protection that avoids nested duplicate spans.
- Tests for hierarchy, metrics, token usage, sampling, sensitive controls, cardinality, and duplicate instrumentation.

### Changed
- Default agent operation name changed from provisional `invoke_agent` to `agent.run`.
- Default tool operation name changed from provisional `execute_tool` to `tool.call`.
- `aae_observability.configure()` now initializes a meter provider and metric instruments.
- `aae_observability.shutdown()` now flushes and shuts down metric resources.
- `TelemetryConfig` now includes `sensitive_data_max_length`.
- Updated package version from `0.2.1` to `0.2.2`.

### Security
- Sensitive data remains disabled by default and requires explicit opt-in.
- Sensitive payloads support application redaction and strict size truncation.
- Metric labels never contain payloads, agent names, prompts, responses, identifiers, or exception messages.
- Generator yield values are not captured as sensitive output.

## [0.2.1] - 2026-08-25

### Added
- Coroutine instrumentation covering the complete awaited lifecycle.
- Context propagation across `await` boundaries using OpenTelemetry and Python `contextvars`.
- Concurrent coroutine isolation validated with `asyncio.gather`.
- Nested parent-child span propagation for instrumented coroutine calls.
- Cancellation recording with `aae_observability.cancelled = true` and unchanged `CancelledError` propagation.
- Synchronous generator instrumentation through completion, exception, `send`, `throw`, and explicit closure.
- Asynchronous generator instrumentation through completion, exception, and explicit closure.
- Generator context isolation between yields to prevent active-span leakage into consumer code.
- Lifecycle tests for coroutine errors, generator errors, explicit closure, nested calls, and concurrent tasks.

### Changed
- Removed the temporary async and generator rejection introduced in Release 0.2.0.
- `@aae_observability.instrument` now preserves whether wrappers are coroutine, generator, or async-generator functions.
- Refactored span status, hook execution, and call preparation into shared interceptor helpers.
- Disabled OpenTelemetry context-manager auto-status handling so `aae_observability` remains the single owner of exception and status semantics.
- Updated package version from `0.2.0` to `0.2.1`.

### Fixed
- Normal explicit async-generator closure is recorded as successful rather than cancelled.
- Explicit exception descriptions are no longer overwritten by automatic context-manager status handling.

### Security
- Generator spans are detached while execution is yielded back to consumers, preventing accidental context leakage.
- Arguments, yielded values, return values, and exception payloads are not added to span attributes.

## [0.2.0] - 2026-08-25

### Added
- Synchronous OpenTelemetry span lifecycle in `@aae_observability.instrument`.
- Structured interceptor pipeline covering context extraction, span creation, pre-invocation hooks, callable execution, post-invocation hooks, and span closure.
- Adapter selection with ordered matching and generic fallback.
- Stable span names for agent and tool operations.
- GenAI span attributes for operation, agent name, agent identifier, and tool name.
- Additional attributes for framework and Python function identity.
- Pre-invocation and post-invocation span lifecycle events.
- Configurable synchronous pre-invocation and post-invocation hooks.
- Hook-failure isolation that records hook errors without changing application behavior.
- Explicit rejection of async and generator callables until their full-lifecycle support arrives in Release 0.2.1.
- Optional application-supplied OpenTelemetry `TracerProvider`.
- Isolated private tracer provider by default without replacing the application's global provider.
- In-memory exporter tests for successful calls, failures, hooks, adapter selection, and nested spans.

### Changed
- `@aae_observability.instrument` now creates real synchronous spans instead of acting as a transparent placeholder.
- `aae_observability.configure()` now initializes tracing and accepts adapters and interceptor hooks.
- `aae_observability.shutdown()` now flushes and shuts down tracing resources as well as the telemetry sink.
- Updated package version from `0.1.2` to `0.2.0`.

### Security
- Function arguments and return values are not recorded as span attributes.
- Exceptions are recorded for diagnostics while the original exception object is re-raised unchanged.

## [0.1.2] - 2026-08-25

### Added
- Immutable Pydantic configuration models with strict unknown-field rejection.
- Top-level `AaeObservabilityConfig` document combining telemetry and governance settings.
- Validation for service identity, sampling ratio, buffer capacity, batch size, flush interval, governance timeout, Event Hub endpoints, and authentication combinations.
- Secret-safe connection-string handling through `SecretStr`.
- TOML and JSON configuration file loading.
- `aae_observability config validate <path>` command with non-zero failure exit codes.
- `--show-effective` output with connection strings redacted.
- `SECURITY.md`, `CONTRIBUTING.md`, and `CODE_OF_CONDUCT.md`.
- Development dependency lock baseline and Dependabot configuration.
- Project metadata validation and clean-wheel installation checks in CI.
- Configuration, file-loading, CLI validation, and secret-redaction tests.

### Changed
- Replaced the initial configuration dataclasses with validated Pydantic models.
- Added Pydantic as a runtime dependency.
- Extended source-distribution contents to include project health and dependency-management files.
- Updated package version from `0.1.1` to `0.1.2`.

### Security
- Effective configuration output never exposes Event Hub connection strings.
- Production guidance favors managed identity or default Azure credentials over connection strings.

## [0.1.1] - 2026-08-25

### Added
- Runtime-checkable `PolicyEngine`, `TelemetrySink`, and `FrameworkAdapter` protocols.
- Abstract base classes for inheritance-oriented extension implementations.
- Framework-neutral `AgentCall`, `ActionSnapshot`, `Identity`, and `Framework` contracts.
- `AllowAllPolicyEngine` and `DenyAllPolicyEngine` reference policy engines.
- `NullTelemetrySink` reference sink with signal counters and lifecycle tracking.
- `GenericFrameworkAdapter` fallback that normalizes decorated Python callables.
- Optional policy-engine and telemetry-sink injection through `aae_observability.configure()`.
- Telemetry sink flush and shutdown integration through `aae_observability.shutdown()`.
- Contract conformance, normalization, lifecycle, and API-wiring tests.

### Changed
- Extended the top-level public API to export all stable Release 0.1.1 contracts.
- Updated package version from `0.1.0` to `0.1.1`.

## [0.1.0] - 2026-08-25

### Added
- PEP 621 `pyproject.toml` using Hatchling and a `src/` package layout.
- Python 3.10, 3.11, and 3.12 support declaration.
- OpenTelemetry API/SDK, OTLP protobuf common encoder, and Azure Event Hubs runtime dependencies.
- Stable public API placeholders: `instrument`, `configure`, `shutdown`, and `is_configured`.
- Typed `PolicyResult`, `Verdict`, `TelemetryConfig`, and `GovernanceConfig` foundations.
- GenAI-aware OpenTelemetry Resource factory with a bootstrap fallback.
- `aae_observability version` CLI command and `py.typed` marker.
- Pytest suite, Ruff, strict Mypy configuration, pre-commit hooks, and CI matrix.
- Build and Twine validation job for wheel and source distributions.

### Validation
- Public API, decorator transparency, configuration lifecycle, Resource attributes, and CLI covered by automated tests.
