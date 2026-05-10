"""Tests for clintrial.producer.kinesis_client.

We use moto's mock_aws decorator to fake the Kinesis service in-process.
No real AWS calls, no credentials needed, runs in CI.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import cast

import boto3
import pytest
from moto import mock_aws

from clintrial.domain.events import (
    AdverseEvent,
    AdverseEventSeverity,
)
from clintrial.domain.identifiers import (
    PatientId,
    SiteId,
    StudyId,
)
from clintrial.producer.kinesis_client import KinesisProducer

pytestmark = pytest.mark.unit

# -----------------------------------------------------------------------------
# Fixtures
# -----------------------------------------------------------------------------
NOW = datetime(2026, 5, 9, 12, 0, 0, tzinfo=UTC)


def _make_event(patient: str = "P-12345") -> AdverseEvent:
    return AdverseEvent(
        study_id=StudyId("NCT04567890"),
        site_id=SiteId("SITE-LON-001"),
        patient_id=PatientId(patient),
        event_timestamp=NOW,
        preferred_term="Headache",
        severity=AdverseEventSeverity.GRADE_1_MILD,
        onset_date=NOW - timedelta(days=1),
    )


@pytest.fixture()
def kinesis_stream() -> Iterator[str]:
    """Provision a fake Kinesis stream via moto and yield its name.

    The mock context manager is inside the fixture so it's active before
    boto3.client is called. Without this, boto3 would reach real AWS.
    """
    with mock_aws():
        stream_name = "test-stream"
        client = boto3.client("kinesis", region_name="eu-west-2")
        client.create_stream(StreamName=stream_name, ShardCount=1)
        yield stream_name


# -----------------------------------------------------------------------------
# Happy path
# -----------------------------------------------------------------------------
class TestPutEventsHappyPath:
    def test_empty_list_is_noop(self, kinesis_stream: str) -> None:
        producer = KinesisProducer(stream_name=kinesis_stream)
        result = producer.put_events([])
        assert result.records_attempted == 0
        assert result.records_succeeded == 0
        assert result.records_failed == 0

    def test_single_event_succeeds(self, kinesis_stream: str) -> None:
        producer = KinesisProducer(stream_name=kinesis_stream)
        result = producer.put_events([_make_event()])
        assert result.records_attempted == 1
        assert result.records_succeeded == 1
        assert result.records_failed == 0
        assert result.success_rate == 1.0

    def test_batch_of_events_succeeds(self, kinesis_stream: str) -> None:
        producer = KinesisProducer(stream_name=kinesis_stream)
        events = [_make_event(f"P-{i:05d}") for i in range(50)]
        result = producer.put_events(events)
        assert result.records_attempted == 50
        assert result.records_succeeded == 50

    def test_partition_key_is_patient_id(self, kinesis_stream: str) -> None:
        # Events for the same patient must produce identical partition keys.
        # The fixture ensures moto is active even though we only use static methods.
        _ = kinesis_stream
        e1 = _make_event(patient="P-99999")
        e2 = _make_event(patient="P-99999")
        entry1 = KinesisProducer._to_entry(e1)
        entry2 = KinesisProducer._to_entry(e2)
        assert entry1["PartitionKey"] == entry2["PartitionKey"] == "P-99999"

    def test_payload_is_valid_json(self, kinesis_stream: str) -> None:
        import json

        event = _make_event()
        entry = KinesisProducer._to_entry(event)
        # Decode bytes back to dict
        payload = json.loads(cast(bytes, entry["Data"]).decode("utf-8"))
        assert payload["event_type"] == "adverse_event"
        assert payload["patient_id"] == "P-12345"


# -----------------------------------------------------------------------------
# Batch chunking — verify we respect Kinesis's 500-record-per-call limit
# -----------------------------------------------------------------------------
class TestBatchChunking:
    def test_chunks_split_at_500(self, kinesis_stream: str) -> None:
        # Create a 600-event batch — must be split into two PutRecords calls
        producer = KinesisProducer(stream_name=kinesis_stream)
        events = [_make_event(f"P-{i:05d}") for i in range(600)]
        result = producer.put_events(events)
        assert result.records_attempted == 600
        assert result.records_succeeded == 600

    def test_chunk_helper_respects_size(self) -> None:
        chunks = KinesisProducer._chunk(list(range(1050)), 500)  # type: ignore[arg-type]
        assert len(chunks) == 3
        assert len(chunks[0]) == 500
        assert len(chunks[1]) == 500
        assert len(chunks[2]) == 50
