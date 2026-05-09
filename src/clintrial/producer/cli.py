"""Command-line entrypoint for the synthetic producer.

Usage:
    clintrial-producer --total 1000 --rate 50

Or via make:
    make producer EVENTS=1000 RATE=50
"""

from __future__ import annotations

import sys

import click

from clintrial.config import settings
from clintrial.domain.identifiers import new_correlation_id
from clintrial.domain.synthetic import TrialEventGenerator
from clintrial.observability import (
    MetricsClient,
    bind_correlation_id,
    configure_logging,
    get_logger,
)
from clintrial.producer.event_generator import ProducerRunner
from clintrial.producer.kinesis_client import KinesisProducer


@click.command(context_settings={"help_option_names": ["-h", "--help"]})
@click.option(
    "--total",
    "-n",
    type=click.IntRange(0, None),
    default=None,
    help=("Total events to emit (0 = forever, default = settings.producer_total_events)."),
)
@click.option(
    "--rate",
    "-r",
    type=click.IntRange(1, 10_000),
    default=None,
    help=("Target events per second (default = settings.producer_rate_eps)."),
)
@click.option(
    "--batch-size",
    "-b",
    type=click.IntRange(1, 500),
    default=100,
    help="Records per Kinesis PutRecords call (1-500).",
)
@click.option(
    "--seed",
    "-s",
    type=int,
    default=42,
    help="Random seed for the synthetic generator (deterministic output).",
)
@click.option(
    "--n-patients",
    type=click.IntRange(1, None),
    default=50,
    help="Size of the synthetic patient pool.",
)
@click.option(
    "--stream-name",
    type=str,
    default=None,
    help="Override the configured Kinesis stream name.",
)
@click.option(
    "--json-logs/--console-logs",
    default=False,
    help="Emit JSON logs (production) or human-readable (local dev).",
)
def main(
    total: int | None,
    rate: int | None,
    batch_size: int,
    seed: int,
    n_patients: int,
    stream_name: str | None,
    json_logs: bool,
) -> None:
    """Stream synthetic clinical trial events to Kinesis."""
    # Resolve defaults from config if not provided
    total_events = total if total is not None else settings.producer_total_events
    target_rate = rate if rate is not None else settings.producer_rate_eps
    target_stream = stream_name or settings.kinesis_stream_name

    configure_logging(json_output=json_logs)
    bind_correlation_id(new_correlation_id())
    logger = get_logger("clintrial.producer.cli")

    logger.info(
        "producer_starting",
        stream_name=target_stream,
        total_events=total_events,
        rate_eps=target_rate,
        batch_size=batch_size,
        seed=seed,
        n_patients=n_patients,
    )

    # Build the producer chain
    metrics = MetricsClient(namespace="ClinTrialStream/Producer")
    metrics.add_dimension("environment", settings.app_env)
    metrics.add_dimension("stream_name", target_stream)

    producer = KinesisProducer(
        stream_name=target_stream,
        region=settings.aws_region,
        metrics=metrics,
    )
    generator = TrialEventGenerator(seed=seed, n_patients=n_patients)
    runner = ProducerRunner(
        producer=producer,
        generator=generator,
        target_rate_eps=target_rate,
        batch_size=batch_size,
        metrics=metrics,
    )

    # Run
    try:
        stats = runner.run(total_events=total_events)
    finally:
        # Always flush metrics on exit (success, error, or SIGINT)
        metrics.flush()

    # Print a friendly summary
    click.echo("")
    click.secho("=" * 60, fg="cyan")
    click.secho(" Producer run complete", fg="cyan", bold=True)
    click.secho("=" * 60, fg="cyan")
    click.echo(f"  Attempted:    {stats.events_attempted}")
    click.secho(f"  Succeeded:    {stats.events_succeeded}", fg="green")
    if stats.events_failed:
        click.secho(f"  Failed:       {stats.events_failed}", fg="red")
    else:
        click.echo(f"  Failed:       {stats.events_failed}")
    click.echo(f"  Batches sent: {stats.batches_sent}")
    click.echo(f"  Duration:     {stats.duration_seconds:.1f}s")
    click.echo(f"  Actual rate:  {stats.actual_rate:.1f} eps")
    click.secho("=" * 60, fg="cyan")

    # Exit non-zero if any events failed (so CI / scripts can detect)
    sys.exit(0 if stats.events_failed == 0 else 1)


if __name__ == "__main__":
    main()
