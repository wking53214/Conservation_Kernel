"""A trusted human can delegate the power to authorize, within a stated scope.

An authorization is already narrow (one subject, one kind of change, one target value). A
`DelegationEvent` is what carries scope: it lets a named delegate issue authorizations, but
only for the subjects it lists (named one by one, never by pattern), the kinds of change it
lists, and the target values it lists, and only while it is in force (its own window, not
revoked). An authorization issued under a delegation cites it (`under_delegation`) and counts
only while every link of the chain is in force and covers it. A delegate may re-delegate only
if the delegation says so, only to a narrower scope, and only to a capped depth; revoking a
link cuts off everything beneath it. The chain must start at a human the registry trusts.
"""
from __future__ import annotations

import pytest

from conservation_kernel import (
    Actor, AuthorizationEvent, ConservationKernel, DelegationEvent, EvidenceRegistry, OriginStatus, RevocationEvent,
    TransitionKind,
)
from conservation_kernel.errors import InvalidEvent
from conservation_kernel.experiments import build_ground_truth
from conservation_kernel.registry import MAX_DELEGATION_DEPTH
from test_authorization_windows import _adoption, _Clock

SUBJECT = "p-ai-inference"
ADOPT = TransitionKind.HUMAN_ADOPTION
FROM = OriginStatus.MACHINE_ORIGINATED.value
TO = OriginStatus.HUMAN_ADOPTED_MACHINE_OUTPUT.value
T1 = "2026-10-01T00:00:00+00:00"
T2 = "2026-10-02T00:00:00+00:00"
T3 = "2026-10-03T00:00:00+00:00"


def _delegation(delegation_id="del-1", *, by="lead", to="reviewer", subjects=(SUBJECT,), kinds=(ADOPT,),
                values=(TO,), parent=None, may_redelegate=False, **window):
    return DelegationEvent(delegation_id=delegation_id, delegator=Actor.human(by), delegate_id=to,
                           subject_ids=subjects, transition_kinds=kinds, to_values=values, reason="cover the queue",
                           parent_delegation_id=parent, may_redelegate=may_redelegate, **window)


def _auth(*, by="reviewer", under="del-1", subject=SUBJECT, to=TO, auth_id="auth-adopt"):
    return AuthorizationEvent(authorization_id=auth_id, authorized_by=Actor.human(by), subject_id=subject,
                              transition_kind=ADOPT, from_value=FROM, to_value=to, reason="adopted",
                              under_delegation=under)


def _registry(*delegations, auth=None):
    registry = EvidenceRegistry(trusted_humans={"lead"})
    for d in delegations:
        registry.add_delegation(d)
    if auth is not None:
        registry.add_authorization(auth)
    return registry


# ---------------------------------------------------------------- scope

def test_an_authorization_inside_the_delegated_scope_counts():
    registry = _registry(_delegation(), auth=_auth())
    assert registry.at(T1).authorization("auth-adopt") is not None


def test_a_delegated_authorization_works_end_to_end_through_the_kernel():
    base, registry = build_ground_truth()
    registry.trusted_humans = frozenset({"lead", "researcher"})      # "researcher" signed the fixture's own
    registry.add_delegation(_delegation())
    registry.add_authorization(_auth())
    k = ConservationKernel(allow_unguarded_roots=True, registry=registry, clock=_Clock(T1), allow_unguarded_evidence=True)
    k.register_root(base)
    output, record = _adoption(registry, base)
    assert k.submit(base, output, record).accepted


@pytest.mark.parametrize("narrowed", [
    {"subjects": ("p-somewhere-else",)},
    {"kinds": (TransitionKind.AUTHORITY_ESCALATION,)},
    {"values": ("SOMETHING_ELSE",)},
])
def test_an_authorization_outside_the_delegated_scope_does_not_count(narrowed):
    registry = _registry(_delegation(**narrowed), auth=_auth())
    assert registry.at(T1).authorization("auth-adopt") is None


def test_a_delegation_names_its_subjects_and_cannot_use_a_wildcard():
    with pytest.raises(InvalidEvent):
        _delegation(subjects=())
    registry = _registry(_delegation(subjects=("*",)), auth=_auth())
    assert registry.at(T1).authorization("auth-adopt") is None       # "*" is just a subject id that matches nothing else


# ---------------------------------------------------------------- who

def test_a_delegation_must_start_at_a_trusted_human():
    with pytest.raises(InvalidEvent, match="does not recognise"):
        _registry(_delegation(by="stranger"))


def test_an_authorization_can_only_cite_a_delegation_to_its_own_author():
    with pytest.raises(InvalidEvent, match="delegated to"):
        _registry(_delegation(to="someone-else"), auth=_auth())


def test_an_authorization_cannot_cite_a_delegation_the_registry_does_not_hold():
    with pytest.raises(InvalidEvent, match="does not hold"):
        _registry(auth=_auth(under="del-missing"))


def test_an_untrusted_human_still_cannot_authorize_without_a_delegation():
    with pytest.raises(InvalidEvent, match="does not recognise"):
        _registry(auth=_auth(under=None))


def test_ids_are_unique_across_authorizations_and_delegations():
    registry = _registry(_delegation(), auth=_auth())
    with pytest.raises(InvalidEvent, match="duplicate"):
        registry.add_delegation(_delegation(delegation_id="auth-adopt"))
    with pytest.raises(InvalidEvent, match="duplicate"):
        registry.add_authorization(_auth(auth_id="del-1"))


# ---------------------------------------------------------------- time and revocation

def test_an_authorization_stops_counting_when_its_delegation_ends():
    registry = _registry(_delegation(valid_until=T2), auth=_auth())
    assert registry.at(T1).authorization("auth-adopt") is not None
    assert registry.at(T2).authorization("auth-adopt") is None


def test_revoking_the_delegation_cuts_off_what_was_issued_under_it():
    registry = _registry(_delegation(), auth=_auth())
    registry.add_revocation(RevocationEvent(revocation_id="rev-d", authorization_id="del-1",
                                            revoked_by=Actor.human("lead"), reason="role ended"), recorded_at=T2)
    assert registry.at(T1).authorization("auth-adopt") is not None
    assert registry.at(T3).authorization("auth-adopt") is None


def test_with_no_time_an_open_ended_chain_counts_and_a_windowed_one_does_not():
    assert _registry(_delegation(), auth=_auth()).at(None).authorization("auth-adopt") is not None
    assert _registry(_delegation(valid_until=T3), auth=_auth()).at(None).authorization("auth-adopt") is None


def test_a_lineage_accepted_under_a_delegation_still_reloads_after_the_delegation_is_revoked(tmp_path):
    base, registry = build_ground_truth()
    registry.trusted_humans = frozenset({"lead", "researcher"})      # "researcher" signed the fixture's own
    registry.add_delegation(_delegation())
    registry.add_authorization(_auth())
    clock = _Clock(T1)
    k = ConservationKernel(allow_unguarded_roots=True, registry=registry, clock=clock, allow_unguarded_evidence=True)
    k.register_root(base)
    output, record = _adoption(registry, base)
    assert k.submit(base, output, record).accepted
    clock.now = T2
    k.revoke(RevocationEvent(revocation_id="rev-d", authorization_id="del-1", revoked_by=Actor.human("lead"),
                             reason="role ended"))
    k.save(tmp_path / "kernel.json")
    restored = ConservationKernel.load(tmp_path / "kernel.json", allow_unguarded_roots=True, trusted_humans={"lead", "researcher"},
                                       clock=_Clock(T3), allow_unguarded_evidence=True)
    assert restored.reconstruct(output.artifact_id).transformation_ids_in_order == ("tx-adopt",)
    assert restored.registry.at(T3).authorization("auth-adopt") is None


# ---------------------------------------------------------------- re-delegation

def _redelegated(**child):
    parent = _delegation(may_redelegate=True, subjects=(SUBJECT, "p-other"))
    defaults = dict(delegation_id="del-2", by="reviewer", to="deputy", parent="del-1")
    return parent, _delegation(**{**defaults, **child})


def test_a_delegate_may_re_delegate_a_narrower_scope_when_allowed():
    parent, child = _redelegated()
    registry = _registry(parent, child, auth=_auth(by="deputy", under="del-2"))
    assert registry.at(T1).authorization("auth-adopt") is not None


def test_re_delegation_needs_permission():
    parent = _delegation()                                      # may_redelegate=False
    child = _delegation(delegation_id="del-2", by="reviewer", to="deputy", parent="del-1")
    with pytest.raises(InvalidEvent, match="re-delegat"):
        _registry(parent, child)


def test_re_delegation_can_only_narrow():
    parent, child = _redelegated(subjects=(SUBJECT, "p-not-in-parent"))
    with pytest.raises(InvalidEvent, match="wider"):
        _registry(parent, child)


def test_only_the_delegate_can_re_delegate():
    parent, child = _redelegated(by="someone-else")
    with pytest.raises(InvalidEvent, match="delegated to"):
        _registry(parent, child)


def test_revoking_a_parent_cuts_off_the_whole_chain_beneath_it():
    parent, child = _redelegated()
    registry = _registry(parent, child, auth=_auth(by="deputy", under="del-2"))
    registry.add_revocation(RevocationEvent(revocation_id="rev-p", authorization_id="del-1",
                                            revoked_by=Actor.human("lead"), reason="role ended"), recorded_at=T2)
    assert registry.at(T3).authorization("auth-adopt") is None


def test_a_chain_cannot_be_deeper_than_the_cap():
    registry = EvidenceRegistry(trusted_humans={"h0"})
    registry.add_delegation(_delegation("d1", by="h0", to="h1", may_redelegate=True))
    for depth in range(2, MAX_DELEGATION_DEPTH + 1):
        registry.add_delegation(_delegation(f"d{depth}", by=f"h{depth - 1}", to=f"h{depth}", parent=f"d{depth - 1}",
                                            may_redelegate=True))
    with pytest.raises(InvalidEvent, match="deeper"):
        registry.add_delegation(_delegation("d-too-deep", by=f"h{MAX_DELEGATION_DEPTH}", to="hx",
                                            parent=f"d{MAX_DELEGATION_DEPTH}"))


# ---------------------------------------------------------------- shape

def test_delegations_round_trip_and_a_registry_without_them_keeps_its_old_shape():
    assert "delegations" not in EvidenceRegistry().snapshot()
    assert "under_delegation" not in _auth(under=None).to_dict()
    parent, child = _redelegated(valid_until=T3)
    registry = _registry(parent, child, auth=_auth(by="deputy", under="del-2"))
    restored = EvidenceRegistry.restore(registry.snapshot(), trusted_humans={"lead"})
    assert restored.at(T1).authorization("auth-adopt") is not None
    assert restored.at(T3).authorization("auth-adopt") is None
    assert DelegationEvent.from_dict(child.to_dict()) == child


def test_a_registry_that_requires_an_end_refuses_an_open_ended_delegation():
    strict = EvidenceRegistry(trusted_humans={"lead"}, require_bounded=True)
    with pytest.raises(InvalidEvent, match="end"):
        strict.add_delegation(_delegation())
    strict.add_delegation(_delegation(valid_until=T3))
