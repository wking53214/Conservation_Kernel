"""Backlog item 4: nobody who records a revocation chooses the time it is recorded at.

`EvidenceRegistry.add_revocation` used to take `recorded_at` from the caller, so a revocation could be recorded in the
past and reach back over decisions already made. The time now comes from the registry's own clock, which a kernel
supplies, and the old parameter is gone from the public method.
"""
from __future__ import annotations

import pytest

from conservation_kernel import Actor, ConservationKernel, EvidenceRegistry, RevocationEvent
from conservation_kernel.errors import InvalidEvent

NOW = "2026-11-01T00:00:00+00:00"
LONG_AGO = "2001-01-01T00:00:00+00:00"


def _revoke(revocation_id="rev-1"):
    return RevocationEvent(revocation_id=revocation_id, authorization_id="auth-1", revoked_by=Actor.human("adopter"),
                           reason="no longer adopted")


def _kernel(registry=None):
    registry = registry or EvidenceRegistry(allow_untrusted_humans=True)
    return ConservationKernel(registry=registry, clock=lambda: NOW, allow_unguarded_roots=True,
                              allow_unguarded_evidence=True)


def test_the_public_method_no_longer_accepts_a_recording_time():
    registry = EvidenceRegistry(allow_untrusted_humans=True, clock=lambda: NOW)
    with pytest.raises(TypeError):
        registry.add_revocation(_revoke(), recorded_at=LONG_AGO)


def test_a_registry_with_no_clock_refuses_to_record_a_revocation():
    registry = EvidenceRegistry(allow_untrusted_humans=True)
    with pytest.raises(InvalidEvent, match="no clock"):
        registry.add_revocation(_revoke())
    assert registry.revocations_of("auth-1") == ()


def test_the_registrys_own_clock_stamps_the_revocation():
    registry = EvidenceRegistry(allow_untrusted_humans=True, clock=lambda: NOW)
    registry.add_revocation(_revoke())
    assert registry._revocations["rev-1"][1] == NOW


def test_a_kernel_stamps_revocations_made_straight_on_its_registry_with_its_own_clock():
    for registry in (None, EvidenceRegistry(allow_untrusted_humans=True)):
        kernel = _kernel(registry)
        kernel.registry.add_revocation(_revoke())
        assert kernel.registry._revocations["rev-1"][1] == NOW


def test_a_registry_keeps_its_own_clock_when_a_kernel_adopts_it():
    registry = EvidenceRegistry(allow_untrusted_humans=True, clock=lambda: "2026-12-01T00:00:00+00:00")
    _kernel(registry).registry.add_revocation(_revoke())
    assert registry._revocations["rev-1"][1] == "2026-12-01T00:00:00+00:00"


def test_kernel_revoke_and_a_snapshot_round_trip_keep_the_recorded_time():
    kernel = _kernel()
    kernel.revoke(_revoke())
    restored = ConservationKernel.from_snapshot(kernel.snapshot(), allow_unguarded_restore=True,
                                                allow_untrusted_humans=True, allow_unguarded_roots=True,
                                                allow_unguarded_evidence=True, clock=lambda: NOW)
    assert restored.registry._revocations["rev-1"][1] == NOW
