"""Holes an independent adversarial review found in the authority lifecycle, as regression tests.

1. Re-using a transformation id after a window closed moved that transformation's decision
   time to the later attempt (the newest accepted report), so a reload failed.
2. History with no stamp was judged as of every reload, so a revocation recorded later still
   reached back over it.
3. A delegated authorization for subject X let its holder create any number of new
   propositions with arbitrary ids, because a new proposition accepts an authorization about
   any of its parents. Delegated power now reaches only the subjects the delegation names.
4. The CNS gate judged with no time, so it refused what the kernel accepted. It can now be
   handed the same clock.
5. A custom verifier receiving the time-bound view lost the registry's read-only settings.
6. The kernel stored whatever its clock returned, and a reload trusted stamps from the future.
"""
from __future__ import annotations

import json

import pytest

from conservation_kernel import (
    Actor, ActorKind, Artifact, AuthorityStatus, AuthorizationEvent, ConservationKernel, DeclaredChange,
    DelegationEvent, Dimension, EpistemicStatus, EvidenceRegistry, IndependentVerifier, OriginStatus, Proposition,
    RevocationEvent, TransformationRecord, TransitionKind,
)
from conservation_kernel.errors import InvalidEvent, LedgerError, SnapshotIntegrityError
from conservation_kernel.experiments import build_ground_truth
from conservation_kernel.model import _digest, canonical_json
from test_authorization_windows import _adoption, _adoption_auth, _Clock

INSIDE = "2026-10-15T12:00:00+00:00"
CLOSES = "2026-11-01T00:00:00+00:00"
AFTER = "2026-11-02T00:00:00+00:00"
LATER = "2026-11-03T00:00:00+00:00"

def _adopted_kernel(clock, **window):
    base, registry = build_ground_truth()
    registry.add_authorization(_adoption_auth(**window))
    k = ConservationKernel(allow_unguarded_roots=True, registry=registry, clock=clock, allow_unguarded_evidence=True)
    k.register_root(base)
    output, record = _adoption(registry, base)
    assert k.submit(base, output, record).accepted
    return k, base, output, record

# ---------------------------------------------------------------- 1. a re-used id cannot move the decision time

def test_reusing_a_transformation_id_later_does_not_move_its_decision_time(tmp_path):
    clock = _Clock(INSIDE)
    k, base, output, record = _adopted_kernel(clock, valid_until=CLOSES)
    clock.now = AFTER
    noop = Artifact(artifact_id="noop", content=base.content, propositions=base.propositions, producer=base.producer,
                    parent_artifact_ids=(base.artifact_id,), version=base.version + 1,
                    functional_contract=base.functional_contract)
    replay = TransformationRecord(transformation_id="tx-adopt", input_artifact_ids=(base.artifact_id,),
                                  output_artifact_id="noop", transformer=noop.producer, transformation_type="NOOP",
                                  declared_changes=(), input_hashes=(base.artifact_digest,),
                                  output_hash=noop.artifact_digest, reason="noop")
    with pytest.raises(LedgerError, match="duplicate transformation"):
        k.submit(base, noop, replay)                       # verified and accepted; the ledger refuses the reused id
    assert k.ledger.verified_at("tx-adopt") == INSIDE
    k.save(tmp_path / "kernel.json")
    restored = ConservationKernel.load(tmp_path / "kernel.json", allow_unguarded_roots=True, clock=_Clock(LATER), allow_unguarded_evidence=True)
    assert restored.ledger.verified_at("tx-adopt") == INSIDE

# ---------------------------------------------------------------- 2. unstamped history is stamped once, on first reload

def test_history_from_before_stamps_is_stamped_on_first_reload_so_a_later_revocation_cannot_reach_it(tmp_path):
    k, *_ = _adopted_kernel(_Clock(INSIDE))
    body = k.snapshot()
    body.pop("snapshot_digest")
    for name in ("root_admitted_at", "transformation_verified_at"):
        body["ledger"].pop(name, None)
    for report in body["ledger"]["reports"]:
        report.pop("verified_at", None)
    body["snapshot_digest"] = _digest(canonical_json(body))
    old = tmp_path / "old.json"
    old.write_text(json.dumps(body))

    first = ConservationKernel.load(old, allow_unguarded_roots=True, clock=_Clock(AFTER), allow_unguarded_evidence=True)
    assert first.ledger.verified_at("tx-adopt") == AFTER          # judged and stamped as of this reload
    later = _Clock(LATER)
    first.clock = later
    first.revoke(RevocationEvent(revocation_id="rev-1", authorization_id="auth-adopt",
                                 revoked_by=Actor.human("adopter"), reason="no longer adopted"))
    first.save(tmp_path / "after.json")
    again = ConservationKernel.load(tmp_path / "after.json", allow_unguarded_roots=True, clock=_Clock(LATER), allow_unguarded_evidence=True)
    assert again.reconstruct("artifact-ground-truth-adopted").transformation_ids_in_order == ("tx-adopt",)

# ---------------------------------------------------------------- 3. delegated power reaches only named subjects

def test_a_delegated_authorization_cannot_authorize_new_propositions_derived_from_its_subject():
    base, registry = build_ground_truth()
    parent = "p-ai-inference"
    registry.trusted_humans = frozenset({"lead", "researcher"})
    registry.add_delegation(DelegationEvent(
        delegation_id="del-1", delegator=Actor.human("lead"), delegate_id="reviewer", subject_ids=(parent,),
        transition_kinds=(TransitionKind.AUTHORITY_ESCALATION,), to_values=(AuthorityStatus.HUMAN_AUTHORIZED.value,),
        reason="cover"))
    registry.add_authorization(AuthorizationEvent(
        authorization_id="auth-del", authorized_by=Actor.human("reviewer"), subject_id=parent,
        transition_kind=TransitionKind.AUTHORITY_ESCALATION, from_value="NONE",
        to_value=AuthorityStatus.HUMAN_AUTHORIZED.value, reason="ok", under_delegation="del-1"))
    child = Proposition("p-child", "Something the delegate wrote.", EpistemicStatus.DECISION,
                        OriginStatus.MACHINE_ORIGINATED, authority=AuthorityStatus.HUMAN_AUTHORIZED,
                        authorization_refs=("auth-del",), parent_proposition_ids=(parent,), derivation_method="rule")
    output = Artifact(f"{base.artifact_id}-child", base.content, (*base.propositions, child),
                      Actor.model("transformer"), parent_artifact_ids=(base.artifact_id,), version=base.version + 1,
                      functional_contract=base.functional_contract)
    record = TransformationRecord(
        transformation_id="tx-child", input_artifact_ids=(base.artifact_id,), output_artifact_id=output.artifact_id,
        transformer=output.producer, transformation_type="DERIVE",
        declared_changes=(DeclaredChange("p-child", Dimension.LINEAGE, "absent", "present", "new",
                                         TransitionKind.DERIVATION),),
        input_hashes=(base.artifact_digest,), output_hash=output.artifact_digest, authorization_refs=("auth-del",),
        reason="test")
    result = IndependentVerifier().verify(base, output, record, registry.at(INSIDE))
    assert "NEW_AUTHORITY_UNVERIFIED" in {v.code for v in result.violations}

# ---------------------------------------------------------------- 4. the gate can share the kernel's clock

def test_the_cns_gate_handed_the_kernels_clock_agrees_with_the_kernel():
    pytest.importorskip("cns.gate")
    from conservation_kernel.cns_connector import verify_to_cns
    base, registry = build_ground_truth()
    registry.add_authorization(_adoption_auth(valid_until=CLOSES))
    output, record = _adoption(registry, base)
    assert verify_to_cns(base, output, record, registry, clock=_Clock(INSIDE)).outcome.value == "pass"
    assert verify_to_cns(base, output, record, registry, clock=_Clock(AFTER)).outcome.value != "pass"

# ---------------------------------------------------------------- 5. the view keeps the registry's settings readable

def test_the_time_bound_view_still_shows_the_registrys_settings():
    registry = EvidenceRegistry(trusted_humans={"lead"}, require_bounded=True)
    view = registry.at(INSIDE)
    assert view.trusted_humans == frozenset({"lead"}) and view.require_bounded is True
    assert view.snapshot() == registry.snapshot()

# ---------------------------------------------------------------- 6. the kernel's own times are checked

def test_a_clock_that_does_not_return_a_time_is_refused():
    k = ConservationKernel(allow_unguarded_roots=True, clock=lambda: "not-a-time", allow_unguarded_evidence=True)
    p = Proposition("p-in", "Sensor reading 42.", EpistemicStatus.INFERENCE, OriginStatus.MACHINE_ORIGINATED)
    with pytest.raises(InvalidEvent, match="clock"):
        k.register_root(Artifact("in-1", "sensor", (p,), Actor("sensor", ActorKind.SYSTEM)))
    assert k.ledger.artifacts() == ()

def test_a_snapshot_stamped_in_the_future_is_refused(tmp_path):
    k, *_ = _adopted_kernel(_Clock(LATER))
    k.save(tmp_path / "kernel.json")
    with pytest.raises(SnapshotIntegrityError, match="future"):
        ConservationKernel.load(tmp_path / "kernel.json", allow_unguarded_roots=True, clock=_Clock(INSIDE), allow_unguarded_evidence=True)
