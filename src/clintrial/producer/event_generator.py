"""Rate-limited event emission loop.

Coordinates the three pieces:
    1. TrialEventGenerator — produces synthetic events
    2. KinesisProducer — sends events to AWS
    3. Rate limiter — enforces events-per-second cap

The runner is small but encodes a few production niceties:
    - Buffers events into batches to amortise Kinesis API calls
    - Sleeps between batches to honour the requested rate
    - Catches Ctrl-C cleanly and reports stats before exiting
    - Emits per-batch CloudWatch metrics (records, latency, success rate)
"""

from __future__ import annotations

import signal
import time
from dataclasses import dataclass
from types import FrameType

from clintrial.domain.synthetic import TrialEventGenerator
from clintrial.observability import MetricsClient, MetricUnit, get_logger
from clintrial.producer.kinesis_client import KinesisProducer

logger = get_logger(__name__)


@dataclass
class RunStats:
    """Aggregate results of a producer run."""

    events_attempted: int = 0
    events_succeeded: int = 0
    events_failed: int = 0
    batches_sent: int = 0
    duration_seconds: float = 0.0

    @property
    def actual_rate(self) -> float:
        if self.duration_seconds == 0:
            return 0.0
        return self.events_attempted / self.duration_seconds


class ProducerRunner:
    """Drives the synthetic event emission loop at a fixed rate.

    Args:
        producer: The KinesisProducer used to send events.
        generator: The TrialEventGenerator used to create events.
        target_rate_eps: Desired events per second.
        batch_size: How many events to accumulate per Kinesis PutRecords call.
            Up to 500 (Kinesis limit). Larger = fewer API calls = lower cost.
        metrics: Optional MetricsClient for batch-level metrics.
    """

    def __init__(
        self,
        producer: KinesisProducer,
        generator: TrialEventGenerator,
        target_rate_eps: int,
        batch_size: int = 100,
        metrics: MetricsClient | None = None,
    ) -> None:
        if target_rate_eps < 1:
            raise ValueError("target_rate_eps must be >= 1")
        if batch_size < 1 or batch_size > 500:
            raise ValueError("batch_size must be between 1 and 500")

        self._producer = producer
        self._generator = generator
        self._target_rate = target_rate_eps
        self._batch_size = batch_size
        self._metrics = metrics
        self._stop_requested = False

    def run(self, total_events: int) -> RunStats:
        """Emit ``total_events`` events at approximately the target rate.

        Args:
            total_events: How many events to send. Use 0 for "run forever
                until Ctrl-C".

        Returns:
            Aggregate statistics for the run.
        """
        # Install a SIGINT handler so Ctrl-C exits cleanly with stats
        original_handler = signal.signal(signal.SIGINT, self._handle_sigint)

        stats = RunStats()
        start_time = time.monotonic()

        # Time per batch to honour target rate
        # If target=50 eps and batch=100 events, each batch takes 100/50 = 2 seconds
        seconds_per_batch = self._batch_size / self._target_rate

        try:
            sent = 0
            while not self._stop_requested:
                if total_events > 0 and sent >= total_events:
                    break

                # Compute the batch size for this iteration (last batch may be smaller)
                remaining = total_events - sent if total_events > 0 else self._batch_size
                this_batch_size = min(self._batch_size, remaining)

                # Generate events
                events = [self._generator.next_event() for _ in range(this_batch_size)]

                batch_start = time.monotonic()
                result = self._producer.put_events(events)
                batch_elapsed = time.monotonic() - batch_start

                # Update stats
                stats.events_attempted += result.records_attempted
                stats.events_succeeded += result.records_succeeded
                stats.events_failed += result.records_failed
                stats.batches_sent += 1
                sent += this_batch_size

                # Per-batch metrics for the dashboard
                if self._metrics is not None:
                    self._metrics.put_metric(
                        "BatchLatencyMs",
                        batch_elapsed * 1000,
                        MetricUnit.MILLISECONDS,
                    )
                    self._metrics.put_metric(
                        "BatchSize",
                        result.records_attempted,
                        MetricUnit.COUNT,
                    )

                # Sleep to honour target rate (subtract time we already spent)
                sleep_for = seconds_per_batch - batch_elapsed
                if sleep_for > 0:
                    time.sleep(sleep_for)
        finally:
            stats.duration_seconds = time.monotonic() - start_time
            # Restore the previous SIGINT handler
            signal.signal(signal.SIGINT, original_handler)

        logger.info(
            "producer_run_complete",
            attempted=stats.events_attempted,
            succeeded=stats.events_succeeded,
            failed=stats.events_failed,
            batches=stats.batches_sent,
            duration_s=round(stats.duration_seconds, 2),
            actual_rate_eps=round(stats.actual_rate, 1),
        )

        return stats

    def _handle_sigint(self, _signum: int, _frame: FrameType | None) -> None:
        """Mark the runner for graceful shutdown on Ctrl-C."""
        logger.warning("sigint_received_stopping_after_current_batch")
        self._stop_requested = True
