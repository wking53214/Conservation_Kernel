"""Conditions on a claim: a summary must not turn a conditional claim absolute.

A proposition may carry `conditions` (the circumstances it holds under). A
transformation may add a condition, but dropping or rewording one widens the
claim and needs a human SCOPE_WIDENING authorization, both when the
proposition itself is rewritten and when a new proposition is derived from a
conditional parent. Ported in spirit from innovation_os's
CompressionConstraint ("local must not become global, conditional must not
become absolute"), which innovation_os defined but never called.
"""

from dataclasses import replace

from conservation_kernel.enums import Dimension, EpistemicStatus, OriginStatus, TransitionKind, VerificationStatus
from conservation_kernel.events import AuthorizationEvent, DeclaredChange, TransformationRecord
from conservation_kernel.experiments import build_ground_truth
from conservation_kernel.model import Actor, Artifact, Proposition
from conservation_kernel.verifier import IndependentVerifier

SUBJECT = "p-ai-inference"
BILLING = "only for the billing queue"
BUSINESS_HOURS = "during business hours"


def _conditional_base(conditions=(BILLING,)):
    base, registry = build_ground_truth()
    props = tuple(
        replace(item, conditions=conditions) if item.proposition_id == SUBJECT else item
        for item in base.propositions
    )
    base = replace(base, artifact_id=f"{base.artifact_id}-conditional", propositions=props,
                   content_digest=None, artifact_digest=None)
    return base, registry


def _output(base, propositions, suffix):
    return Artifact(
        artifact_id=f"{base.artifact_id}-{suffix}",
        content=base.content,
        propositions=tuple(propositions),
        producer=Actor.model(f"summarizer-{suffix}"),
        parent_artifact_ids=(base.artifact_id,),
        version=base.version + 1,
        functional_contract=base.functional_contract,
    )


def _record(base, output, declarations, suffix, authorization_refs=()):
    return TransformationRecord(
        transformation_id=f"tx-scope-{suffix}",
        input_artifact_ids=(base.artifact_id,),
        output_artifact_id=output.artifact_id,
        transformer=output.producer,
        transformation_type="SUMMARY",
        declared_changes=tuple(declarations),
        input_hashes=(base.artifact_digest,),
        output_hash=output.artifact_digest,
        authorization_refs=tuple(authorization_refs),
        reason="scope fixture",
    )


def _rewrite(base, registry, new_conditions, suffix, authorization_refs=()):
    old = base.proposition_map()[SUBJECT]
    new = replace(old, conditions=new_conditions)
    output = _output(base, (new if item.proposition_id == SUBJECT else item for item in base.propositions), suffix)
    record = _record(base, output, (
        DeclaredChange(SUBJECT, Dimension.SCOPE, list(old.conditions), list(new.conditions), "conditions changed"),
    ), suffix, authorization_refs)
    return IndependentVerifier().verify(base, output, record, registry)


def _codes(result):
    return {v.code for v in result.violations}


def _widening(registry, auth_id, subject, from_value, to_value):
    event = AuthorizationEvent(
        authorization_id=auth_id,
        authorized_by=Actor.human("approver"),
        subject_id=subject,
        transition_kind=TransitionKind.SCOPE_WIDENING,
        from_value=list(from_value),
        to_value=list(to_value),
        reason="a human confirmed the claim holds more widely",
    )
    registry.add_authorization(event)
    return event.authorization_id


def test_dropping_a_condition_without_authorization_is_rejected():
    base, registry = _conditional_base()
    result = _rewrite(base, registry, (), "drop")
    assert not result.accepted
    assert "UNAUTHORIZED_SCOPE_WIDENING" in _codes(result)


def test_adding_a_condition_narrows_and_passes():
    base, registry = _conditional_base()
    result = _rewrite(base, registry, (BILLING, BUSINESS_HOURS), "narrow")
    assert result.accepted
    assert result.status is VerificationStatus.PASS_WITH_DECLARED_TRANSFORMATION


def test_rewording_a_condition_counts_as_dropping_it():
    base, registry = _conditional_base()
    result = _rewrite(base, registry, ("for billing",), "reword")
    assert "UNAUTHORIZED_SCOPE_WIDENING" in _codes(result)


def test_human_scope_widening_authorization_allows_the_drop():
    base, registry = _conditional_base()
    auth = _widening(registry, "auth-widen", SUBJECT, (BILLING,), ())
    result = _rewrite(base, registry, (), "drop-authorized", authorization_refs=(auth,))
    assert result.accepted, _codes(result)


def test_authorization_for_a_different_widening_does_not_count():
    base, registry = _conditional_base((BILLING, BUSINESS_HOURS))
    auth = _widening(registry, "auth-other", SUBJECT, (BILLING, BUSINESS_HOURS), (BILLING,))
    result = _rewrite(base, registry, (), "drop-all", authorization_refs=(auth,))
    assert "UNAUTHORIZED_SCOPE_WIDENING" in _codes(result)


def test_undeclared_condition_change_is_caught():
    base, registry = _conditional_base()
    old = base.proposition_map()[SUBJECT]
    new = replace(old, conditions=(BILLING, BUSINESS_HOURS))
    output = _output(base, (new if item.proposition_id == SUBJECT else item for item in base.propositions), "silent")
    result = IndependentVerifier().verify(base, output, _record(base, output, (), "silent"), registry)
    assert "UNDECLARED_CHANGE" in _codes(result)


def _derive(base, registry, conditions, suffix, authorization_refs=()):
    summary = Proposition(
        proposition_id=f"p-summary-{suffix}",
        text="Callers abandon after long waits.",
        epistemic_status=EpistemicStatus.INFERENCE,
        origin=OriginStatus.MACHINE_ORIGINATED,
        parent_proposition_ids=(SUBJECT,),
        conditions=conditions,
    )
    output = _output(base, (*base.propositions, summary), suffix)
    record = _record(base, output, (
        DeclaredChange(summary.proposition_id, Dimension.LINEAGE, "absent", "present", "summary added"),
    ), suffix, authorization_refs)
    return IndependentVerifier().verify(base, output, record, registry)


def test_derived_summary_must_carry_parent_conditions():
    base, registry = _conditional_base()
    result = _derive(base, registry, (), "absolute")
    assert "CONDITION_DROPPED_IN_DERIVATION" in _codes(result)


def test_derived_summary_that_keeps_the_condition_passes():
    base, registry = _conditional_base()
    result = _derive(base, registry, (BILLING,), "kept")
    assert "CONDITION_DROPPED_IN_DERIVATION" not in _codes(result)
    assert result.accepted, _codes(result)


def test_derived_summary_with_human_widening_passes():
    base, registry = _conditional_base()
    auth = _widening(registry, "auth-derive", "p-summary-widened", (BILLING,), ())
    result = _derive(base, registry, (), "widened", authorization_refs=(auth,))
    assert "CONDITION_DROPPED_IN_DERIVATION" not in _codes(result)


def test_a_proposition_without_conditions_keeps_its_digest():
    base, _ = build_ground_truth()
    for item in base.propositions:
        assert "conditions" not in item.to_dict()
    rebuilt = replace(base, content_digest=None, artifact_digest=None)
    assert rebuilt.artifact_digest == base.artifact_digest


def test_conditions_round_trip_and_change_the_digest():
    base, _ = _conditional_base()
    data = base.to_dict()
    assert Artifact.from_dict(data).proposition_map()[SUBJECT].conditions == (BILLING,)
    plain, _ = build_ground_truth()
    assert base.proposition_map()[SUBJECT].to_dict() != plain.proposition_map()[SUBJECT].to_dict()
