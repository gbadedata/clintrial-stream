"""Tests for clintrial.domain.identifiers."""

from __future__ import annotations

import re

import pytest

from clintrial.domain.identifiers import (
    new_correlation_id,
    new_event_id,
)

pytestmark = pytest.mark.unit

# Crockford Base32: digits + letters minus I, L, O, U
_CROCKFORD_PATTERN = re.compile(r"^[0-9A-HJKMNP-TV-Z]{26}$")


class TestUlidGeneration:
    def test_event_id_is_26_chars_crockford_base32(self) -> None:
        eid = new_event_id()
        assert _CROCKFORD_PATTERN.match(eid), f"{eid} is not a valid ULID format"

    def test_correlation_id_is_26_chars_crockford_base32(self) -> None:
        cid = new_correlation_id()
        assert _CROCKFORD_PATTERN.match(cid), f"{cid} is not a valid ULID format"

    def test_consecutive_ids_are_unique(self) -> None:
        ids = {new_event_id() for _ in range(1000)}
        assert len(ids) == 1000, "Expected 1000 unique IDs, found collisions"

    def test_consecutive_ids_are_sortable_by_time(self) -> None:
        # ULIDs encode the timestamp in the leading 10 chars (48 bits, base32).
        # Earlier IDs should sort lexicographically before later ones.
        first = new_event_id()
        # Force a tiny delay so timestamps differ
        import time

        time.sleep(0.002)
        second = new_event_id()
        assert first < second, f"Expected {first} < {second} (chronological order)"
