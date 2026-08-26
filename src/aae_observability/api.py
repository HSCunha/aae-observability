"""Stable top-level API and instrumentation entry points."""

from __future__ import annotations

import contextlib
import functools
import inspect
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, TypeVar, cast

from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.sampling import ParentBased, TraceIdRatioBased
from opentelemetry.trace import Tracer

from aae_observability._version import __version__
from aae_observability.adapters import build_adapter_registry
from aae_observability.config import (
    AaeObservabilityConfig,
    GovernanceConfig,
    RuntimeConfigReloader,
    TelemetryConfig,
    build_layered_reloader,
    load_layered_config,
)
from aae_observability.contracts import (
    AllowAllPolicyEngine,
    FrameworkAdapter,
    OperationType,
    PolicyEngine,
    TelemetrySink,
)
from aae_observability.decorator import (
    InterceptorSettings,
    PostInvocationHook,
    PreInvocationHook,
    SensitiveDataRedactor,
    invoke_async,
    invoke_async_generator,
    invoke_generator,
    invoke_sync,
)
from aae_observability.governance.audit import GovernanceAuditSink
from aae_observability.governance.enforcement import GovernanceSettings
from aae_observability.governance.report import CompositeGovernanceAuditSink, GovernanceReport
from aae_observability.governance.telemetry import GovernanceMetrics
from aae_observability.resource import build_resource
from aae_observability.telemetry import (
    BufferedTelemetrySink,
    BufferMetrics,
    OperationMetrics,
    TelemetryBuffer,
)

F = TypeVar("F", bound=Callable[..., Any])


@dataclass(slots=True)
class _RuntimeState:
    telemetry: TelemetryConfig | None = None
    governance: GovernanceConfig | None = None
    resource: Any = None
    policy_engine: PolicyEngine | None = None
    governance_metrics: GovernanceMetrics | None = None
    governance_audit_sink: GovernanceAuditSink | None = None
    governance_report: GovernanceReport | None = None
    telemetry_sink: TelemetrySink | None = None
    tracer_provider: TracerProvider | None = None
    tracer: Tracer | None = None
    meter_provider: MeterProvider | None = None
    metrics: OperationMetrics | None = None
    telemetry_buffer: TelemetryBuffer | None = None
    buffer_metrics: BufferMetrics | None = None
    sensitive_data_redactor: SensitiveDataRedactor | None = None
    adapters: tuple[FrameworkAdapter, ...] = field(default_factory=tuple)
    pre_hooks: tuple[PreInvocationHook, ...] = field(default_factory=tuple)
    post_hooks: tuple[PostInvocationHook, ...] = field(default_factory=tuple)
    config_reloader: RuntimeConfigReloader | None = None
    configured: bool = False


_STATE = _RuntimeState()
_STATE_LOCK = threading.RLock()


def configure(
    telemetry: TelemetryConfig | None = None,
    governance: GovernanceConfig | None = None,
    *,
    config_file: str | None = None,
    environ: dict[str, str] | None = None,
    policy_engine: PolicyEngine | None = None,
    telemetry_sink: TelemetrySink | None = None,
    tracer_provider: TracerProvider | None = None,
    meter_provider: MeterProvider | None = None,
    adapters: tuple[FrameworkAdapter, ...] | None = None,
    pre_hooks: tuple[PreInvocationHook, ...] = (),
    post_hooks: tuple[PostInvocationHook, ...] = (),
    sensitive_data_redactor: SensitiveDataRedactor | None = None,
    governance_audit_sink: GovernanceAuditSink | None = None,
    discover_adapters: bool = True,
    reload_event_sink: Callable[[Any], None] | None = None,
) -> None:
    """Configure settings, contracts, adapters, hooks, and tracing.

    A private tracer provider is used rather than replacing OpenTelemetry's
    process-wide provider. Applications may inject their own provider.
    """
    explicit_telemetry = telemetry
    explicit_governance = governance
    resolved = load_layered_config(
        config_file, telemetry=telemetry, governance=governance, environ=environ
    )
    telemetry = resolved.telemetry
    governance = resolved.governance
    resource = build_resource(
        service_name=telemetry.service_name,
        service_namespace=telemetry.service_namespace,
        environment=telemetry.environment,
    )
    provider = tracer_provider or TracerProvider(
        resource=resource,
        sampler=ParentBased(TraceIdRatioBased(telemetry.sampling_ratio)),
    )
    metric_provider = meter_provider or MeterProvider(resource=resource)

    _STATE.telemetry = telemetry
    _STATE.governance = governance
    _STATE.resource = resource
    _STATE.policy_engine = policy_engine or AllowAllPolicyEngine()
    _STATE.governance_metrics = GovernanceMetrics.create(
        metric_provider.get_meter("aae-observability.governance", __version__)
    )
    _STATE.governance_report = GovernanceReport()
    _STATE.governance_audit_sink = CompositeGovernanceAuditSink(
        *tuple(
            sink for sink in (governance_audit_sink, _STATE.governance_report) if sink is not None
        )
    )
    meter = metric_provider.get_meter("aae-observability", __version__)
    telemetry_buffer = TelemetryBuffer(telemetry.buffer_capacity, telemetry.drop_policy)
    buffer_metrics = BufferMetrics.create(meter)
    _STATE.telemetry_buffer = telemetry_buffer
    _STATE.buffer_metrics = buffer_metrics
    _STATE.telemetry_sink = telemetry_sink or BufferedTelemetrySink(
        telemetry_buffer, buffer_metrics=buffer_metrics
    )
    _STATE.tracer_provider = provider
    _STATE.tracer = provider.get_tracer("aae-observability", __version__)
    _STATE.meter_provider = metric_provider
    _STATE.metrics = OperationMetrics.create(meter)
    _STATE.sensitive_data_redactor = sensitive_data_redactor
    _STATE.adapters = build_adapter_registry(adapters, discover_plugins=discover_adapters)
    _STATE.pre_hooks = pre_hooks
    _STATE.post_hooks = post_hooks
    _STATE.configured = True
    if _STATE.config_reloader is not None:
        _STATE.config_reloader.stop()
        _STATE.config_reloader = None
    if governance.hot_reload_enabled:
        if config_file is None:
            raise ValueError("config_file is required when hot reload is enabled")
        policy_source = governance.policy_source

        def apply_reload(candidate: AaeObservabilityConfig) -> None:
            policy_engine_candidate = _STATE.policy_engine
            if candidate.governance.policy_source:
                from aae_observability.governance import LocalPolicyEngine

                policy_engine_candidate = LocalPolicyEngine.from_file(
                    candidate.governance.policy_source
                )
            with _STATE_LOCK:
                _STATE.telemetry = candidate.telemetry
                _STATE.governance = candidate.governance
                _STATE.policy_engine = policy_engine_candidate

        _STATE.config_reloader = build_layered_reloader(
            config_file,
            apply_reload,
            telemetry=explicit_telemetry,
            governance=explicit_governance,
            environ=environ,
            policy_source=policy_source,
            interval_ms=governance.hot_reload_interval_ms,
            event_sink=reload_event_sink,
        )
        _STATE.config_reloader.start()


def is_configured() -> bool:
    """Return whether the package has been configured."""
    return _STATE.configured


def _interceptor_settings() -> InterceptorSettings:
    """Return configured interceptor settings, applying safe defaults lazily."""
    if not _STATE.configured:
        configure()
    if _STATE.tracer is None:
        raise RuntimeError("aae_observability tracer is unavailable after configuration")
    return InterceptorSettings(
        tracer=_STATE.tracer,
        adapters=_STATE.adapters,
        pre_hooks=_STATE.pre_hooks,
        post_hooks=_STATE.post_hooks,
        metrics=_STATE.metrics,
        capture_sensitive_data=bool(_STATE.telemetry and _STATE.telemetry.capture_sensitive_data),
        sensitive_data_max_length=(
            _STATE.telemetry.sensitive_data_max_length if _STATE.telemetry else 2_048
        ),
        sensitive_data_redactor=_STATE.sensitive_data_redactor,
        governance=(
            GovernanceSettings(
                _STATE.policy_engine,
                _STATE.governance.enabled,
                _STATE.governance.fail_closed,
                _STATE.governance.evaluation_timeout_ms,
                _STATE.governance.audit_enabled,
                _STATE.governance_metrics,
                _STATE.governance_audit_sink,
            )
            if _STATE.policy_engine and _STATE.governance
            else None
        ),
    )


def get_governance_report() -> GovernanceReport:
    """Return the active operational governance report."""
    if not _STATE.configured:
        configure()
    if _STATE.governance_report is None:
        raise RuntimeError("governance report is unavailable")
    return _STATE.governance_report


def get_config_reloader() -> RuntimeConfigReloader | None:
    """Return the active hot-reload controller, when configured."""
    return _STATE.config_reloader


def instrument(
    func: F | None = None,
    *,
    agent_name: str | None = None,
    tool_name: str | None = None,
    operation: OperationType | str | None = None,
) -> F | Callable[[F], F]:
    """Instrument sync, coroutine, and generator agent/tool callables.

    Wrappers preserve metadata, values, exceptions, and complete execution
    lifecycles, including coroutine awaits and generator iteration.
    """

    def decorator(target: F) -> F:
        if getattr(target, "__aae_observability_native_instrumented__", False):
            return target
        if getattr(target, "__aae_observability_instrumented__", False):
            return target

        # Mark the original callable because adapters receive it inside wrappers.
        target.__aae_observability_instrumented__ = True
        target.__aae_observability_agent_name__ = agent_name
        target.__aae_observability_tool_name__ = tool_name
        target.__aae_observability_operation__ = operation

        if inspect.isasyncgenfunction(target):

            @functools.wraps(target)
            async def async_generator_wrapper(*args: Any, **kwargs: Any) -> Any:
                instrumented = invoke_async_generator(target, args, kwargs, _interceptor_settings())
                try:
                    while True:
                        try:
                            item = await instrumented.__anext__()
                        except StopAsyncIteration:
                            break
                        yield item
                except GeneratorExit:
                    await instrumented.aclose()
                    raise

            wrapper: Callable[..., Any] = async_generator_wrapper
        elif inspect.iscoroutinefunction(target):

            @functools.wraps(target)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                return await invoke_async(target, args, kwargs, _interceptor_settings())

            wrapper = async_wrapper
        elif inspect.isgeneratorfunction(target):

            @functools.wraps(target)
            def generator_wrapper(*args: Any, **kwargs: Any) -> Any:
                return (yield from invoke_generator(target, args, kwargs, _interceptor_settings()))

            wrapper = generator_wrapper
        else:

            @functools.wraps(target)
            def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
                return invoke_sync(target, args, kwargs, _interceptor_settings())

            wrapper = sync_wrapper

        wrapper.__aae_observability_instrumented__ = True
        wrapper.__aae_observability_agent_name__ = agent_name
        wrapper.__aae_observability_tool_name__ = tool_name
        wrapper.__aae_observability_operation__ = operation
        return cast(F, wrapper)

    return decorator(func) if func is not None else decorator


def shutdown(timeout_ms: int = 30_000) -> None:
    """Flush and stop configured telemetry and tracing resources."""
    reloader = _STATE.config_reloader
    if reloader is not None:
        reloader.stop(timeout_ms)
        _STATE.config_reloader = None
    audit_sink = _STATE.governance_audit_sink
    if audit_sink is not None:
        flush = getattr(audit_sink, "flush", None)
        close = getattr(audit_sink, "close", None)
        if callable(flush):
            with contextlib.suppress(Exception):
                flush(timeout_ms)
        if callable(close):
            with contextlib.suppress(Exception):
                close(timeout_ms)
    if _STATE.telemetry_sink is not None:
        _STATE.telemetry_sink.force_flush(timeout_ms)
        _STATE.telemetry_sink.shutdown(timeout_ms)
    if _STATE.meter_provider is not None:
        _STATE.meter_provider.force_flush(timeout_millis=timeout_ms)
        _STATE.meter_provider.shutdown(timeout_millis=timeout_ms)
    if _STATE.tracer_provider is not None:
        _STATE.tracer_provider.force_flush(timeout_millis=timeout_ms)
        _STATE.tracer_provider.shutdown()
    _STATE.configured = False
    _STATE.tracer = None
    _STATE.tracer_provider = None
    _STATE.meter_provider = None
    _STATE.metrics = None
    _STATE.telemetry_buffer = None
    _STATE.buffer_metrics = None
    _STATE.governance_audit_sink = None
    _STATE.governance_report = None
