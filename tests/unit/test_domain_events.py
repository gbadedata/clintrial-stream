"""Tests for clintrial.domain.events."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from pydantic import TypeAdapter, ValidationError

from clintrial.domain.events import (
    AdverseEvent,
    AdverseEventOutcome,
    AdverseEventSeverity,
    EnrollmentEvent,
    EnrollmentStatus,
    LabAnalyte,
    LabResult,
    SeriousnessCriterion,
    TrialEvent,
)
from clintrial.domain.identifiers import (
    PatientId,
    SiteId,
    StudyId,
)

pytestmark = pytest.mark.unit

# =============================================================================
# Helpers
# =============================================================================
NOW = datetime(2026, 5, 9, 0, 0, 0, tzinfo=UTC)
ONSET = NOW - timedelta(days=2)


def _common_envelope() -> dict[str, Any]:
    """Minimal valid envelope fields for any event."""
    return {
        "study_id": StudyId("NCT04567890"),
        "site_id": SiteId("SITE-LON-001"),
        "patient_id": PatientId("P-12345"),
        "event_timestamp": NOW,
    }


# =============================================================================
# AdverseEvent
# =============================================================================
class TestAdverseEvent:
    def test_minimal_valid_event(self) -> None:
        ae = AdverseEvent(
            **_common_envelope(),
            preferred_term="Headache",
            severity=AdverseEventSeverity.GRADE_1_MILD,
            onset_date=ONSET,
        )
        assert ae.event_type == "adverse_event"
        assert ae.is_serious is False
        assert ae.outcome == AdverseEventOutcome.UNKNOWN
        assert ae.event_id is not None
        assert ae.correlation_id is not None

    def test_serious_event_requires_seriousness_criteria(self) -> None:
        with pytest.raises(ValidationError, match="seriousness_criteria"):
            AdverseEvent(
                **_common_envelope(),
                preferred_term="Anaphylaxis",
                severity=AdverseEventSeverity.GRADE_3_SEVERE,
                is_serious=True,
                seriousness_criteria=[],
                onset_date=ONSET,
            )

    def test_seriousness_criteria_without_serious_flag_rejected(self) -> None:
        with pytest.raises(ValidationError, match="is_serious=False"):
            AdverseEvent(
                **_common_envelope(),
                preferred_term="Headache",
                severity=AdverseEventSeverity.GRADE_1_MILD,
                is_serious=False,
                seriousness_criteria=[SeriousnessCriterion.HOSPITALISATION],
                onset_date=ONSET,
            )

    def test_grade_5_must_have_fatal_outcome(self) -> None:
        with pytest.raises(ValidationError, match="outcome=fatal"):
            AdverseEvent(
                **_common_envelope(),
                preferred_term="Cardiac arrest",
                severity=AdverseEventSeverity.GRADE_5_DEATH,
                is_serious=True,
                seriousness_criteria=[SeriousnessCriterion.DEATH],
                outcome=AdverseEventOutcome.RECOVERED,
                onset_date=ONSET,
            )

    def test_grade_5_must_have_death_in_seriousness_criteria(self) -> None:
        with pytest.raises(ValidationError, match="results_in_death"):
            AdverseEvent(
                **_common_envelope(),
                preferred_term="Cardiac arrest",
                severity=AdverseEventSeverity.GRADE_5_DEATH,
                is_serious=True,
                seriousness_criteria=[SeriousnessCriterion.LIFE_THREATENING],
                outcome=AdverseEventOutcome.FATAL,
                onset_date=ONSET,
            )

    def test_resolution_before_onset_rejected(self) -> None:
        with pytest.raises(ValidationError, match="resolution_date"):
            AdverseEvent(
                **_common_envelope(),
                preferred_term="Headache",
                severity=AdverseEventSeverity.GRADE_1_MILD,
                onset_date=ONSET,
                resolution_date=ONSET - timedelta(days=1),
            )

    def test_naive_datetime_rejected(self) -> None:
        envelope = _common_envelope()
        envelope["event_timestamp"] = datetime(2026, 5, 9, 0, 0, 0)  # no tzinfo
        with pytest.raises(ValidationError, match="timezone-aware"):
            AdverseEvent(
                **envelope,
                preferred_term="Headache",
                severity=AdverseEventSeverity.GRADE_1_MILD,
                onset_date=ONSET,
            )

    def test_extra_fields_rejected(self) -> None:
        with pytest.raises(ValidationError):
            AdverseEvent(
                **_common_envelope(),
                preferred_term="Headache",
                severity=AdverseEventSeverity.GRADE_1_MILD,
                onset_date=ONSET,
                made_up_field="should_be_rejected",  # type: ignore[call-arg]
            )


# =============================================================================
# EnrollmentEvent
# =============================================================================
class TestEnrollmentEvent:
    def test_minimal_valid_enrollment(self) -> None:
        evt = EnrollmentEvent(
            **_common_envelope(),
            new_status=EnrollmentStatus.ENROLLED,
        )
        assert evt.event_type == "enrollment_event"
        assert evt.previous_status is None
        assert evt.reason is None

    def test_withdrawal_requires_reason(self) -> None:
        with pytest.raises(ValidationError, match="requires a reason"):
            EnrollmentEvent(
                **_common_envelope(),
                new_status=EnrollmentStatus.WITHDRAWN_BY_PATIENT,
            )

    def test_withdrawal_with_reason_accepted(self) -> None:
        evt = EnrollmentEvent(
            **_common_envelope(),
            new_status=EnrollmentStatus.WITHDRAWN_BY_PATIENT,
            reason="Patient requested withdrawal",
        )
        assert evt.reason == "Patient requested withdrawal"

    def test_screen_failure_requires_reason(self) -> None:
        with pytest.raises(ValidationError, match="requires a reason"):
            EnrollmentEvent(
                **_common_envelope(),
                new_status=EnrollmentStatus.SCREEN_FAILURE,
            )


# =============================================================================
# LabResult
# =============================================================================
class TestLabResult:
    def _common_lab_kwargs(self) -> dict[str, Any]:
        return {
            **_common_envelope(),
            "analyte": LabAnalyte.HAEMOGLOBIN,
            "unit": "g/L",
            "reference_low": Decimal("120"),
            "reference_high": Decimal("160"),
            "specimen_collected_at": NOW - timedelta(hours=1),
        }

    def test_in_range_value(self) -> None:
        lab = LabResult(**self._common_lab_kwargs(), value=Decimal("140"))
        assert lab.event_type == "lab_result"
        assert lab.is_out_of_range is False

    def test_below_reference_is_out_of_range(self) -> None:
        lab = LabResult(**self._common_lab_kwargs(), value=Decimal("100"))
        assert lab.is_out_of_range is True

    def test_above_reference_is_out_of_range(self) -> None:
        lab = LabResult(**self._common_lab_kwargs(), value=Decimal("180"))
        assert lab.is_out_of_range is True

    def test_inverted_reference_range_rejected(self) -> None:
        with pytest.raises(ValidationError, match="reference_low must be"):
            LabResult(
                **_common_envelope(),
                analyte=LabAnalyte.HAEMOGLOBIN,
                value=Decimal("140"),
                unit="g/L",
                reference_low=Decimal("160"),
                reference_high=Decimal("120"),
                specimen_collected_at=NOW,
            )

    def test_specimen_naive_datetime_rejected(self) -> None:
        kwargs = self._common_lab_kwargs()
        kwargs["specimen_collected_at"] = datetime(2026, 5, 9, 0, 0, 0)  # naive
        with pytest.raises(ValidationError, match="timezone-aware"):
            LabResult(**kwargs, value=Decimal("140"))


# =============================================================================
# Discriminated union
# =============================================================================
class TestTrialEventDiscriminator:
    """Verify that TrialEvent dispatches to the right variant by event_type."""

    _adapter: TypeAdapter[TrialEvent] = TypeAdapter(TrialEvent)

    def test_adverse_event_round_trip(self) -> None:
        original = AdverseEvent(
            **_common_envelope(),
            preferred_term="Nausea",
            severity=AdverseEventSeverity.GRADE_2_MODERATE,
            onset_date=ONSET,
        )
        serialised = original.model_dump_json()
        round_tripped = self._adapter.validate_json(serialised)
        assert isinstance(round_tripped, AdverseEvent)
        assert round_tripped.preferred_term == "Nausea"

    def test_lab_result_round_trip(self) -> None:
        original = LabResult(
            **_common_envelope(),
            analyte=LabAnalyte.GLUCOSE,
            value=Decimal("5.2"),
            unit="mmol/L",
            reference_low=Decimal("3.9"),
            reference_high=Decimal("5.5"),
            specimen_collected_at=NOW - timedelta(hours=1),
        )
        round_tripped = self._adapter.validate_json(original.model_dump_json())
        assert isinstance(round_tripped, LabResult)
        assert round_tripped.value == Decimal("5.2")

    def test_unknown_event_type_rejected(self) -> None:
        bad_payload = {
            "event_type": "nonsense",
            **_common_envelope(),
        }
        with pytest.raises(ValidationError):
            self._adapter.validate_python(bad_payload)
