"""Trial event domain models.

These are the three event types emitted by clinical trial sites:

1. AdverseEvent — a patient experiences an unexpected medical occurrence.
   Format follows ICH E2B(R3), the international standard required by FDA,
   EMA, and PMDA for individual case safety reports.

2. EnrollmentEvent — a patient is enrolled, withdrawn, or completes the study.
   Critical for protocol compliance reporting.

3. LabResult — a measurement of a biological analyte (blood, urine, vitals).
   High volume, generally low criticality, but used to flag drug toxicity.

All three share a common envelope (event_id, timestamp, correlation_id, etc.)
and are unified in the TrialEvent discriminated union.

DESIGN NOTE: We use Pydantic v2's discriminated unions (the `Field(discriminator=...)`
pattern) instead of inheritance because:
  - Discriminated unions serialise/deserialise with no ambiguity
  - The type checker can narrow `TrialEvent` to a specific variant
  - A single field (`event_type`) determines which validator runs
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from clintrial.domain.identifiers import (
    CorrelationId,
    EventId,
    PatientId,
    SiteId,
    StudyId,
    new_correlation_id,
    new_event_id,
)

# =============================================================================
# Enumerations — controlled vocabularies
# =============================================================================
# Real clinical trial systems use controlled vocabularies (CDISC, MedDRA,
# SNOMED CT) rather than free-text. Free-text causes downstream chaos:
# spelling variants, inconsistent capitalisation, language differences.
#
# These enums encode a tiny slice of those vocabularies — enough to be
# realistic without licensing the actual MedDRA dictionary (which costs
# thousands of dollars per year).


class AdverseEventSeverity(StrEnum):
    """Severity grade per CTCAE v5.0 (Common Terminology Criteria for Adverse Events).

    Real cancer trials use grades 1-5 from this exact scale.
    """

    GRADE_1_MILD = "grade_1_mild"
    GRADE_2_MODERATE = "grade_2_moderate"
    GRADE_3_SEVERE = "grade_3_severe"
    GRADE_4_LIFE_THREATENING = "grade_4_life_threatening"
    GRADE_5_DEATH = "grade_5_death"


class AdverseEventOutcome(StrEnum):
    """Outcome at the time of reporting per ICH E2B(R3) field E.i.7."""

    RECOVERED = "recovered"
    RECOVERING = "recovering"
    NOT_RECOVERED = "not_recovered"
    RECOVERED_WITH_SEQUELAE = "recovered_with_sequelae"
    FATAL = "fatal"
    UNKNOWN = "unknown"


class SeriousnessCriterion(StrEnum):
    """ICH E2B(R3) seriousness criteria (field E.i.3.2).

    An adverse event is considered "serious" if it meets at least ONE of these.
    The seriousness flag triggers regulatory reporting timelines (e.g. 7-day
    reporting for life-threatening events).
    """

    DEATH = "results_in_death"
    LIFE_THREATENING = "life_threatening"
    HOSPITALISATION = "requires_or_prolongs_hospitalisation"
    DISABILITY = "persistent_or_significant_disability"
    CONGENITAL_ANOMALY = "congenital_anomaly_or_birth_defect"
    OTHER_MEDICALLY_IMPORTANT = "other_medically_important"


class EnrollmentStatus(StrEnum):
    """Patient enrollment status per CDISC SDTM DS domain."""

    SCREENED = "screened"
    SCREEN_FAILURE = "screen_failure"
    ENROLLED = "enrolled"
    RANDOMISED = "randomised"
    COMPLETED = "completed"
    WITHDRAWN_BY_PATIENT = "withdrawn_by_patient"
    WITHDRAWN_BY_INVESTIGATOR = "withdrawn_by_investigator"
    LOST_TO_FOLLOW_UP = "lost_to_follow_up"
    DEATH = "death"


class LabAnalyte(StrEnum):
    """Common laboratory analytes per CDISC SDTM LB domain.

    A real LB submission has hundreds of analytes. These are the most common.
    """

    HAEMOGLOBIN = "haemoglobin"
    PLATELETS = "platelets"
    WHITE_BLOOD_CELLS = "white_blood_cells"
    NEUTROPHILS = "neutrophils"
    ALANINE_AMINOTRANSFERASE = "alanine_aminotransferase"  # ALT — liver function
    ASPARTATE_AMINOTRANSFERASE = "aspartate_aminotransferase"  # AST — liver function
    CREATININE = "creatinine"  # kidney function
    GLUCOSE = "glucose"
    SODIUM = "sodium"
    POTASSIUM = "potassium"


# =============================================================================
# Base envelope shared by all event types
# =============================================================================


class _EventEnvelope(BaseModel):
    """Common metadata shared by every trial event.

    Not exposed publicly — concrete event types inherit from this and add
    their own fields.
    """

    model_config = ConfigDict(
        # Forbid extra fields to catch typos like `study_di` instead of `study_id`
        extra="forbid",
        # Use enum values when serialising to JSON (instead of enum names)
        use_enum_values=True,
        # Allow population by both field name and alias (useful when consuming
        # legacy JSON that uses different naming conventions)
        populate_by_name=True,
    )

    # Identifiers
    event_id: EventId = Field(default_factory=new_event_id)
    correlation_id: CorrelationId = Field(default_factory=new_correlation_id)
    study_id: StudyId
    site_id: SiteId
    patient_id: PatientId

    # Timestamps — always UTC, always ISO-8601
    event_timestamp: datetime = Field(
        ...,
        description="When the event occurred at the trial site (clinical time)",
    )
    received_timestamp: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="When the event reached our ingestion system (system time)",
    )

    @field_validator("event_timestamp", "received_timestamp")
    @classmethod
    def _ensure_utc(cls, v: datetime) -> datetime:
        """Reject naive datetimes — every timestamp must be timezone-aware."""
        if v.tzinfo is None:
            raise ValueError("Timestamps must be timezone-aware (use UTC)")
        return v.astimezone(UTC)


# =============================================================================
# Adverse Event
# =============================================================================


class AdverseEvent(_EventEnvelope):
    """An adverse event reported during a clinical trial.

    Follows ICH E2B(R3) for the fields most commonly captured in source data.
    """

    event_type: Literal["adverse_event"] = "adverse_event"

    # MedDRA-style preferred term — the standardised name of the event.
    # Real systems use a MedDRA Preferred Term Code (e.g. 10019211) but for
    # synthetic data we use the human-readable term.
    preferred_term: str = Field(..., min_length=1, max_length=200)

    # Severity grade (CTCAE v5.0)
    severity: AdverseEventSeverity

    # Whether the event meets ANY seriousness criterion (ICH E2B(R3) E.i.3.1).
    # If True, `seriousness_criteria` MUST be non-empty.
    is_serious: bool = False
    seriousness_criteria: list[SeriousnessCriterion] = Field(default_factory=list)

    # Current outcome at time of report
    outcome: AdverseEventOutcome = AdverseEventOutcome.UNKNOWN

    # Onset and resolution dates (None if ongoing)
    onset_date: datetime
    resolution_date: datetime | None = None

    # Suspected drug (free text — real systems link to a drug dictionary)
    suspected_drug: str | None = Field(default=None, max_length=200)

    @model_validator(mode="after")
    def _validate_seriousness(self) -> AdverseEvent:
        """A serious AE must specify at least one seriousness criterion."""
        if self.is_serious and not self.seriousness_criteria:
            raise ValueError("is_serious=True requires at least one seriousness_criteria value")
        if not self.is_serious and self.seriousness_criteria:
            raise ValueError(
                "seriousness_criteria provided but is_serious=False — set is_serious=True"
            )
        return self

    @model_validator(mode="after")
    def _validate_grade5_outcome(self) -> AdverseEvent:
        """A grade 5 (death) event must have outcome=fatal and seriousness=death."""
        if self.severity == AdverseEventSeverity.GRADE_5_DEATH:
            if self.outcome != AdverseEventOutcome.FATAL:
                raise ValueError("Grade 5 events must have outcome=fatal")
            if SeriousnessCriterion.DEATH not in self.seriousness_criteria:
                raise ValueError(
                    "Grade 5 events must list 'results_in_death' in seriousness_criteria"
                )
        return self

    @model_validator(mode="after")
    def _validate_resolution_after_onset(self) -> AdverseEvent:
        """Resolution date must not precede onset date."""
        if self.resolution_date is not None and self.resolution_date < self.onset_date:
            raise ValueError("resolution_date must be on or after onset_date")
        return self


# =============================================================================
# Enrollment Event
# =============================================================================


class EnrollmentEvent(_EventEnvelope):
    """A change in patient enrollment status."""

    event_type: Literal["enrollment_event"] = "enrollment_event"

    # New status the patient transitioned to
    new_status: EnrollmentStatus

    # Optional previous status (None for initial screening)
    previous_status: EnrollmentStatus | None = None

    # Reason for status change (free text, often required for withdrawals)
    reason: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def _validate_withdrawal_has_reason(self) -> EnrollmentEvent:
        """Withdrawal events must include a reason."""
        withdrawal_statuses = {
            EnrollmentStatus.WITHDRAWN_BY_PATIENT,
            EnrollmentStatus.WITHDRAWN_BY_INVESTIGATOR,
            EnrollmentStatus.SCREEN_FAILURE,
        }
        if self.new_status in withdrawal_statuses and not self.reason:
            raise ValueError(f"Status {self.new_status} requires a reason")
        return self


# =============================================================================
# Lab Result
# =============================================================================


class LabResult(_EventEnvelope):
    """A laboratory measurement.

    Includes reference range so downstream consumers can flag out-of-range
    values without needing to look up the analyte separately.
    """

    event_type: Literal["lab_result"] = "lab_result"

    analyte: LabAnalyte
    value: Decimal = Field(..., description="Measured value")
    unit: str = Field(..., min_length=1, max_length=50)

    # Reference range from the testing lab (these vary by lab and patient demographics)
    reference_low: Decimal
    reference_high: Decimal

    # Specimen collection time (often differs from event_timestamp which is when
    # the result was reported)
    specimen_collected_at: datetime

    @field_validator("specimen_collected_at")
    @classmethod
    def _specimen_must_be_utc(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("specimen_collected_at must be timezone-aware (use UTC)")
        return v.astimezone(UTC)

    @model_validator(mode="after")
    def _validate_reference_range_ordered(self) -> LabResult:
        """reference_low must not exceed reference_high."""
        if self.reference_low > self.reference_high:
            raise ValueError("reference_low must be <= reference_high")
        return self

    @property
    def is_out_of_range(self) -> bool:
        """True if the measured value falls outside the reference range."""
        return self.value < self.reference_low or self.value > self.reference_high


# =============================================================================
# Discriminated union — TrialEvent
# =============================================================================
# Pydantic v2's discriminated union: the `event_type` field selects which
# variant to validate against. This means:
#
#   raw = {"event_type": "adverse_event", ...}
#   parsed = TypeAdapter(TrialEvent).validate_python(raw)
#   # parsed is now narrowed to AdverseEvent
#
# The performance benefit is significant: instead of trying every variant
# until one validates, Pydantic looks at event_type and jumps directly to
# the right one.

TrialEvent = Annotated[
    AdverseEvent | EnrollmentEvent | LabResult,
    Field(discriminator="event_type"),
]
"""Union of all trial event types, discriminated by `event_type`."""
