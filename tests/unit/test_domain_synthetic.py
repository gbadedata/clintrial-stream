"""Tests for clintrial.domain.synthetic."""

from __future__ import annotations

import pytest

from clintrial.domain.events import (
    AdverseEvent,
    EnrollmentEvent,
    LabResult,
)
from clintrial.domain.synthetic import (
    ANALYTE_RANGES,
    SAMPLE_SITES,
    SAMPLE_STUDIES,
    TrialEventGenerator,
)

pytestmark = pytest.mark.unit


class TestTrialEventGenerator:
    def test_default_generator_produces_valid_events(self) -> None:
        gen = TrialEventGenerator(seed=42, n_patients=10)
        events = gen.stream(total_events=100)
        assert len(events) == 100
        # Every event must be one of the three known types
        valid_types = (AdverseEvent, EnrollmentEvent, LabResult)
        assert all(isinstance(e, valid_types) for e in events)

    def test_seed_produces_deterministic_output(self) -> None:
        a = TrialEventGenerator(seed=123, n_patients=10).stream(total_events=20)
        b = TrialEventGenerator(seed=123, n_patients=10).stream(total_events=20)
        # Compare a stable representation; full event_id/timestamps differ by
        # generation moment, but the semantic fields should match
        a_events = [e.event_type for e in a]
        b_events = [e.event_type for e in b]
        assert a_events == b_events

    def test_different_seeds_produce_different_output(self) -> None:
        a = TrialEventGenerator(seed=1, n_patients=10).stream(total_events=50)
        b = TrialEventGenerator(seed=999, n_patients=10).stream(total_events=50)
        a_types = [e.event_type for e in a]
        b_types = [e.event_type for e in b]
        assert a_types != b_types

    def test_kind_filter_produces_only_that_kind(self) -> None:
        gen = TrialEventGenerator(seed=42)
        labs = [gen.next_event(kind="lab_result") for _ in range(20)]
        assert all(isinstance(e, LabResult) for e in labs)

        aes = [gen.next_event(kind="adverse_event") for _ in range(20)]
        assert all(isinstance(e, AdverseEvent) for e in aes)

        enrollments = [gen.next_event(kind="enrollment_event") for _ in range(20)]
        assert all(isinstance(e, EnrollmentEvent) for e in enrollments)

    def test_lab_results_use_known_analyte_ranges(self) -> None:
        gen = TrialEventGenerator(seed=42)
        labs = [gen.next_event(kind="lab_result") for _ in range(50)]
        for lab in labs:
            assert isinstance(lab, LabResult)
            expected_low, expected_high, expected_unit = ANALYTE_RANGES[lab.analyte]
            assert lab.reference_low == expected_low
            assert lab.reference_high == expected_high
            assert lab.unit == expected_unit

    def test_studies_and_sites_come_from_sample_sets(self) -> None:
        gen = TrialEventGenerator(seed=42)
        events = gen.stream(total_events=100)
        for evt in events:
            assert evt.study_id in SAMPLE_STUDIES
            assert evt.site_id in SAMPLE_SITES

    def test_patient_pool_is_finite(self) -> None:
        n_patients = 5
        gen = TrialEventGenerator(seed=42, n_patients=n_patients)
        events = gen.stream(total_events=200)
        unique_patients = {e.patient_id for e in events}
        assert len(unique_patients) <= n_patients

    def test_out_of_range_probability_is_respected(self) -> None:
        # With probability=1.0, every lab result should be out of range
        gen = TrialEventGenerator(seed=42, out_of_range_lab_probability=1.0)
        labs = [gen.next_event(kind="lab_result") for _ in range(30)]
        for lab in labs:
            assert isinstance(lab, LabResult)
            assert lab.is_out_of_range, (
                f"Expected out-of-range, got {lab.value} "
                f"in [{lab.reference_low}, {lab.reference_high}]"
            )

    def test_zero_out_of_range_probability_keeps_values_in_range(self) -> None:
        gen = TrialEventGenerator(seed=42, out_of_range_lab_probability=0.0)
        labs = [gen.next_event(kind="lab_result") for _ in range(30)]
        for lab in labs:
            assert isinstance(lab, LabResult)
            assert not lab.is_out_of_range

    def test_serious_ae_triggers_seriousness_criteria(self) -> None:
        gen = TrialEventGenerator(seed=42, serious_ae_probability=1.0)
        for _ in range(20):
            evt = gen.next_event(kind="adverse_event")
            assert isinstance(evt, AdverseEvent)
            assert evt.is_serious is True
            assert len(evt.seriousness_criteria) >= 1
