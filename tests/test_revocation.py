"""An authorization can be revoked, from a moment forward, never backward.

A `RevocationEvent` names the authorization it ends. It takes effect when it is recorded,
or at a later `effective_at` (a revocation can be scheduled), and from then on the
authorization does not count. It never reaches back: a revocation may not take effect
before the moment the deciding kernel recorded it, so a decision made while the
authorization held stays valid and its lineage still reloads. Only a human can revoke, and
where a registry trusts a named set of humans, only one of them.
"""
from __future__ import annotations

import pytest

from conservation_kernel import (
    Actor, ActorKind, Artifact, AuthorityStatus, AuthorizationEvent, ConservationKernel, EpistemicStatus,
    EvidenceRegistry, OriginStatus, Proposition, RevocationEvent, TransitionKind,
)
from conservation_kernel.errors import InvalidEvent, RootAdmissionError
from conservation_kernel.experiments import build_ground_truth
from test_authorization_windows import _adoption, _adoption_auth, _Clock

T1 = "2026-10-01T00:00:00+00:00"
T2 = "2026-10-02T00:00:00+00:00"
T3 = "2026-10-03T00:00:00+00:00"
T4 = "2026-10-04T00:00:00+00:00"


def _revoke(effective_at=None, *, revocation_id="rev-1", target="auth-adopt", by=None):
    return RevocationEvent(revocation_id=revocation_id, authorization_id=target,
                           revoked_by=by or Actor.human("adopter"), reason="no longer adopted",
                           effective_at=effective_at)


def _kernel(now):
    base, registry = build_ground_truth()
    registry.add_authorization(_adoption_auth())
    clock = _Clock(now)
    k = ConservationKernel(allow_unguarded_roots=True, registry=registry, clock=clock)
    k.register_root(base)
    return k, clock, base, registry


def test_a_revoked_authorization_does_not_count_after_the_revocation():
    k, clock, base, registry = _kernel(T1)
    k.revoke(_revoke())
    clock.now = T2
    output, record = _adoption(registry, base)
    result = k.submit(base, output, record)
    assert not result.accepted and "MISSING_HUMAN_ADOPTION" in {v.code for v in result.violations}


def test_a_decision_made_before_the_revocation_still_reloads_after_it(tmp_path):
    k, clock, base, registry = _kernel(T1)
    output, record = _adoption(registry, base)
    assert k.submit(base, output, record).accepted
    clock.now = T2
    k.revoke(_revoke())
    k.save(tmp_path / "kernel.json")
    restored = ConservationKernel.load(tmp_path / "kernel.json", allow_unguarded_roots=True, clock=_Clock(T3))
    assert restored.reconstruct(output.artifact_id).transformation_ids_in_order == ("tx-adopt",)
    assert [r.revocation_id for r in restored.registry.revocations_of("auth-adopt")] == ["rev-1"]


def test_a_revocation_can_be_scheduled_and_counts_only_from_then():
    k, clock, base, registry = _kernel(T1)
    k.revoke(_revoke(effective_at=T3))
    assert registry.at(T2).authorization("auth-adopt") is not None
    assert registry.at(T3).authorization("auth-adopt") is None


def test_a_revocation_cannot_reach_back_before_it_was_recorded():
    k, clock, *_ = _kernel(T3)
    with pytest.raises(InvalidEvent, match="before it was recorded"):
        k.revoke(_revoke(effective_at=T2))


def test_with_no_time_a_revoked_authorization_does_not_count():
    k, *_ = _kernel(T1)
    k.revoke(_revoke(effective_at=T4))           # not even in effect yet
    assert k.registry.at(None).authorization("auth-adopt") is None


def test_only_a_human_can_revoke():
    with pytest.raises(InvalidEvent, match="human"):
        _revoke(by=Actor.model("helpful-agent"))


def test_where_humans_are_named_only_a_named_one_can_revoke():
    registry = EvidenceRegistry(trusted_humans={"adopter"})
    with pytest.raises(InvalidEvent, match="does not recognise"):
        registry.add_revocation(_revoke(by=Actor.human("stranger")), recorded_at=T1)
    registry.add_revocation(_revoke(), recorded_at=T1)


def test_revoking_an_authorization_the_registry_has_not_seen_yet_still_applies_when_it_arrives():
    registry = EvidenceRegistry()
    registry.add_revocation(_revoke(), recorded_at=T1)
    registry.add_authorization(_adoption_auth())
    assert registry.at(T2).authorization("auth-adopt") is None


def test_a_revocation_id_is_used_once():
    registry = EvidenceRegistry()
    registry.add_revocation(_revoke(), recorded_at=T1)
    with pytest.raises(InvalidEvent, match="duplicate"):
        registry.add_revocation(_revoke(target="auth-other"), recorded_at=T1)


def test_a_registry_with_no_revocations_keeps_its_old_snapshot_shape_and_one_with_them_round_trips():
    registry = EvidenceRegistry()
    registry.add_authorization(_adoption_auth())
    assert "revocations" not in registry.snapshot()
    registry.add_revocation(_revoke(effective_at=T3), recorded_at=T1)
    restored = EvidenceRegistry.restore(registry.snapshot())
    assert restored.at(T2).authorization("auth-adopt") is not None
    assert restored.at(T3).authorization("auth-adopt") is None


def test_a_root_claim_whose_authorization_was_revoked_is_refused():
    registry = EvidenceRegistry()
    registry.add_authorization(AuthorizationEvent(
        authorization_id="auth-root", authorized_by=Actor.human("approver"), subject_id="p-claim",
        transition_kind=TransitionKind.AUTHORITY_ESCALATION, from_value="NONE", to_value="HUMAN_AUTHORIZED",
        reason="approved"))
    clock = _Clock(T1)
    k = ConservationKernel(allow_unguarded_roots=True, registry=registry, clock=clock)
    k.revoke(_revoke(target="auth-root", by=Actor.human("approver")))
    clock.now = T2
    p = Proposition("p-claim", "Deploy to production.", EpistemicStatus.DECISION, OriginStatus.MACHINE_ORIGINATED,
                    authority=AuthorityStatus.HUMAN_AUTHORIZED, authorization_refs=("auth-root",))
    with pytest.raises(RootAdmissionError, match="no authorization for this proposition"):
        k.register_root(Artifact("root-claim", "x", (p,), Actor("bot", ActorKind.SYSTEM)))


def test_a_revocation_round_trips_as_a_dictionary():
    revocation = _revoke(effective_at=T3)
    assert RevocationEvent.from_dict(revocation.to_dict()) == revocation
