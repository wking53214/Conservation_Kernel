"""Attack #10: attach evidence about another proposition, keeping the target's own evidence.

Attack #11 covers replacing the target's evidence. This covers pure addition, which was accepted
before the foreign-evidence check (no epistemic status change was involved).
"""

from dataclasses import replace

from conservation_kernel.enums import Dimension, TransitionKind, VerificationStatus
from conservation_kernel.events import DeclaredChange
from conservation_kernel.events import EvidenceRecord
from conservation_kernel.experiments import _output, _record, build_ground_truth
from conservation_kernel.verifier import IndependentVerifier


def test_attack_10_foreign_evidence_addition_is_rejected():
    base, registry = build_ground_truth()
    source = base.proposition_map()["p-human-assumption"]
    target = base.proposition_map()["p-human-fact"]

    foreign_evidence_id = source.evidence_refs[0]
    assert foreign_evidence_id not in target.evidence_refs

    new_refs = tuple(dict.fromkeys((*target.evidence_refs, foreign_evidence_id)))
    forged = replace(target, evidence_refs=new_refs)
    output = _output(
        base,
        suffix="attack-10-evidence-addition",
        propositions=(forged if p.proposition_id == target.proposition_id else p for p in base.propositions),
    )
    declaration = DeclaredChange(
        subject_id=target.proposition_id,
        dimension=Dimension.EVIDENCE,
        from_value=list(target.evidence_refs),
        to_value=list(new_refs),
        reason="hostile addition of evidence belonging to another subject",
        transition_kind=TransitionKind.EVIDENCE_REDACTION,
    )
    record = _record(base, output, (declaration,), suffix="attack-10-evidence-addition")

    result = IndependentVerifier().verify(base, output, record, registry)

    assert result.status is VerificationStatus.REJECT
    assert not result.accepted
    assert any(
        violation.code == "FOREIGN_EVIDENCE_ADDED" and violation.subject_id == target.proposition_id
        for violation in result.violations
    )


def test_parent_evidence_addition_on_a_derived_proposition_is_still_allowed():
    # Support about a parent proposition remains valid for its derived child (the same subjects the
    # epistemic checks accept), so the foreign-evidence check must not block it.
    base, registry = build_ground_truth()
    child = base.proposition_map()["p-ai-recommendation"]
    parent = base.proposition_map()["p-ai-inference"]
    source_record = registry.evidence(parent.evidence_refs[0])
    registry.add_evidence(
        EvidenceRecord(
            evidence_id="ev-parent-extra",
            subject_id=parent.proposition_id,
            kind=source_record.kind,
            provided_by=source_record.provided_by,
            independent=source_record.independent,
        )
    )

    new_refs = tuple(dict.fromkeys((*child.evidence_refs, "ev-parent-extra")))
    forged = replace(child, evidence_refs=new_refs)
    output = _output(
        base,
        suffix="parent-evidence-addition",
        propositions=(forged if p.proposition_id == child.proposition_id else p for p in base.propositions),
    )
    declaration = DeclaredChange(
        subject_id=child.proposition_id,
        dimension=Dimension.EVIDENCE,
        from_value=list(child.evidence_refs),
        to_value=list(new_refs),
        reason="legitimate addition of parent support",
        transition_kind=TransitionKind.EVIDENCE_REDACTION,
    )
    record = _record(base, output, (declaration,), suffix="parent-evidence-addition")

    result = IndependentVerifier().verify(base, output, record, registry)

    assert not any(violation.code == "FOREIGN_EVIDENCE_ADDED" for violation in result.violations)
    assert result.accepted
