"""CloudWatch custom metrics via the Embedded Metric Format (EMF).

EMF is a JSON specification that lets you emit CloudWatch metrics by simply
printing a structured log line. CloudWatch parses the line and extracts
metrics — no separate boto3 PutMetricData call required, no extra latency,
no extra cost (you pay only for the log ingestion that you'd already pay for).

This is the modern way to emit custom metrics from Lambda. It's how
aws-lambda-powertools does it under the hood.

Format spec:
    https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/CloudWatch_Embedded_Metric_Format_Specification.html

Usage:

    from clintrial.observability import MetricsClient, MetricUnit

    metrics = MetricsClient(namespace="ClinTrialStream/Producer")
    metrics.add_dimension("environment", "dev")
    metrics.add_dimension("stream_name", "clintrial-stream-dev-events")

    metrics.put_metric("EventsProduced", 1, MetricUnit.COUNT)
    metrics.put_metric("EventLatencyMs", 42.3, MetricUnit.MILLISECONDS)

    metrics.flush()  # writes the EMF JSON line to stdout

The flush is what triggers CloudWatch to ingest. Typical pattern: call
flush at the end of each batch / Lambda invocation.
"""

from __future__ import annotations

import json
import sys
import time
from enum import StrEnum
from typing import IO, Any


class MetricUnit(StrEnum):
    """CloudWatch metric units, exact strings expected by EMF.

    Subset of the full CloudWatch enum — these are the ones you actually use.
    See: https://docs.aws.amazon.com/AmazonCloudWatch/latest/APIReference/API_MetricDatum.html
    """

    COUNT = "Count"
    SECONDS = "Seconds"
    MILLISECONDS = "Milliseconds"
    BYTES = "Bytes"
    KILOBYTES = "Kilobytes"
    PERCENT = "Percent"
    NONE = "None"


class MetricsClient:
    """Buffers metrics in memory until flush(), then writes a single EMF line.

    Call once at the start of a logical scope (a producer batch, a Lambda
    invocation), accumulate metrics with put_metric(), then flush() at the end.

    Args:
        namespace: CloudWatch metrics namespace (e.g. ``ClinTrialStream/Producer``).
        stream: Where to write the EMF line. Defaults to stdout. Tests pass StringIO.
    """

    def __init__(self, namespace: str, *, stream: IO[str] | None = None) -> None:
        self._namespace = namespace
        self._stream: IO[str] = stream if stream is not None else sys.stdout
        self._metrics: list[dict[str, Any]] = []
        self._dimensions: dict[str, str] = {}
        self._properties: dict[str, Any] = {}

    # -------------------------------------------------------------------------
    # Dimensions
    # -------------------------------------------------------------------------
    def add_dimension(self, name: str, value: str) -> None:
        """Add a dimension that applies to every metric in this batch.

        Dimensions partition metrics: e.g. EventsProduced by stream_name lets
        you graph each stream independently. Limit: 30 dimensions per metric.
        """
        if len(self._dimensions) >= 30:
            raise ValueError("CloudWatch allows at most 30 dimensions per metric")
        self._dimensions[name] = value

    # -------------------------------------------------------------------------
    # Properties (high-cardinality context, not a metric dimension)
    # -------------------------------------------------------------------------
    def add_property(self, name: str, value: Any) -> None:
        """Add a non-dimensional property to the EMF record.

        Properties show up in the log line for searchability but don't create
        cartesian-product cost in CloudWatch metrics. Use for things like
        request_id, patient_id, or anything high-cardinality.
        """
        self._properties[name] = value

    # -------------------------------------------------------------------------
    # Metrics
    # -------------------------------------------------------------------------
    def put_metric(self, name: str, value: float, unit: MetricUnit = MetricUnit.NONE) -> None:
        """Record a single metric value.

        Multiple calls with the same name in one batch are aggregated by
        CloudWatch into stats (sum, average, min, max, count).
        """
        self._metrics.append({"Name": name, "Unit": unit.value, "Value": value})

    # -------------------------------------------------------------------------
    # Flush
    # -------------------------------------------------------------------------
    def flush(self) -> None:
        """Write the buffered metrics as a single EMF JSON line and reset.

        Produces output like:
            {"_aws":{"Timestamp":...,"CloudWatchMetrics":[{...}]},
             "EventsProduced":1, "stream_name":"...", ...}

        CloudWatch Logs picks this up automatically and creates the metrics.
        """
        if not self._metrics:
            return

        record: dict[str, Any] = {
            "_aws": {
                "Timestamp": int(time.time() * 1000),
                "CloudWatchMetrics": [
                    {
                        "Namespace": self._namespace,
                        "Dimensions": [list(self._dimensions.keys())],
                        "Metrics": self._metrics,
                    }
                ],
            },
        }

        # Dimensions are emitted as top-level keys (CloudWatch reads them from there)
        record.update(self._dimensions)

        # Metric values are also emitted as top-level keys
        for m in self._metrics:
            record[m["Name"]] = m["Value"]

        # Non-metric properties for log searchability
        record.update(self._properties)

        # Single line, no whitespace, so CloudWatch's parser is happy
        self._stream.write(json.dumps(record, separators=(",", ":"), default=str) + "\n")
        self._stream.flush()

        # Reset for next batch
        self._metrics.clear()
        self._properties.clear()

    # -------------------------------------------------------------------------
    # Context manager — auto-flush on exit
    # -------------------------------------------------------------------------
    def __enter__(self) -> MetricsClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.flush()
