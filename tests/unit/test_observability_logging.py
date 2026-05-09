"""Tests for clintrial.observability.logging."""

from __future__ import annotations

import pytest

from clintrial.observability.logging import (
    bind_correlation_id,
    clear_correlation_id,
    get_correlation_id,
)

pytestmark = pytest.mark.unit


class TestCorrelationIdContext:
    def setup_method(self) -> None:
        # Each test starts with a clean correlation id
        clear_correlation_id()

    def test_no_correlation_id_by_default(self) -> None:
        assert get_correlation_id() is None

    def test_bind_then_get(self) -> None:
        bind_correlation_id("01HABC123XYZ")
        assert get_correlation_id() == "01HABC123XYZ"

    def test_clear_resets_to_none(self) -> None:
        bind_correlation_id("01HABC123XYZ")
        clear_correlation_id()
        assert get_correlation_id() is None

    def test_rebind_replaces_value(self) -> None:
        bind_correlation_id("first")
        bind_correlation_id("second")
        assert get_correlation_id() == "second"


class TestContextVarIsolation:
    """ContextVars must be isolated across tasks.

    This isn't trivial — a global variable would leak across tests and across
    concurrent producer batches. ContextVar with .set() inside an async task
    creates a copy that doesn't escape.
    """

    @pytest.mark.asyncio()
    async def test_context_isolated_in_async_task(self) -> None:
        import asyncio

        bind_correlation_id("outer")

        async def task_a() -> str | None:
            bind_correlation_id("inner-a")
            await asyncio.sleep(0)
            return get_correlation_id()

        async def task_b() -> str | None:
            bind_correlation_id("inner-b")
            await asyncio.sleep(0)
            return get_correlation_id()

        # Run both tasks concurrently — each should see its own value
        result_a, result_b = await asyncio.gather(task_a(), task_b())
        assert result_a == "inner-a"
        assert result_b == "inner-b"
