"""Tests for Release 0.2.1 coroutine and generator lifecycle instrumentation."""

from __future__ import annotations

import asyncio
import inspect
from typing import Any

import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import StatusCode

import aae_observability


def tracing_provider() -> tuple[TracerProvider, InMemorySpanExporter]:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    return provider, exporter


def test_coroutine_span_covers_complete_await_lifecycle() -> None:
    provider, exporter = tracing_provider()
    aae_observability.configure(tracer_provider=provider)
    observed: list[bool] = []

    @aae_observability.instrument(agent_name="async-planner")
    async def run() -> str:
        observed.append(trace.get_current_span().is_recording())
        await asyncio.sleep(0)
        observed.append(trace.get_current_span().is_recording())
        return "done"

    assert inspect.iscoroutinefunction(run)
    assert asyncio.run(run()) == "done"
    assert observed == [True, True]
    span = exporter.get_finished_spans()[0]
    assert span.name == "agent.run async-planner"
    assert span.status.status_code is StatusCode.OK


def test_concurrent_coroutines_keep_isolated_contexts() -> None:
    provider, exporter = tracing_provider()
    aae_observability.configure(tracer_provider=provider)

    @aae_observability.instrument(agent_name="worker")
    async def worker(value: int) -> tuple[int, int]:
        before = trace.get_current_span().get_span_context().span_id
        await asyncio.sleep(0)
        after = trace.get_current_span().get_span_context().span_id
        return before, after

    async def execute() -> list[tuple[int, int]]:
        return await asyncio.gather(*(worker(value) for value in range(5)))

    contexts = asyncio.run(execute())
    assert all(before == after for before, after in contexts)
    assert len({before for before, _ in contexts}) == 5
    spans = exporter.get_finished_spans()
    assert len(spans) == 5
    assert len({span.context.trace_id for span in spans}) == 5


def test_nested_async_calls_propagate_parent_context() -> None:
    provider, exporter = tracing_provider()
    aae_observability.configure(tracer_provider=provider)

    @aae_observability.instrument(agent_name="child")
    async def child() -> str:
        await asyncio.sleep(0)
        return "child"

    @aae_observability.instrument(agent_name="parent")
    async def parent() -> str:
        return await child()

    assert asyncio.run(parent()) == "child"
    spans = {span.name: span for span in exporter.get_finished_spans()}
    assert spans["agent.run child"].parent.span_id == spans["agent.run parent"].context.span_id
    assert spans["agent.run child"].context.trace_id == spans["agent.run parent"].context.trace_id


def test_coroutine_cancellation_is_recorded_and_reraised() -> None:
    provider, exporter = tracing_provider()
    aae_observability.configure(tracer_provider=provider)

    @aae_observability.instrument(agent_name="cancelled-worker")
    async def wait_forever() -> None:
        await asyncio.Event().wait()

    async def execute() -> None:
        task = asyncio.create_task(wait_forever())
        await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(execute())
    span = exporter.get_finished_spans()[0]
    assert span.status.status_code is StatusCode.ERROR
    assert span.attributes["aae.observability.cancelled"] is True
    assert any(event.name == "exception" for event in span.events)


def test_coroutine_exception_is_recorded_and_original_is_reraised() -> None:
    provider, exporter = tracing_provider()
    aae_observability.configure(tracer_provider=provider)
    expected = ValueError("async failure")

    @aae_observability.instrument(agent_name="failing-worker")
    async def fail() -> None:
        await asyncio.sleep(0)
        raise expected

    with pytest.raises(ValueError) as caught:
        asyncio.run(fail())
    assert caught.value is expected
    assert exporter.get_finished_spans()[0].status.status_code is StatusCode.ERROR


def test_sync_generator_span_ends_only_after_iteration_completion() -> None:
    provider, exporter = tracing_provider()
    aae_observability.configure(tracer_provider=provider)

    @aae_observability.instrument(agent_name="producer", tool_name="stream")
    def stream() -> Any:
        yield 1
        yield 2
        return "complete"

    generator = stream()
    assert inspect.isgenerator(generator)
    assert exporter.get_finished_spans() == ()
    assert next(generator) == 1
    assert exporter.get_finished_spans() == ()
    assert next(generator) == 2
    with pytest.raises(StopIteration) as stopped:
        next(generator)
    assert stopped.value.value == "complete"
    span = exporter.get_finished_spans()[0]
    assert span.status.status_code is StatusCode.OK


def test_sync_generator_send_close_and_exception_lifecycle() -> None:
    provider, exporter = tracing_provider()
    aae_observability.configure(tracer_provider=provider)

    @aae_observability.instrument(agent_name="producer")
    def echo() -> Any:
        value = yield "ready"
        yield value

    generator = echo()
    assert next(generator) == "ready"
    assert generator.send("sent") == "sent"
    generator.close()
    assert len(exporter.get_finished_spans()) == 1
    assert exporter.get_finished_spans()[0].status.status_code is StatusCode.OK

    @aae_observability.instrument(agent_name="failing-producer")
    def fail_stream() -> Any:
        yield "first"
        raise RuntimeError("stream failure")

    failing = fail_stream()
    assert next(failing) == "first"
    with pytest.raises(RuntimeError, match="stream failure"):
        next(failing)
    failed_span = exporter.get_finished_spans()[-1]
    assert failed_span.status.status_code is StatusCode.ERROR


def test_async_generator_span_covers_iteration_and_close() -> None:
    provider, exporter = tracing_provider()
    aae_observability.configure(tracer_provider=provider)

    @aae_observability.instrument(agent_name="async-producer", tool_name="stream")
    async def stream() -> Any:
        yield 1
        await asyncio.sleep(0)
        yield 2

    async def consume_all() -> list[int]:
        values: list[int] = []
        async for item in stream():
            values.append(item)
            assert exporter.get_finished_spans() == ()
        return values

    assert inspect.isasyncgenfunction(stream)
    assert asyncio.run(consume_all()) == [1, 2]
    span = exporter.get_finished_spans()[0]
    assert span.status.status_code is StatusCode.OK

    provider2, exporter2 = tracing_provider()
    aae_observability.configure(tracer_provider=provider2)

    @aae_observability.instrument(agent_name="closable-producer")
    async def closable() -> Any:
        yield "first"
        yield "second"

    async def consume_one() -> None:
        generator = closable()
        assert await generator.__anext__() == "first"
        await generator.aclose()

    asyncio.run(consume_one())
    assert len(exporter2.get_finished_spans()) == 1
    assert exporter2.get_finished_spans()[0].status.status_code is StatusCode.OK


def test_generator_does_not_leak_current_span_between_yields() -> None:
    provider, exporter = tracing_provider()
    aae_observability.configure(tracer_provider=provider)

    @aae_observability.instrument(agent_name="isolated-producer")
    def produce() -> Any:
        assert trace.get_current_span().is_recording()
        yield "value"
        assert trace.get_current_span().is_recording()

    generator = produce()
    assert next(generator) == "value"
    assert trace.get_current_span().is_recording() is False
    with pytest.raises(StopIteration):
        next(generator)
    assert len(exporter.get_finished_spans()) == 1


def test_async_generator_exception_is_recorded_and_reraised() -> None:
    provider, exporter = tracing_provider()
    aae_observability.configure(tracer_provider=provider)
    expected = LookupError("async stream failure")

    @aae_observability.instrument(agent_name="failing-async-producer")
    async def fail_stream() -> Any:
        yield "first"
        raise expected

    async def consume() -> None:
        generator = fail_stream()
        assert await generator.__anext__() == "first"
        with pytest.raises(LookupError) as caught:
            await generator.__anext__()
        assert caught.value is expected

    asyncio.run(consume())
    span = exporter.get_finished_spans()[0]
    assert span.status.status_code is StatusCode.ERROR
    assert any(event.name == "exception" for event in span.events)
