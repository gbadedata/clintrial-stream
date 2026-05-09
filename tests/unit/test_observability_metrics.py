"""Tests for clintrial.observability.metrics."""

from __future__ import annotations

import io
import json
from typing import Any, cast

import pytest

from clintrial.observability.metrics import MetricsClient, MetricUnit

pytestmark = pytest.mark.unit


def _capture_emf(client: MetricsClient, stream: io.StringIO) -> dict[str, Any]:
    """Flush a client and return the parsed EMF JSON record."""
    client.flush()
    raw = stream.getvalue().strip()
    return cast(dict[str, Any], json.loads(raw))


class TestMetricsClientEmfFormat:
    def test_no_metrics_no_output(self) -> None:
        stream = io.StringIO()
        client = MetricsClient(namespace="Test", stream=stream)
        client.flush()
        assert stream.getvalue() == ""

    def test_single_metric_produces_valid_emf(self) -> None:
        stream = io.StringIO()
        client = MetricsClient(namespace="ClinTrialStream/Test", stream=stream)
        client.put_metric("EventsProduced", 42, MetricUnit.COUNT)
        record = _capture_emf(client, stream)

        # EMF spec requires _aws envelope with these keys
        assert "_aws" in record
        assert "Timestamp" in record["_aws"]
        assert "CloudWatchMetrics" in record["_aws"]

        cwm = record["_aws"]["CloudWatchMetrics"][0]
        assert cwm["Namespace"] == "ClinTrialStream/Test"

        # Metric definitions
        assert cwm["Metrics"][0] == {
            "Name": "EventsProduced",
            "Unit": "Count",
            "Value": 42,
        }

        # Metric value also appears at top level
        assert record["EventsProduced"] == 42

    def test_dimensions_in_emf(self) -> None:
        stream = io.StringIO()
        client = MetricsClient(namespace="Test", stream=stream)
        client.add_dimension("environment", "dev")
        client.add_dimension("stream_name", "events")
        client.put_metric("Latency", 12.5, MetricUnit.MILLISECONDS)
        record = _capture_emf(client, stream)

        # Dimensions registered in CloudWatchMetrics
        cwm = record["_aws"]["CloudWatchMetrics"][0]
        # Dimensions field is a list of lists per EMF spec
        assert cwm["Dimensions"][0] == ["environment", "stream_name"]

        # And present as top-level keys
        assert record["environment"] == "dev"
        assert record["stream_name"] == "events"

    def test_multiple_metrics_in_one_record(self) -> None:
        stream = io.StringIO()
        client = MetricsClient(namespace="Test", stream=stream)
        client.put_metric("EventsProduced", 100, MetricUnit.COUNT)
        client.put_metric("LatencyMs", 5.5, MetricUnit.MILLISECONDS)
        record = _capture_emf(client, stream)

        metric_names = {m["Name"] for m in record["_aws"]["CloudWatchMetrics"][0]["Metrics"]}
        assert metric_names == {"EventsProduced", "LatencyMs"}

    def test_property_appears_at_top_level_not_in_metrics(self) -> None:
        stream = io.StringIO()
        client = MetricsClient(namespace="Test", stream=stream)
        client.add_property("patient_id", "P-12345")
        client.put_metric("EventsProduced", 1, MetricUnit.COUNT)
        record = _capture_emf(client, stream)

        # patient_id at top level
        assert record["patient_id"] == "P-12345"

        # But NOT in the Metrics array (it's a property, not a metric)
        metric_names = [m["Name"] for m in record["_aws"]["CloudWatchMetrics"][0]["Metrics"]]
        assert "patient_id" not in metric_names

    def test_too_many_dimensions_rejected(self) -> None:
        client = MetricsClient(namespace="Test", stream=io.StringIO())
        for i in range(30):
            client.add_dimension(f"d{i}", str(i))
        with pytest.raises(ValueError, match="30 dimensions"):
            client.add_dimension("d30", "31")

    def test_flush_resets_state(self) -> None:
        stream = io.StringIO()
        client = MetricsClient(namespace="Test", stream=stream)
        client.put_metric("First", 1, MetricUnit.COUNT)
        client.flush()

        # Second flush with no new metrics should produce no output
        before = stream.getvalue()
        client.flush()
        assert stream.getvalue() == before

    def test_context_manager_auto_flushes(self) -> None:
        stream = io.StringIO()
        with MetricsClient(namespace="Test", stream=stream) as client:
            client.put_metric("EventsProduced", 5, MetricUnit.COUNT)
        # After __exit__, EMF should have been written
        record = json.loads(stream.getvalue().strip())
        assert record["EventsProduced"] == 5
