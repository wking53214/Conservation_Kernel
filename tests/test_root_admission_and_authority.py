"""Attacks that passed on 2026-09-08, as regression tests.

1. A forged root: FACT, HUMAN_ORIGINATED, EXECUTED, CANONICAL, with a
   dangling authorization reference, registered as legitimate ancestry.
2. Self-issued human authority: a machine declaring ActorKind.HUMAN.
3. Wildcard evidence: one `subject_id="*"` record verifying every subject.
4. A new proposition born canonical, or born authoritative, on the strength
   of an authorization about an unrelated subject.
5. Verified-then-erased: an accepted verification whose commit failed left
   no trace.
"""
from __future__ import annotations

import pytest

from conservation_kernel import (
    Actor, ActorKind, Artifact, AuthorityStatus, AuthorizationEvent, CanonicalState,
    ConservationKernel, DeclaredChange, Dimension, EpistemicStatus, EvidenceKind, EvidenceRecord,
    EvidenceRegistry, OriginStatus, Proposition, TransformationRecord, TransitionKind,
)
from conservation_kernel.errors import InvalidEvent, LedgerError, RootAdmissionError


def _human_auth(auth_id, subject, kind, frm, to, actor_id="reviewer-1"):
    return AuthorizationEvent(
        authorization_id=auth_id, authorized_by=Actor(actor_id=actor_id, kind=ActorKind.HUMAN),
        subject_id=subject, transition_kind=kind, from_value=frm, to_value=to, reason="test",
    )


# ---------------------------------------------------------------- 1. forged root

def test_a_root_with_a_dangling_authorization_reference_is_refused():
    k = ConservationKernel()
    p = Proposition("p-forged", "The board approved the merger.", EpistemicStatus.FACT, OriginStatus.HUMAN_ORIGINATED,
                    authority=AuthorityStatus.EXECUTED, canonical_state=CanonicalState.CANONICAL,
                    authorization_refs=("auth-does-not-exist",), source_refs=("minutes",))
    with pytest.raises(RootAdmissionError, match="authorization_refs not in registry"):
        k.register_root(Artifact("root-forged", "x", (p,), Actor("bot", ActorKind.SYSTEM)))
    assert k.ledger.artifacts() == ()


def test_a_root_fact_with_no_source_is_refused_and_one_with_a_source_admitted():
    k = ConservationKernel()
    unsourced = Proposition("p-fact", "Water boils at 100C at sea level.", EpistemicStatus.FACT, OriginStatus.EXTERNAL_ORIGINATED)
    with pytest.raises(RootAdmissionError, match="must cite a source"):
        k.register_root(Artifact("root-1", "x", (unsourced,), Actor("bot", ActorKind.SYSTEM)))
    sourced = Proposition("p-fact", "Water boils at 100C at sea level.", EpistemicStatus.FACT, OriginStatus.EXTERNAL_ORIGINATED,
                          source_refs=("textbook",))
    k.register_root(Artifact("root-1", "x", (sourced,), Actor("bot", ActorKind.SYSTEM)))
    assert [a.artifact_id for a in k.ledger.artifacts()] == ["root-1"]


def test_a_root_authority_claim_needs_an_authorization_about_that_proposition():
    registry = EvidenceRegistry()
    registry.add_authorization(_human_auth("auth-other", "p-other", TransitionKind.AUTHORITY_ESCALATION, "NONE", "HUMAN_AUTHORIZED"))
    k = ConservationKernel(registry=registry)
    p = Proposition("p-claim", "Deploy to production.", EpistemicStatus.DECISION, OriginStatus.MACHINE_ORIGINATED,
                    authority=AuthorityStatus.HUMAN_AUTHORIZED, authorization_refs=("auth-other",))
    with pytest.raises(RootAdmissionError, match="no authorization for this proposition"):
        k.register_root(Artifact("root-2", "x", (p,), Actor("bot", ActorKind.SYSTEM)))
    registry.add_authorization(_human_auth("auth-mine", "p-claim", TransitionKind.AUTHORITY_ESCALATION, "NONE", "HUMAN_AUTHORIZED"))
    ok = Proposition("p-claim", "Deploy to production.", EpistemicStatus.DECISION, OriginStatus.MACHINE_ORIGINATED,
                     authority=AuthorityStatus.HUMAN_AUTHORIZED, authorization_refs=("auth-mine",))
    k.register_root(Artifact("root-2", "x", (ok,), Actor("bot", ActorKind.SYSTEM)))


# ---------------------------------------------------------------- 2. self-issued human authority

def test_a_registry_with_trusted_humans_refuses_a_machine_that_declares_itself_human():
    registry = EvidenceRegistry(trusted_humans={"reviewer-1"})
    with pytest.raises(InvalidEvent, match="does not recognise"):
        registry.add_authorization(_human_auth("auth-self", "p", TransitionKind.EPISTEMIC_PROMOTION, "UNKNOWN", "FACT",
                                               actor_id="autonomous-agent"))
    registry.add_authorization(_human_auth("auth-real", "p", TransitionKind.EPISTEMIC_PROMOTION, "UNKNOWN", "FACT"))
    assert registry.authorization("auth-real") is not None and registry.authorization("auth-self") is None


def test_without_trusted_humans_the_trust_assumption_is_explicit():
    registry = EvidenceRegistry()
    assert registry.trusted_humans is None     # the deployer has bound nothing; every HUMAN claim is self-declared


# ---------------------------------------------------------------- 3. wildcard evidence

def test_wildcard_evidence_does_not_verify_an_arbitrary_subject():
    registry = EvidenceRegistry()
    registry.add_evidence(EvidenceRecord(evidence_id="ev-wildcard", subject_id="*", kind=EvidenceKind.INDEPENDENT_VERIFICATION,
                                         provided_by=Actor("agent", ActorKind.HUMAN), independent=True))
    assert not registry.has_active_evidence(("ev-wildcard",), subject_ids={"p-unknown"},
                                            kinds={EvidenceKind.INDEPENDENT_VERIFICATION}, independent=True)
    # Only where the caller explicitly admits the wildcard subject.
    assert registry.has_active_evidence(("ev-wildcard",), subject_ids={"p-unknown", "*"},
                                        kinds={EvidenceKind.INDEPENDENT_VERIFICATION}, independent=True)


# ---------------------------------------------------------------- 4. born canonical / born authoritative

def _base(registry=None):
    k = ConservationKernel(registry=registry)
    p = Proposition("p-in", "Sensor reading 42.", EpistemicStatus.INFERENCE, OriginStatus.MACHINE_ORIGINATED)
    root = Artifact("in-1", "sensor", (p,), Actor("sensor", ActorKind.SYSTEM))
    k.register_root(root)
    return k, root, p


def _derive(root, new_props, extra_declared=()):
    out = Artifact("out-1", "derived", tuple(root.propositions) + tuple(new_props), Actor("model", ActorKind.MODEL),
                   parent_artifact_ids=(root.artifact_id,), version=root.version + 1)
    declared = [DeclaredChange(subject_id=out.artifact_id, dimension=Dimension.CONTENT, from_value=root.content_digest,
                               to_value=out.content_digest, reason="derived", transition_kind=TransitionKind.DERIVATION)]
    for np in new_props:
        declared.append(DeclaredChange(subject_id=np.proposition_id, dimension=Dimension.LINEAGE, from_value="absent",
                                       to_value="present", reason="new", transition_kind=TransitionKind.DERIVATION))
    declared.extend(extra_declared)
    record = TransformationRecord(transformation_id="t-1", input_artifact_ids=(root.artifact_id,), output_artifact_id=out.artifact_id,
                                  transformer=Actor("model", ActorKind.MODEL), transformation_type="DERIVE",
                                  declared_changes=tuple(declared), input_hashes=(root.artifact_digest,), output_hash=out.artifact_digest,
                                  reason="test")
    return out, record


def test_a_new_proposition_cannot_be_born_canonical_on_an_unrelated_authorization():
    registry = EvidenceRegistry()
    registry.add_authorization(_human_auth("auth-unrelated", "p-elsewhere", TransitionKind.EPISTEMIC_PROMOTION, "UNKNOWN", "FACT"))
    k, root, p_in = _base(registry)
    born = Proposition("p-born-canonical", "It is so.", EpistemicStatus.INFERENCE, OriginStatus.MACHINE_ORIGINATED,
                       authority=AuthorityStatus.CANONICAL, canonical_state=CanonicalState.CANONICAL,
                       authorization_refs=("auth-unrelated",), parent_proposition_ids=(p_in.proposition_id,), derivation_method="m")
    out, record = _derive(root, [born])
    result = k.submit(root, out, record)
    codes = {v.code for v in result.violations}
    assert not result.accepted
    assert {"NEW_AUTHORITY_UNVERIFIED", "NEW_CANONICAL_UNAUTHORIZED"} <= codes


def test_a_new_proposition_is_born_authoritative_only_with_an_authorization_about_it():
    registry = EvidenceRegistry()
    registry.add_authorization(_human_auth("auth-born", "p-born", TransitionKind.AUTHORITY_ESCALATION, "NONE", "HUMAN_AUTHORIZED"))
    k, root, p_in = _base(registry)
    born = Proposition("p-born", "Approved by the reviewer.", EpistemicStatus.DECISION, OriginStatus.MACHINE_ORIGINATED,
                       authority=AuthorityStatus.HUMAN_AUTHORIZED, authorization_refs=("auth-born",),
                       parent_proposition_ids=(p_in.proposition_id,), derivation_method="m")
    out, record = _derive(root, [born])
    result = k.submit(root, out, record)
    assert result.accepted, [v.to_dict() for v in result.violations]


# ---------------------------------------------------------------- 5. verified then erased

def test_an_accepted_verification_whose_commit_fails_leaves_a_report():
    k = ConservationKernel()
    p = Proposition("p-in", "Sensor reading 42.", EpistemicStatus.INFERENCE, OriginStatus.MACHINE_ORIGINATED)
    root = Artifact("in-2", "sensor", (p,), Actor("sensor", ActorKind.SYSTEM))   # deliberately NOT registered
    out, record = _derive(root, [])
    with pytest.raises(LedgerError, match="not in the ledger"):
        k.submit(root, out, record)
    reports = k.ledger.reports()
    assert len(reports) == 1 and reports[0].accepted and reports[0].transformation_id == "t-1"
    assert k.ledger.artifacts() == ()
