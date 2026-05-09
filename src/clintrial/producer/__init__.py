"""Synthetic event producer for the ClinTrial-Stream Kinesis stream.

The producer simulates clinical trial sites emitting events at a configurable
rate. Used for demos and load testing — the real platform replaces this with
ingestion from EHR systems, EDC platforms, etc.

Public API:
    KinesisProducer  — the boto3-backed client with retry/backoff
    ProducerRunner   — orchestrates the rate-limited emission loop
    PutResult        — result of a single PutRecords call

Run from CLI:
    clintrial-producer --total 1000 --rate 50
"""

from clintrial.producer.event_generator import ProducerRunner
from clintrial.producer.kinesis_client import KinesisProducer, PutResult

__all__ = [
    "KinesisProducer",
    "ProducerRunner",
    "PutResult",
]
