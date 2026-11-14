"""Authorizing and restoring refuse unless the deployer has said something, or opted out out loud.

A registry with no `trusted_humans` cannot tell a human from an actor that labels itself one, so it refuses every
authorization and delegation unless `allow_untrusted_humans=True`. A snapshot holding roots is not restored into a
kernel with no root guard unless `allow_unguarded_restore=True`.
"""
from __future__ import annotations

import pytest

from conservation_kernel import (
    Actor, ActorKind, Artifact, AuthorizationEvent, ConservationKernel, ConservationLedger, DelegationEvent,
    EpistemicStatus, EvidenceRegistry, OriginStatus, Proposition, TransitionKind,
)
from conservation_kernel.errors import InvalidEvent, UnguardedKernelError


def _authorization(authorization_id="auth-1"):
    return AuthorizationEvent(
        authorization_id=authorization_id, authorized_by=Actor.human("reviewer-1"), subject_id="p-1",
        transition_kind=TransitionKind.AUTHORITY_ESCALATION, from_value="NONE", to_value="HUMAN_AUTHORIZED",
        reason="test")


def _delegation():
    return DelegationEvent(
        delegation_id="del-1", delegator=Actor.human("reviewer-1"), delegate_id="deputy-1", subject_ids=("p-1",),
        transition_kinds=(TransitionKind.AUTHORITY_ESCALATION,), to_values=("HUMAN_AUTHORIZED",), reason="test")


def _rooted_snapshot():
    kernel = ConservationKernel(allow_unguarded_roots=True, allow_unguarded_evidence=True)
    prop = Proposition("p-1", "Sensor reading 42.", EpistemicStatus.INFERENCE, OriginStatus.MACHINE_ORIGINATED)
    kernel.register_root(Artifact("root-1", "sensor", (prop,), Actor("sensor", ActorKind.SYSTEM)))
    return kernel.snapshot()


def test_authorization_is_refused_without_trusted_humans():
    with pytest.raises(InvalidEvent, match="no trusted_humans"):
        EvidenceRegistry().add_authorization(_authorization())


def test_delegation_is_refused_without_trusted_humans():
    with pytest.raises(InvalidEvent, match="no trusted_humans"):
        EvidenceRegistry().add_delegation(_delegation())


def test_authorization_is_allowed_from_a_trusted_human():
    registry = EvidenceRegistry(trusted_humans={"reviewer-1"})
    registry.add_authorization(_authorization())
    registry.add_delegation(_delegation())
    assert registry.authorization("auth-1") is not None


def test_authorization_is_allowed_with_explicit_allow_untrusted_humans():
    registry = EvidenceRegistry(allow_untrusted_humans=True)
    registry.add_authorization(_authorization())
    registry.add_delegation(_delegation())
    assert registry.authorization("auth-1") is not None


def test_a_kernel_built_with_allow_untrusted_humans_authorizes_and_one_without_refuses():
    ConservationKernel(allow_unguarded_roots=True, allow_unguarded_evidence=True,
                       allow_untrusted_humans=True).registry.add_authorization(_authorization())
    with pytest.raises(InvalidEvent):
        ConservationKernel(allow_unguarded_roots=True, allow_unguarded_evidence=True).registry.add_authorization(
            _authorization())


def test_restore_of_a_rooted_snapshot_is_refused_without_a_guard():
    snapshot = _rooted_snapshot()
    with pytest.raises(UnguardedKernelError, match="allow_unguarded_restore"):
        ConservationKernel.from_snapshot(snapshot, allow_unguarded_roots=True, allow_unguarded_evidence=True)
    with pytest.raises(UnguardedKernelError):
        ConservationLedger.restore(snapshot["ledger"])


def test_restore_of_a_rooted_snapshot_is_allowed_with_a_guard():
    # The guard is required to be configured; it is not run on the restored roots, so one that refuses is not asked.
    restored = ConservationKernel.from_snapshot(_rooted_snapshot(), root_guard=lambda artifact: False,
                                                allow_unguarded_evidence=True)
    assert restored.ledger.artifact("root-1")


def test_restore_of_a_rooted_snapshot_is_allowed_with_allow_unguarded_restore():
    restored = ConservationKernel.from_snapshot(_rooted_snapshot(), allow_unguarded_restore=True,
                                                allow_unguarded_roots=True, allow_unguarded_evidence=True)
    assert restored.ledger.artifact("root-1")
    assert ConservationLedger.restore(_rooted_snapshot()["ledger"], allow_unguarded_restore=True).artifact("root-1")


def test_restore_of_a_snapshot_with_no_roots_needs_no_guard_or_flag():
    empty = ConservationKernel(allow_unguarded_roots=True, allow_unguarded_evidence=True).snapshot()
    ConservationKernel.from_snapshot(empty, allow_unguarded_roots=True, allow_unguarded_evidence=True)
