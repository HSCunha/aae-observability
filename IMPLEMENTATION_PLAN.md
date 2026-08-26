# `aae_observability` — Agent Governance & Observability
## Reusable Python Package · Phased Implementation Plan

**Goal:** A pip-installable Python package exposing a **function decorator** that can wrap agent functions across frameworks (Microsoft Agent Framework, LangChain, CrewAI/AutoGen multi-agent), that:

1. **Intercepts** every agent/tool call to **enforce governance policy in real time**, and
2. Generates **OpenTelemetry-compliant** telemetry (traces, metrics, logs) that is **buffered, batched, serialized (OTLP) and shipped directly to Azure Event Hub — with no external OpenTelemetry Collector**.

**Design pivot (collector-less):** Because there is no Collector to provide buffering, batching, retry and OTLP encoding, those responsibilities are **built into the package** (Phase 3). The decorator conforms to the **OpenTelemetry GenAI Semantic Conventions** already used by Microsoft Agent Framework, and the governance interceptor implements the **Agent Governance Toolkit (AGT) / ACS** contract so policies are portable.

---

## Conventions used in this plan

- **Package name (PyPI):** `aae_observability` · **Import root:** `aae_observability`
- **Primary decorator:** `@aae_observability.instrument(...)`
- **Versioning:** Semantic Versioning. Each phase ships one or more **preliminary releases** (`0.x.y`). GA is `1.0.0`.
- **Release discipline:** After completing a release's steps, append an entry to `RELEASE.md` (Keep-a-Changelog style, newest first), tag the commit, and publish to the internal index.
- **Definition of Done per release:** code + unit tests (≥85% on new code) + docstrings + `RELEASE.md` entry + green CI.

### Target package layout
```
aae_observability/
├── __init__.py            # public API: instrument, configure, PolicyResult
├── config/                # Phase 1 & 5: settings, schema, loaders, hot-reload
├── decorator/             # Phase 2: interceptor, span lifecycle, framework adapters
├── telemetry/             # Phase 3: buffer, batcher, serializer, eventhub_exporter
├── governance/            # Phase 4: policy engine, ACS adapter, enforcement actions
├── adapters/              # framework shims (maf, langchain, multiagent)
└── _internal/             # utils, retry, backoff, clock, context propagation
tests/                     # Phase 6: mocked agents, unit + integration
```

---

# Phase 1 — Project Design & Foundations
*Objective: bootstrap the package, vendor/pin the OpenTelemetry SDK, and define the interfaces for the Microsoft Agent Governance Toolkit (AGT/ACS) and framework adapters.*

### Release 0.1.0 — Project scaffold & bundled OTel SDK
1. Initialize repo with `pyproject.toml` (PEP 621), `src/` layout, `ruff` + `mypy` + `pytest`, and pre-commit hooks.
2. **Pin and bundle the OpenTelemetry SDK** as hard dependencies so the package is self-contained (no runtime assumption of a Collector): `opentelemetry-api`, `opentelemetry-sdk`, `opentelemetry-exporter-otlp-proto-common` (for OTLP encoding), and `azure-eventhub`.
3. Create the empty public surface in `aae_observability/__init__.py`: `instrument`, `configure`, `shutdown`, plus typed placeholders `PolicyResult`, `TelemetryConfig`, `GovernanceConfig`.
4. Add a `Resource` factory that stamps `service.name`, `service.namespace`, `deployment.environment`, and agent-level attributes per **OTel GenAI semantic conventions** so downstream tools recognize the signals.
5. Wire CI (build, lint, type-check, unit test matrix for Python 3.10–3.12).
6. **Update `RELEASE.md`** → `0.1.0`.

### Release 0.1.1 — Governance & framework interface contracts
1. Define `PolicyEngine` protocol (`evaluate(action_snapshot) -> Verdict`) mirroring the **ACS decision model**: a full action snapshot in, a fail-closed verdict out (`allow` / `deny` / `require_approval` / `redact` / `kill`).
2. Define `TelemetrySink` protocol (`emit(spans, metrics, logs)`) so the engine (Phase 3) is swappable.
3. Define `FrameworkAdapter` protocol: `extract_context(fn, args, kwargs)` → normalized `AgentCall` (agent name, tool name, inputs, run/trace IDs) for MAF, LangChain and multi-agent.
4. Publish these as stable ABCs/Protocols with type stubs; document the extension points.
5. **Update `RELEASE.md`** → `0.1.1`.

### Release 0.1.2 — Configuration schema & CI hardening
1. Define the config **schema** (pydantic) covering: Event Hub endpoint/namespace/name, batch size, flush interval, buffer capacity, drop policy, policy source, auth mode, sampling.
2. Provide schema validation + a `aae_observability config validate` CLI stub.
3. Add coverage gate, SBOM generation, and dependency pinning/lockfile.
4. **Update `RELEASE.md`** → `0.1.2`.

---

# Phase 2 — Core Decorator
*Objective: build `@aae_observability.instrument`, with async handling and full span lifecycle management, plus framework adapters.*

### Release 0.2.0 — Base decorator (sync) + span creation
1. Implement `@aae_observability.instrument` for **synchronous** functions: open a span on entry, set GenAI attributes (`gen_ai.operation.name`, `gen_ai.agent.name`, `gen_ai.tool.name`), close on exit.
2. Record exceptions on the span (`record_exception`, status = ERROR) without swallowing them.
3. Establish the **interceptor pipeline** skeleton: `pre-hook → (policy placeholder) → invoke → post-hook`.
4. **Update `RELEASE.md`** → `0.2.0`.

### Release 0.2.1 — Asynchronous handling
1. Detect `async def`, coroutines, async generators and sync generators; wrap each correctly so spans span the *entire* awaited/iterated lifetime.
2. Ensure **OTel context propagation** across `await` boundaries and thread pools (`contextvars`).
3. Add concurrency tests (many simultaneous coroutines → correct parent/child span trees).
4. **Update `RELEASE.md`** → `0.2.1`.

### Release 0.2.2 — Span lifecycle & semantic conventions
1. Formalize span kinds and parent/child nesting: `agent.run` → `llm.chat` / `tool.call` / `retrieval.query` per the recommended agent trace structure.
2. Capture **metrics** (token counts, operation duration, invocation count) using the `gen_ai`/`aae_observability` metric namespaces.
3. Add opt-in **sensitive-data** capture (prompts/results) — **off by default**, mirroring MAF's `enable_sensitive_data` guidance.
4. **Update `RELEASE.md`** → `0.2.2`.

### Release 0.2.3 — Framework adapters (MAF, LangChain, multi-agent)
1. Implement `MAFAdapter`: align with MAF's existing OTel emission to avoid duplicate spans (respect its `sourceName`).
2. Implement `LangChainAdapter`: map chains/tools/agents to normalized `AgentCall`.
3. Implement `MultiAgentAdapter`: propagate a shared correlation/trace ID across agent hand-offs so a multi-agent run is one trace.
4. Auto-select adapter via lightweight signature/heuristic detection; allow explicit override.
5. **Update `RELEASE.md`** → `0.2.3`.

---

# Phase 3 — Robust Telemetry Engine (collector-less)
*Objective: buffer, batch, serialize, and ship telemetry directly to Event Hub — replacing everything a Collector would have done.*

### Release 0.3.0 — In-memory buffering
1. Implement a bounded, thread-safe **ring buffer** for spans/metrics/logs with a configurable capacity and back-pressure/drop policy (drop-oldest vs. drop-new) plus a dropped-record counter (self-telemetry).
2. Producer side is non-blocking so instrumentation never stalls the agent.
3. **Update `RELEASE.md`** → `0.3.0`.

### Release 0.3.1 — Batching processor
1. Implement a background **batch processor** flushing on **size** OR **time** (`max_batch_size`, `flush_interval_ms`), mirroring the Collector's `batch` processor semantics.
2. Add graceful `shutdown()`/`force_flush()` (atexit + signal hooks) so no data is lost on exit.
3. **Update `RELEASE.md`** → `0.3.1`.

### Release 0.3.2 — OTLP serialization
1. Serialize batches to **OTLP protobuf** using `opentelemetry-exporter-otlp-proto-common` encoders so the payload is standard OTLP that any backend can decode.
2. Support optional gzip compression and a max-payload guard that splits oversized batches.
3. Add round-trip encode/decode unit tests.
4. **Update `RELEASE.md`** → `0.3.2`.

### Release 0.3.3 — Direct Event Hub exporter (no Collector)
1. Implement `EventHubExporter` using `azure-eventhub` `EventHubProducerClient`: wrap each OTLP payload as an `EventData`, batch via `create_batch()`, and `send_batch()`.
2. Add **retry with exponential backoff + jitter**, partition-key strategy (e.g., by `trace_id` for ordering), and connection reuse.
3. Support both connection-string and (Phase 5) credential auth; expose delivery metrics (success/fail/retry).
4. Provide a local `ConsoleExporter` for dev, matching the Aspire/console pattern.
5. **Update `RELEASE.md`** → `0.3.3`.

---

# Phase 4 — Governance Policy Enforcement
*Objective: enforce policy in real time inside the interceptor, before the wrapped call executes.*

### Release 0.4.0 — Policy engine interface & loader
1. Implement `PolicyEngine` per the 0.1.1 contract with a **YAML policy loader** compatible with the AGT/ACS policy shape (`apiVersion`, `default_action`, `rules[]` with `condition`/`action`).
2. Support an **ACS adapter** so an existing AGT deployment can be the decision authority (delegate `evaluate`).
3. Cache compiled policies; expose `aae_observability policy validate`.
4. **Update `RELEASE.md`** → `0.4.0`.

### Release 0.4.1 — Real-time validation in the interceptor
1. Insert policy evaluation into the pipeline **pre-invocation**: build the action snapshot (agent, tool, args, identity, context) and call `evaluate()` **before** the wrapped function runs.
2. Enforce **fail-closed** semantics (deny on engine error/timeout) with a strict latency budget target.
3. Emit a governance decision as a span event + audit log record for every call (tamper-evident audit trail).
4. **Update `RELEASE.md`** → `0.4.1`.

### Release 0.4.2 — Enforcement actions (incl. kill switch)
1. Implement verdict handlers: `allow` (proceed), `deny` (raise `GovernanceDenied`), `redact` (mask inputs/outputs), `require_approval` (block pending human approval), and `kill` (soft/hard kill of the agent action).
2. Correlate each enforcement action with its telemetry span and audit entry.
3. Map coverage to the **OWASP Agentic Top 10** risk categories and document which rule types address each.
4. **Update `RELEASE.md`** → `0.4.2`.

---

# Phase 5 — Configuration Injection
*Objective: dynamic endpoints, secrets, and runtime settings without code changes.*

### Release 0.5.0 — Layered config loader & dynamic endpoints
1. Implement precedence: **explicit args → env vars (`OTEL_EXPORTER_OTLP_*`, `AAE_OBSERVABILITY_*`) → config file → defaults**, so it drops into MAF's env-driven setup.
2. Allow the Event Hub endpoint, batch/flush settings, and policy source to be injected at `configure()` time or via env.
3. **Update `RELEASE.md`** → `0.5.0`.

### Release 0.5.1 — Secret & credential injection
1. Support `DefaultAzureCredential` / `ManagedIdentityCredential` for Event Hub auth (recommend Managed Identity in prod per MAF guidance), plus connection-string fallback for dev.
2. Integrate optional Key Vault resolution for secrets; never log secret material.
3. **Update `RELEASE.md`** → `0.5.1`.

### Release 0.5.2 — Hot reload / runtime reconfiguration
1. Watch policy + config sources; apply changes (sampling, flush interval, policy rules) **without restart**, atomically and thread-safely.
2. Emit a self-telemetry event on each reload for auditability.
3. **Update `RELEASE.md`** → `0.5.2`.

---

# Phase 6 — Testing & Deployment
*Objective: verify data integrity against mocked agents and ship it.*

### Release 0.6.0 — Mocked agents & unit tests (data integrity)
1. Build mock MAF/LangChain/multi-agent functions and a **fake Event Hub sink** capturing sent `EventData`.
2. Assert **data integrity**: every wrapped call → correct spans/metrics, attributes conform to GenAI conventions, OTLP decodes cleanly, no records dropped under normal load.
3. Add property/fuzz tests for buffer/batcher edge cases (overflow, flush-on-exit, concurrency).
4. **Update `RELEASE.md`** → `0.6.0`.

### Release 0.6.1 — Integration tests & round-trip verification
1. End-to-end: instrument mock agents → engine → **real Event Hub** (test namespace) → consumer decodes OTLP → verify counts/attributes match emitted.
2. Test governance paths (allow/deny/redact/kill) end-to-end incl. fail-closed and latency budget.
3. Chaos tests: transient Event Hub failures → retry/backoff → no data loss.
4. **Update `RELEASE.md`** → `0.6.1`.

### Release 0.6.2 — Packaging, docs & deployment
1. Build wheels/sdist, generate docs (quickstart, policy authoring, config reference), publish to the internal package index.
2. Provide a 2-line integration example (`@aae_observability.instrument` + `aae_observability.configure(...)`) and a deployment checklist (identity, endpoint, policy source).
3. Ship a versioned migration/compat note vs. MAF's native OTel setup.
4. **Update `RELEASE.md`** → `0.6.2`.

### Release 1.0.0 — General Availability
1. Freeze the public API, finalize semantic-versioning guarantees and support matrix.
2. Complete security review (SBOM, dependency audit), performance benchmarks (throughput, added latency), and the OWASP Agentic Top 10 coverage attestation.
3. Tag `1.0.0`, publish release notes.
4. **Update `RELEASE.md`** → `1.0.0`.

---

## Traceability: your brief → this plan

| Your requirement | Where it's delivered |
|---|---|
| Decorator usable across MAF / LangChain / multi-agent | Phase 2 (0.2.0–0.2.3) |
| Real-time policy enforcement in the interceptor | Phase 4 (0.4.1–0.4.2) |
| OpenTelemetry-compliant telemetry | Phase 1 (0.1.0) + Phase 2 (0.2.2) |
| Internal buffering, batching, serialization | Phase 3 (0.3.0–0.3.2) |
| Direct-to-Event-Hub, no external collector | Phase 3 (0.3.3) |
| Dynamic endpoints & settings injection | Phase 5 (0.5.0–0.5.2) |
| Testing vs. mocked agents + data integrity + deployment | Phase 6 (0.6.0–1.0.0) |
