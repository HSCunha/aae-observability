"""Sync, coroutine, and generator interception with OpenTelemetry spans."""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncGenerator, Callable, Generator, Sequence
from dataclasses import dataclass
from typing import Any

from opentelemetry import trace
from opentelemetry.trace import Span, Status, StatusCode, Tracer

from aae_observability import semconv
from aae_observability.contracts import (
    AgentCall,
    FrameworkAdapter,
    GenericFrameworkAdapter,
    OperationType,
)
from aae_observability.governance.enforcement import (
    GovernanceSettings,
    evaluate_async,
    evaluate_sync,
)
from aae_observability.telemetry import OperationMetrics

PreInvocationHook = Callable[[AgentCall, Span], None]
PostInvocationHook = Callable[[AgentCall, Span, Any | None, BaseException | None], None]
SensitiveDataRedactor = Callable[[str], str]


@dataclass(frozen=True, slots=True)
class InterceptorSettings:
    """Immutable settings used by all interceptor variants."""

    tracer: Tracer
    adapters: Sequence[FrameworkAdapter]
    pre_hooks: Sequence[PreInvocationHook] = ()
    post_hooks: Sequence[PostInvocationHook] = ()
    metrics: OperationMetrics | None = None
    capture_sensitive_data: bool = False
    sensitive_data_max_length: int = 2_048
    sensitive_data_redactor: SensitiveDataRedactor | None = None
    governance: GovernanceSettings | None = None


def select_adapter(
    func: Callable[..., Any], adapters: Sequence[FrameworkAdapter]
) -> FrameworkAdapter:
    """Return the first matching adapter, falling back to the generic adapter."""
    for adapter in adapters:
        if adapter.matches(func):
            return adapter
    return GenericFrameworkAdapter()


def _operation_name(call: AgentCall) -> str:
    operation = call.operation
    if isinstance(operation, OperationType):
        return operation.value
    if operation:
        return operation
    return OperationType.TOOL_CALL.value if call.is_tool_call else OperationType.AGENT_RUN.value


def _metric_attributes(call: AgentCall) -> dict[str, str]:
    """Return low-cardinality attributes only; never include payload data."""
    return {
        "gen_ai.operation.name": _operation_name(call),
        "aae.observability.framework": call.framework.value,
        "aae.observability.outcome": "unknown",
    }


def _serialize_sensitive(value: Any, settings: InterceptorSettings) -> str:
    try:
        serialized = json.dumps(value, default=repr, ensure_ascii=False)
    except (TypeError, ValueError):
        serialized = repr(value)
    if settings.sensitive_data_redactor is not None:
        serialized = settings.sensitive_data_redactor(serialized)
    return serialized[: settings.sensitive_data_max_length]


def _capture_inputs(span: Span, call: AgentCall, settings: InterceptorSettings) -> None:
    if not settings.capture_sensitive_data:
        return
    span.add_event(
        "aae.observability.sensitive.input",
        {
            "aae.observability.input": _serialize_sensitive(
                {"args": call.inputs, "kwargs": dict(call.kwargs)}, settings
            )
        },
    )


def _capture_output(span: Span, result: Any, settings: InterceptorSettings) -> None:
    if settings.capture_sensitive_data:
        span.add_event(
            "aae.observability.sensitive.output",
            {"aae.observability.output": _serialize_sensitive(result, settings)},
        )


def _start_metrics(call: AgentCall, settings: InterceptorSettings) -> tuple[float, dict[str, str]]:
    attrs = _metric_attributes(call)
    if settings.metrics is not None:
        settings.metrics.invocations.add(1, attrs)
        settings.metrics.active.add(1, attrs)
        input_tokens = call.attributes.get("gen_ai.usage.input_tokens")
        output_tokens = call.attributes.get("gen_ai.usage.output_tokens")
        if isinstance(input_tokens, int) and input_tokens >= 0:
            settings.metrics.input_tokens.add(input_tokens, attrs)
        if isinstance(output_tokens, int) and output_tokens >= 0:
            settings.metrics.output_tokens.add(output_tokens, attrs)
    return time.monotonic(), attrs


def _finish_metrics(
    started: float,
    attrs: dict[str, str],
    error: BaseException | None,
    settings: InterceptorSettings,
) -> None:
    if settings.metrics is None:
        return
    final_attrs = dict(attrs)
    final_attrs["aae.observability.outcome"] = (
        "cancelled"
        if isinstance(error, asyncio.CancelledError)
        else ("error" if error else "success")
    )
    settings.metrics.duration.record(time.monotonic() - started, final_attrs)
    settings.metrics.active.add(-1, attrs)
    if error is not None:
        settings.metrics.errors.add(1, final_attrs)
    if isinstance(error, asyncio.CancelledError):
        settings.metrics.cancellations.add(1, final_attrs)


def span_name(call: AgentCall) -> str:
    """Build a stable, low-cardinality span name for an invocation."""
    operation = _operation_name(call)
    target = call.tool_name or call.agent_name or call.function_name or "anonymous"
    return f"{operation} {target}"


def apply_call_attributes(span: Span, call: AgentCall) -> None:
    """Apply normalized GenAI and aae_observability attributes to a span."""
    operation = _operation_name(call)
    span.set_attribute(semconv.GEN_AI_OPERATION_NAME, operation)
    span.set_attribute("aae.observability.framework", call.framework.value)
    if call.agent_name:
        span.set_attribute(semconv.GEN_AI_AGENT_NAME, call.agent_name)
    if call.agent_id:
        span.set_attribute(semconv.GEN_AI_AGENT_ID, call.agent_id)
    if call.tool_name:
        span.set_attribute(semconv.GEN_AI_TOOL_NAME, call.tool_name)
    if call.function_name:
        span.set_attribute("code.function.name", call.function_name)
    if call.run_id:
        span.set_attribute("aae.observability.run.id", call.run_id)
    for key, value in call.attributes.items():
        if isinstance(value, (bool, str, int, float)):
            span.set_attribute(key, value)


def _record_hook_error(span: Span, phase: str, error: Exception) -> None:
    span.add_event(
        "aae.observability.hook.error",
        {"aae.observability.hook.phase": phase, "exception.type": type(error).__name__},
    )


def _run_pre_hooks(call: AgentCall, span: Span, settings: InterceptorSettings) -> None:
    span.add_event("aae.observability.interceptor.pre_invocation")
    for hook in settings.pre_hooks:
        try:
            hook(call, span)
        except Exception as hook_error:
            _record_hook_error(span, "pre_invocation", hook_error)


def _run_post_hooks(
    call: AgentCall,
    span: Span,
    result: Any | None,
    error: BaseException | None,
    settings: InterceptorSettings,
) -> None:
    for hook in settings.post_hooks:
        try:
            hook(call, span, result, error)
        except Exception as hook_error:
            _record_hook_error(span, "post_invocation", hook_error)
    span.add_event("aae.observability.interceptor.post_invocation")


def _record_success(span: Span) -> None:
    span.set_status(Status(StatusCode.OK))


def _record_failure(span: Span, error: BaseException) -> None:
    span.record_exception(error)
    if isinstance(error, asyncio.CancelledError):
        span.set_attribute("aae.observability.cancelled", True)
    span.set_status(Status(StatusCode.ERROR, str(error) or type(error).__name__))


def _prepare_call(
    func: Callable[..., Any],
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    settings: InterceptorSettings,
) -> AgentCall:
    adapter = select_adapter(func, settings.adapters)
    return adapter.extract_context(func, args, kwargs)


def _start_span(call: AgentCall, settings: InterceptorSettings) -> Span:
    span = settings.tracer.start_span(span_name(call), kind=trace.SpanKind.INTERNAL)
    apply_call_attributes(span, call)
    _capture_inputs(span, call, settings)
    return span


def invoke_sync(
    func: Callable[..., Any],
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    settings: InterceptorSettings,
) -> Any:
    """Invoke a synchronous callable inside the interceptor pipeline."""
    call = _prepare_call(func, args, kwargs, settings)
    if settings.governance is not None:
        evaluate_sync(call, settings.governance)
    span = _start_span(call, settings)
    metric_started, metric_attrs = _start_metrics(call, settings)
    result: Any | None = None
    error: BaseException | None = None
    try:
        with trace.use_span(
            span, end_on_exit=False, record_exception=False, set_status_on_exception=False
        ):
            _run_pre_hooks(call, span, settings)
            try:
                result = func(*args, **kwargs)
                _capture_output(span, result, settings)
                _record_success(span)
                return result
            except BaseException as exc:
                error = exc
                _record_failure(span, exc)
                raise
            finally:
                _run_post_hooks(call, span, result, error, settings)
    finally:
        _finish_metrics(metric_started, metric_attrs, error, settings)
        span.end()


async def invoke_async(
    func: Callable[..., Any],
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    settings: InterceptorSettings,
) -> Any:
    """Await a coroutine function while keeping its span current."""
    call = _prepare_call(func, args, kwargs, settings)
    if settings.governance is not None:
        await evaluate_async(call, settings.governance)
    span = _start_span(call, settings)
    metric_started, metric_attrs = _start_metrics(call, settings)
    result: Any | None = None
    error: BaseException | None = None
    try:
        with trace.use_span(
            span, end_on_exit=False, record_exception=False, set_status_on_exception=False
        ):
            _run_pre_hooks(call, span, settings)
            try:
                result = await func(*args, **kwargs)
                _capture_output(span, result, settings)
                _record_success(span)
                return result
            except BaseException as exc:
                error = exc
                _record_failure(span, exc)
                raise
            finally:
                _run_post_hooks(call, span, result, error, settings)
    finally:
        _finish_metrics(metric_started, metric_attrs, error, settings)
        span.end()


def invoke_generator(
    func: Callable[..., Any],
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    settings: InterceptorSettings,
) -> Generator[Any, Any, Any]:
    """Instrument a synchronous generator for its complete iteration lifecycle."""
    call = _prepare_call(func, args, kwargs, settings)
    if settings.governance is not None:
        evaluate_sync(call, settings.governance)
    span = _start_span(call, settings)
    metric_started, metric_attrs = _start_metrics(call, settings)
    generator = func(*args, **kwargs)
    result: Any | None = None
    error: BaseException | None = None
    started = False
    send_value: Any = None
    thrown: BaseException | None = None
    try:
        with trace.use_span(
            span, end_on_exit=False, record_exception=False, set_status_on_exception=False
        ):
            _run_pre_hooks(call, span, settings)
        while True:
            try:
                with trace.use_span(
                    span, end_on_exit=False, record_exception=False, set_status_on_exception=False
                ):
                    if thrown is not None:
                        current = thrown
                        thrown = None
                        yielded = generator.throw(current)
                    elif not started:
                        started = True
                        yielded = next(generator)
                    else:
                        yielded = generator.send(send_value)
                        send_value = None
            except StopIteration as stop:
                result = stop.value
                _capture_output(span, result, settings)
                _record_success(span)
                return result

            try:
                send_value = yield yielded
            except GeneratorExit:
                with trace.use_span(
                    span, end_on_exit=False, record_exception=False, set_status_on_exception=False
                ):
                    generator.close()
                _record_success(span)
                raise
            except BaseException as exc:
                thrown = exc
    except GeneratorExit:
        raise
    except BaseException as exc:
        error = exc
        _record_failure(span, exc)
        raise
    finally:
        with trace.use_span(
            span, end_on_exit=False, record_exception=False, set_status_on_exception=False
        ):
            _run_post_hooks(call, span, result, error, settings)
        _finish_metrics(metric_started, metric_attrs, error, settings)
        span.end()


async def invoke_async_generator(
    func: Callable[..., Any],
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    settings: InterceptorSettings,
) -> AsyncGenerator[Any, Any]:
    """Instrument an async generator for its complete iteration lifecycle."""
    call = _prepare_call(func, args, kwargs, settings)
    if settings.governance is not None:
        await evaluate_async(call, settings.governance)
    span = _start_span(call, settings)
    metric_started, metric_attrs = _start_metrics(call, settings)
    generator = func(*args, **kwargs)
    error: BaseException | None = None
    started = False
    send_value: Any = None
    thrown: BaseException | None = None
    try:
        with trace.use_span(
            span, end_on_exit=False, record_exception=False, set_status_on_exception=False
        ):
            _run_pre_hooks(call, span, settings)
        while True:
            try:
                with trace.use_span(
                    span, end_on_exit=False, record_exception=False, set_status_on_exception=False
                ):
                    if thrown is not None:
                        current = thrown
                        thrown = None
                        item = await generator.athrow(current)
                    elif not started:
                        started = True
                        item = await generator.__anext__()
                    else:
                        item = await generator.asend(send_value)
                        send_value = None
            except StopAsyncIteration:
                _record_success(span)
                break

            try:
                send_value = yield item
            except GeneratorExit:
                with trace.use_span(
                    span, end_on_exit=False, record_exception=False, set_status_on_exception=False
                ):
                    await generator.aclose()
                _record_success(span)
                raise
            except BaseException as exc:
                thrown = exc
    except GeneratorExit:
        raise
    except BaseException as exc:
        error = exc
        _record_failure(span, exc)
        raise
    finally:
        with trace.use_span(
            span, end_on_exit=False, record_exception=False, set_status_on_exception=False
        ):
            _run_post_hooks(call, span, None, error, settings)
        _finish_metrics(metric_started, metric_attrs, error, settings)
        span.end()
