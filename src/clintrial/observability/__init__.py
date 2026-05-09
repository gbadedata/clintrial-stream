"""Observability — structured logging, metrics, and tracing utilities.

The whole point of this package is that producer, consumer, and API code
should be able to emit logs and metrics with a single import:

    from clintrial.observability import get_logger, MetricsClient

No structlog config in app code. No boto3.client('cloudwatch') everywhere.
One source of truth, applied consistently.
"""

from clintrial.observability.logging import (
    bind_correlation_id,
    clear_correlation_id,
    configure_logging,
    get_correlation_id,
    get_logger,
)
from clintrial.observability.metrics import MetricsClient, MetricUnit

__all__ = [
    "MetricUnit",
    "MetricsClient",
    "bind_correlation_id",
    "clear_correlation_id",
    "configure_logging",
    "get_correlation_id",
    "get_logger",
]
