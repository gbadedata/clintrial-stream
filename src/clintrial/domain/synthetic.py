"""Synthetic trial event generator.

Produces realistic-looking trial events for demos and load testing. Uses
deterministic randomness (seedable) so the same seed produces the same
sequence of events — essential for reproducible benchmarks.

Realism is key. An interviewer reading the generated data should see:
- Real-sounding patient IDs (P-12345)
- ClinicalTrials.gov-format study IDs (NCT followed by 8 digits)
- Real medical adverse event terms
- Lab values within physiologic ranges
- Plausible age/sex distributions
"""

from __future__ import annotations

import random
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Literal

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

# =============================================================================
# Reference data — small slices of real medical vocabularies
# =============================================================================

# Real ClinicalTrials.gov-format study IDs (prefix + 8 digits).
# These are made up for the demo but follow the real format.
SAMPLE_STUDIES: list[StudyId] = [
    StudyId("NCT04567890"),  # synthetic — would be e.g. "Drug X for Type 2 Diabetes"
    StudyId("NCT05123456"),  # synthetic — would be e.g. "Vaccine Y safety"
    StudyId("NCT05789012"),  # synthetic — would be e.g. "Cancer Z phase 2"
]

# Real-format site IDs (location code + sequence number)
SAMPLE_SITES: list[SiteId] = [
    SiteId("SITE-LON-001"),  # London
    SiteId("SITE-LON-002"),
    SiteId("SITE-CAM-001"),  # Cambridge
    SiteId("SITE-EDI-001"),  # Edinburgh
    SiteId("SITE-MAN-001"),  # Manchester
    SiteId("SITE-DUB-001"),  # Dublin
]

# Real adverse event preferred terms — a small slice of MedDRA. These are
# the most common AEs reported in oncology and cardiovascular trials.
SAMPLE_AE_TERMS: list[str] = [
    "Nausea",
    "Vomiting",
    "Diarrhoea",
    "Fatigue",
    "Headache",
    "Pyrexia",  # fever
    "Anaemia",
    "Neutropenia",
    "Thrombocytopenia",
    "Alanine aminotransferase increased",
    "Aspartate aminotransferase increased",
    "Hypertension",
    "Hypotension",
    "Rash",
    "Pruritus",  # itching
    "Dyspnoea",  # shortness of breath
    "Cough",
    "Constipation",
    "Decreased appetite",
    "Insomnia",
]

# Common drug names (DCI/INN format — international nonproprietary names)
SAMPLE_DRUGS: list[str] = [
    "Investigational product A",
    "Pembrolizumab",
    "Atezolizumab",
    "Trastuzumab",
    "Carboplatin",
    "Paclitaxel",
    "Placebo",
]

# Lab analyte reference ranges (adult, mixed sex, broadly representative).
# Real ranges depend on the lab and patient demographics — production systems
# pull these from a clinical database. Values are (low, high, unit).
ANALYTE_RANGES: dict[LabAnalyte, tuple[Decimal, Decimal, str]] = {
    LabAnalyte.HAEMOGLOBIN: (Decimal("120"), Decimal("160"), "g/L"),
    LabAnalyte.PLATELETS: (Decimal("150"), Decimal("400"), "10^9/L"),
    LabAnalyte.WHITE_BLOOD_CELLS: (Decimal("4.0"), Decimal("11.0"), "10^9/L"),
    LabAnalyte.NEUTROPHILS: (Decimal("2.0"), Decimal("7.5"), "10^9/L"),
    LabAnalyte.ALANINE_AMINOTRANSFERASE: (Decimal("7"), Decimal("56"), "U/L"),
    LabAnalyte.ASPARTATE_AMINOTRANSFERASE: (Decimal("10"), Decimal("40"), "U/L"),
    LabAnalyte.CREATININE: (Decimal("60"), Decimal("110"), "umol/L"),
    LabAnalyte.GLUCOSE: (Decimal("3.9"), Decimal("5.5"), "mmol/L"),
    LabAnalyte.SODIUM: (Decimal("135"), Decimal("145"), "mmol/L"),
    LabAnalyte.POTASSIUM: (Decimal("3.5"), Decimal("5.0"), "mmol/L"),
}


# =============================================================================
# Generator
# =============================================================================


class TrialEventGenerator:
    """Produces synthetic trial events.

    Args:
        seed: Random seed. Same seed produces identical event sequences —
            critical for reproducible tests and demos.
        n_patients: How many distinct patients to simulate. Each patient_id
            is reused across events to create realistic per-patient histories.
        out_of_range_lab_probability: Probability a generated lab result will
            fall outside the reference range. Default 0.1 produces enough
            "interesting" results to test downstream filtering without being
            unrealistic.
        serious_ae_probability: Probability an adverse event is "serious"
            (triggering regulatory reporting). Default 0.05 — real trials
            see roughly 5-10% serious AEs.
    """

    def __init__(
        self,
        seed: int = 42,
        n_patients: int = 50,
        out_of_range_lab_probability: float = 0.10,
        serious_ae_probability: float = 0.05,
    ) -> None:
        self._rng = random.Random(seed)
        self._n_patients = n_patients
        self._out_of_range_prob = out_of_range_lab_probability
        self._serious_ae_prob = serious_ae_probability

        # Pre-generate the patient pool so events refer to the same patients
        self._patients: list[PatientId] = [
            PatientId(f"P-{10000 + i:05d}") for i in range(n_patients)
        ]

    # -------------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------------

    def next_event(
        self,
        kind: Literal["adverse_event", "enrollment_event", "lab_result"] | None = None,
    ) -> TrialEvent:
        """Produce a single random event.

        Args:
            kind: If specified, generate that exact event type. If None,
                pick randomly with weighting that approximates real trial
                ratios (lab results dominate).
        """
        if kind is None:
            kind = self._rng.choices(  # type: ignore[assignment]
                population=["adverse_event", "enrollment_event", "lab_result"],
                weights=[0.10, 0.05, 0.85],
                k=1,
            )[0]

        if kind == "adverse_event":
            return self._make_adverse_event()
        if kind == "enrollment_event":
            return self._make_enrollment_event()
        if kind == "lab_result":
            return self._make_lab_result()
        raise ValueError(f"Unknown event kind: {kind}")

    def stream(self, total_events: int) -> list[TrialEvent]:
        """Generate a fixed-size batch of events."""
        return [self.next_event() for _ in range(total_events)]

    # -------------------------------------------------------------------------
    # Per-event-type generators
    # -------------------------------------------------------------------------

    def _make_adverse_event(self) -> AdverseEvent:
        is_serious = self._rng.random() < self._serious_ae_prob

        # Severity grade — weighted toward milder events
        severity = self._rng.choices(
            population=list(AdverseEventSeverity),
            weights=[0.40, 0.30, 0.20, 0.08, 0.02],
            k=1,
        )[0]

        # Build seriousness criteria appropriately
        seriousness_criteria: list[SeriousnessCriterion] = []
        outcome = AdverseEventOutcome.RECOVERED

        if severity == AdverseEventSeverity.GRADE_5_DEATH:
            # Grade 5 forces death + fatal outcome (model_validator enforces this)
            is_serious = True
            seriousness_criteria = [SeriousnessCriterion.DEATH]
            outcome = AdverseEventOutcome.FATAL
        elif is_serious:
            # Pick 1-2 random seriousness criteria (excluding death for non-fatal)
            non_death_criteria = [
                c for c in SeriousnessCriterion if c != SeriousnessCriterion.DEATH
            ]
            n_criteria = self._rng.randint(1, 2)
            seriousness_criteria = self._rng.sample(non_death_criteria, n_criteria)
            outcome = self._rng.choice(
                [
                    AdverseEventOutcome.RECOVERED,
                    AdverseEventOutcome.RECOVERING,
                    AdverseEventOutcome.NOT_RECOVERED,
                ]
            )

        # Onset 0-30 days ago
        onset = datetime.now(UTC) - timedelta(days=self._rng.randint(0, 30))

        # Resolution: 60% have resolved, 40% still ongoing
        resolution: datetime | None = None
        if self._rng.random() < 0.60:
            resolution = onset + timedelta(days=self._rng.randint(0, 14))

        return AdverseEvent(
            study_id=self._rng.choice(SAMPLE_STUDIES),
            site_id=self._rng.choice(SAMPLE_SITES),
            patient_id=self._rng.choice(self._patients),
            event_timestamp=datetime.now(UTC),
            preferred_term=self._rng.choice(SAMPLE_AE_TERMS),
            severity=severity,
            is_serious=is_serious,
            seriousness_criteria=seriousness_criteria,
            outcome=outcome,
            onset_date=onset,
            resolution_date=resolution,
            suspected_drug=self._rng.choice(SAMPLE_DRUGS),
        )

    def _make_enrollment_event(self) -> EnrollmentEvent:
        new_status = self._rng.choice(list(EnrollmentStatus))

        # Withdrawal events must have a reason; provide one
        reason = None
        if new_status in {
            EnrollmentStatus.WITHDRAWN_BY_PATIENT,
            EnrollmentStatus.WITHDRAWN_BY_INVESTIGATOR,
            EnrollmentStatus.SCREEN_FAILURE,
        }:
            reasons = [
                "Patient request",
                "Adverse event",
                "Protocol deviation",
                "Lost to follow-up",
                "Inclusion criteria not met",
                "Investigator decision",
            ]
            reason = self._rng.choice(reasons)

        return EnrollmentEvent(
            study_id=self._rng.choice(SAMPLE_STUDIES),
            site_id=self._rng.choice(SAMPLE_SITES),
            patient_id=self._rng.choice(self._patients),
            event_timestamp=datetime.now(UTC),
            new_status=new_status,
            previous_status=None,
            reason=reason,
        )

    def _make_lab_result(self) -> LabResult:
        analyte = self._rng.choice(list(LabAnalyte))
        ref_low, ref_high, unit = ANALYTE_RANGES[analyte]

        # Decide if this result should be out of range
        if self._rng.random() < self._out_of_range_prob:
            # Out of range — pick low or high direction
            if self._rng.random() < 0.5:
                # Below reference (e.g. 50-95% of low bound)
                value = ref_low * Decimal(str(self._rng.uniform(0.50, 0.95)))
            else:
                # Above reference (e.g. 105-200% of high bound)
                value = ref_high * Decimal(str(self._rng.uniform(1.05, 2.00)))
        else:
            # In range — uniform between low and high
            value_float = self._rng.uniform(float(ref_low), float(ref_high))
            value = Decimal(str(round(value_float, 2)))

        # Specimen collected 0-4 hours before reporting
        specimen_time = datetime.now(UTC) - timedelta(hours=self._rng.uniform(0, 4))

        return LabResult(
            study_id=self._rng.choice(SAMPLE_STUDIES),
            site_id=self._rng.choice(SAMPLE_SITES),
            patient_id=self._rng.choice(self._patients),
            event_timestamp=datetime.now(UTC),
            analyte=analyte,
            value=value.quantize(Decimal("0.01")),
            unit=unit,
            reference_low=ref_low,
            reference_high=ref_high,
            specimen_collected_at=specimen_time,
        )
