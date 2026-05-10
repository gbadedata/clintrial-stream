"""Type-safe identifiers for trial entities.

We use NewType wrappers around `str` rather than raw strings so the type
checker catches accidentally swapping a PatientId for a StudyId. At runtime
they are still strings — no overhead, no marshalling cost.

Generated identifiers use ULIDs (Universally Unique Lexicographically Sortable
Identifiers) instead of UUIDs because ULIDs:
- Are sortable by creation time (useful for debugging)
- Are URL-safe (no hyphens that need URL-encoding)
- Are still 128-bit globally unique
"""

from __future__ import annotations

import secrets
import time
from typing import NewType

# -----------------------------------------------------------------------------
# Type-safe ID wrappers
# -----------------------------------------------------------------------------
# NewType creates distinct types at type-check time but compiles to the
# underlying type at runtime. mypy will reject:
#     def lookup(p: PatientId) -> Patient: ...
#     lookup(study_id)  # mypy error: expected PatientId, got StudyId

PatientId = NewType("PatientId", str)
"""Identifier for a study participant (e.g. P-12345)."""

SiteId = NewType("SiteId", str)
"""Identifier for a clinical trial site (e.g. SITE-LON-001)."""

StudyId = NewType("StudyId", str)
"""Identifier for a clinical study (e.g. NCT04567890 — real ClinicalTrials.gov format)."""

CorrelationId = NewType("CorrelationId", str)
"""Identifier traced across all log lines for a single event/request."""

EventId = NewType("EventId", str)
"""Identifier for a single trial event."""

# -----------------------------------------------------------------------------
# ID generators
# -----------------------------------------------------------------------------
# We implement a small ULID generator inline rather than depending on a separate
# `python-ulid` package. Keeps the dependency footprint smaller for a portfolio
# project. ULID format: 26 chars, Crockford Base32, sortable by time.

_CROCKFORD_BASE32 = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
"""Crockford Base32 alphabet — excludes I, L, O, U to avoid visual confusion."""


def _generate_ulid() -> str:
    """Generate a ULID: 48-bit timestamp + 80-bit randomness, Crockford Base32-encoded.

    Returns a 26-character string sortable by creation time.
    """
    # 48-bit millisecond timestamp
    ms = int(time.time() * 1000) & ((1 << 48) - 1)

    # 80 bits of cryptographically secure randomness
    random_bits = secrets.randbits(80)

    # Pack into a single 128-bit integer
    value = (ms << 80) | random_bits

    # Encode as Crockford Base32 (5 bits per character → 26 characters for 130 bits)
    out = []
    for _ in range(26):
        out.append(_CROCKFORD_BASE32[value & 0x1F])
        value >>= 5
    return "".join(reversed(out))


def new_event_id() -> EventId:
    """Generate a fresh event ID."""
    return EventId(_generate_ulid())


def new_correlation_id() -> CorrelationId:
    """Generate a fresh correlation ID."""
    return CorrelationId(_generate_ulid())
