"""Tests for clintrial.producer.event_generator (the ProducerRunner)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from clintrial.domain.synthetic import TrialEventGenerator
from clintrial.producer.event_generator import ProducerRunner
from clintrial.producer.kinesis_client import PutResult

pytestmark = pytest.mark.unit


def _mock_producer(success_count: int = 100, failure_count: int = 0) -> MagicMock:
    """A KinesisProducer mock that returns canned PutResults."""
    producer = MagicMock()
    producer.put_events.return_value = PutResult(
        records_attempted=success_count + failure_count,
        records_succeeded=success_count,
        records_failed=failure_count,
    )
    return producer


class TestProducerRunner:
    def test_emits_exactly_total_events(self) -> None:
        producer = _mock_producer(success_count=20)
        runner = ProducerRunner(
            producer=producer,
            generator=TrialEventGenerator(seed=1),
            target_rate_eps=1000,  # high rate to make test fast
            batch_size=20,
        )
        stats = runner.run(total_events=20)
        assert stats.events_attempted == 20
        assert stats.events_succeeded == 20
        assert stats.batches_sent == 1

    def test_total_events_split_across_batches(self) -> None:
        # 100 events, batch_size 20 → 5 batches
        # Mock returns 20 successes per batch
        producer = _mock_producer(success_count=20)
        runner = ProducerRunner(
            producer=producer,
            generator=TrialEventGenerator(seed=1),
            target_rate_eps=10_000,
            batch_size=20,
        )
        stats = runner.run(total_events=100)
        assert stats.events_attempted == 100
        assert stats.batches_sent == 5

    def test_invalid_rate_rejected(self) -> None:
        with pytest.raises(ValueError, match="target_rate_eps"):
            ProducerRunner(
                producer=_mock_producer(),
                generator=TrialEventGenerator(seed=1),
                target_rate_eps=0,
            )

    def test_invalid_batch_size_rejected(self) -> None:
        with pytest.raises(ValueError, match="batch_size"):
            ProducerRunner(
                producer=_mock_producer(),
                generator=TrialEventGenerator(seed=1),
                target_rate_eps=10,
                batch_size=600,  # exceeds Kinesis limit
            )

    def test_failures_propagate_to_stats(self) -> None:
        producer = _mock_producer(success_count=15, failure_count=5)
        runner = ProducerRunner(
            producer=producer,
            generator=TrialEventGenerator(seed=1),
            target_rate_eps=10_000,
            batch_size=20,
        )
        stats = runner.run(total_events=20)
        assert stats.events_succeeded == 15
        assert stats.events_failed == 5

    def test_rate_limiting_takes_at_least_expected_time(self) -> None:
        """If we ask for 50 events at 100 eps with batch=50, total time >= ~0.5s."""
        import time

        producer = _mock_producer(success_count=50)
        runner = ProducerRunner(
            producer=producer,
            generator=TrialEventGenerator(seed=1),
            target_rate_eps=100,  # 100 eps
            batch_size=50,
        )

        start = time.monotonic()
        runner.run(total_events=50)
        elapsed = time.monotonic() - start

        # 50 events at 100 eps = should take ~0.5s. Allow some headroom for fast machines.
        # We check at least 0.4s to avoid flakiness, but not so tight that it's
        # affected by mock overhead.
        assert elapsed >= 0.4, f"Run completed too fast: {elapsed}s"
