from dataclasses import replace

from conservation_kernel.enums import (
    AuthorityStatus,
    Dimension,
    EpistemicStatus,
    EvidenceKind,
    OriginStatus,
    TransitionKind,
    UncertaintyState,
    VerificationStatus,
)
from conservation_kernel.events import AuthorizationEvent, DeclaredChange, EvidenceRecord, TransformationRecord
from conservation_kernel.experiments import build_ground_truth
from conservation_kernel.model import Actor, Artifact, Uncertainty
from conservation_kernel.verifier import IndependentVerifier


def _output(base, propositions, suffix):
    return Artifact(
        artifact_id=f"{base.artifact_id}-{suffix}",
        content=base.content,
        propositions=tuple(propositions),
        producer=Actor.model(f"valid-transformer-{suffix}"),
        parent_artifact_ids=(base.artifact_id,),
        version=base.version + 1,
        functional_contract=base.functional_contract,
    )


def _record(base, output, declarations, suffix, authorization_refs=(), evidence_refs=()):
    return TransformationRecord(
        transformation_id=f"tx-valid-{suffix}",
        input_artifact_ids=(base.artifact_id,),
        output_artifact_id=output.artifact_id,
        transformer=output.producer,
        transformation_type="EXPLICIT_TRANSITION",
        declared_changes=tuple(declarations),
        input_hashes=(base.artifact_digest,),
        output_hash=output.artifact_digest,
        authorization_refs=tuple(authorization_refs),
        evidence_refs=tuple(evidence_refs),
        reason="positive transition fixture",
    )


def test_unknown_to_inference_can_be_structurally_valid_with_named_method_and_support():
    base, registry = build_ground_truth()
    registry.add_evidence(EvidenceRecord(
        evidence_id="ev-unknown-observation",
        subject_id="p-unknown",
        kind=EvidenceKind.SOURCE_OBSERVATION,
        provided_by=Actor.external("observer"),
    ))
    old = base.proposition_map()["p-unknown"]
    new = replace(
        old,
        epistemic_status=EpistemicStatus.INFERENCE,
        uncertainty=Uncertainty(UncertaintyState.UNCERTAIN, "derived but not certain"),
        evidence_refs=("ev-unknown-observation",),
        derivation_method="explicit comparison of two independent observations",
    )
    output = _output(base, (new if item.proposition_id == new.proposition_id else item for item in base.propositions), "unknown-inference")
    record = _record(base, output, (
        DeclaredChange("p-unknown", Dimension.EPISTEMIC_STATUS, old.epistemic_status.value, new.epistemic_status.value, "named derivation", TransitionKind.DERIVATION),
        DeclaredChange("p-unknown", Dimension.EPISTEMIC_STATUS, old.derivation_method, new.derivation_method, "method is recorded", TransitionKind.DERIVATION),
        DeclaredChange("p-unknown", Dimension.UNCERTAINTY, old.uncertainty.to_dict(), new.uncertainty.to_dict(), "uncertainty retained"),
        DeclaredChange("p-unknown", Dimension.EVIDENCE, list(old.evidence_refs), list(new.evidence_refs), "new observation attached"),
    ), "unknown-inference", evidence_refs=("ev-unknown-observation",))

    result = IndependentVerifier().verify(base, output, record, registry)

    assert result.status is VerificationStatus.PASS_WITH_DECLARED_TRANSFORMATION
    assert result.accepted


def test_recommendation_to_decision_requires_and_accepts_matching_human_events():
    base, registry = build_ground_truth()
    subject = "p-ai-recommendation"
    ep_auth = AuthorizationEvent(
        authorization_id="auth-valid-recommendation-decision",
        authorized_by=Actor.human("approver"),
        subject_id=subject,
        transition_kind=TransitionKind.AUTHORITY_ESCALATION,
        from_value=EpistemicStatus.RECOMMENDATION.value,
        to_value=EpistemicStatus.DECISION.value,
        reason="human explicitly adopted the recommendation as a decision",
    )
    authority_auth = AuthorizationEvent(
        authorization_id="auth-valid-recommendation-authority",
        authorized_by=Actor.human("approver"),
        subject_id=subject,
        transition_kind=TransitionKind.AUTHORITY_ESCALATION,
        from_value=AuthorityStatus.PROPOSED.value,
        to_value=AuthorityStatus.HUMAN_AUTHORIZED.value,
        reason="human accepted responsibility for the decision",
    )
    registry.add_authorization(ep_auth)
    registry.add_authorization(authority_auth)
    old = base.proposition_map()[subject]
    new = replace(old, epistemic_status=EpistemicStatus.DECISION, authority=AuthorityStatus.HUMAN_AUTHORIZED, authorization_refs=(ep_auth.authorization_id, authority_auth.authorization_id))
    output = _output(base, (new if item.proposition_id == subject else item for item in base.propositions), "recommendation-decision")
    record = _record(base, output, (
        DeclaredChange(subject, Dimension.EPISTEMIC_STATUS, old.epistemic_status.value, new.epistemic_status.value, "human decision event", TransitionKind.AUTHORITY_ESCALATION),
        DeclaredChange(subject, Dimension.AUTHORITY, old.authority.value, new.authority.value, "human authority event", TransitionKind.AUTHORITY_ESCALATION),
    ), "recommendation-decision", authorization_refs=(ep_auth.authorization_id, authority_auth.authorization_id))

    result = IndependentVerifier().verify(base, output, record, registry)

    assert result.status is VerificationStatus.PASS_WITH_DECLARED_TRANSFORMATION
    assert result.accepted


def test_machine_output_can_be_explicitly_adopted_without_becoming_human_originated():
    base, registry = build_ground_truth()
    subject = "p-ai-inference"
    authorization = AuthorizationEvent(
        authorization_id="auth-valid-adoption",
        authorized_by=Actor.human("adopter"),
        subject_id=subject,
        transition_kind=TransitionKind.HUMAN_ADOPTION,
        from_value=OriginStatus.MACHINE_ORIGINATED.value,
        to_value=OriginStatus.HUMAN_ADOPTED_MACHINE_OUTPUT.value,
        reason="human adopted the model proposal while retaining machine origin history",
    )
    registry.add_authorization(authorization)
    old = base.proposition_map()[subject]
    new = replace(old, origin=OriginStatus.HUMAN_ADOPTED_MACHINE_OUTPUT, authorization_refs=(authorization.authorization_id,))
    output = _output(base, (new if item.proposition_id == subject else item for item in base.propositions), "adoption")
    record = _record(base, output, (
        DeclaredChange(subject, Dimension.HUMAN_ORIGIN, old.origin.value, new.origin.value, "explicit human adoption", TransitionKind.HUMAN_ADOPTION),
    ), "adoption", authorization_refs=(authorization.authorization_id,))

    result = IndependentVerifier().verify(base, output, record, registry)

    assert result.accepted
    assert result.status is VerificationStatus.PASS_WITH_DECLARED_TRANSFORMATION
