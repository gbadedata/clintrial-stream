"""Domain layer — pure business logic, no AWS, no I/O.

This package defines the core concepts of a clinical trial event stream:

- Trial events: adverse events, enrollment changes, lab results
- Reference data: organisations, sites, patients, drugs
- Validation: invariants enforced at the boundary by Pydantic

By keeping this layer free of AWS imports, we get:
- Fast unit tests (no boto3 mocking required)
- Reusability across producers, consumers, and the API
- Clear separation between "what" (domain) and "how" (infrastructure)
"""

from clintrial.domain.events import (
    AdverseEvent,
    EnrollmentEvent,
    LabResult,
    TrialEvent,
)
from clintrial.domain.identifiers import (
    PatientId,
    SiteId,
    StudyId,
    new_correlation_id,
    new_event_id,
)

__all__ = [
    "AdverseEvent",
    "EnrollmentEvent",
    "LabResult",
    "PatientId",
    "SiteId",
    "StudyId",
    "TrialEvent",
    "new_correlation_id",
    "new_event_id",
]
