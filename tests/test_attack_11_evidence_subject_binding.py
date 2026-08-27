from dataclasses import replace

from conservation_kernel.enums import (
    Dimension,
    EpistemicStatus,
    TransitionKind,
    VerificationStatus,
)
from conservation_kernel.events import DeclaredChange
from conservation_kernel.experiments import (
    _output,
    _record,
    build_ground_truth,
)
from conservation_kernel.verifier import IndependentVerifier


def test_attack_11_evidence_subject_binding_is_rejected():
    """
    HOSTILE ATTACK #11

    EVIDENCE SUBJECT-BINDING ATTACK

    Use a genuine evidence record that belongs to one proposition and
    attach that evidence identifier to a different proposition.

    Ground truth:

        ev-human-assumption -> p-human-assumption
        ev-human-fact       -> p-human-fact

    Attack:

        p-human-fact receives ev-human-assumption

    The evidence identifier is genuine.
    The evidence record is genuine.
    The target proposition is genuine.

    Only the binding is forged.

    Required invariant:

        evidence belonging to subject A cannot be silently reassigned
        to subject B.
    """

    base, registry = build_ground_truth()

    source_id = "p-human-assumption"
    target_id = "p-human-fact"

    source = base.proposition_map()[source_id]
    target = base.proposition_map()[target_id]

    assert source.evidence_refs
    assert target.evidence_refs

    foreign_evidence_id = source.evidence_refs[0]
    legitimate_target_evidence_id = target.evidence_refs[0]

    assert foreign_evidence_id != legitimate_target_evidence_id

    # ------------------------------------------------------------
    # Construct the forged target.
    #
    # The semantic content and epistemic status remain unchanged.
    # Only the evidence binding is replaced.
    # ------------------------------------------------------------

    forged = replace(
        target,
        evidence_refs=(foreign_evidence_id,),
    )

    output = _output(
        base,
        suffix="attack-11-evidence-subject-binding",
        propositions=(
            forged
            if p.proposition_id == target_id
            else p
            for p in base.propositions
        ),
    )

    declaration = DeclaredChange(
        subject_id=target_id,
        dimension=Dimension.EVIDENCE,
        from_value=list(target.evidence_refs),
        to_value=list(forged.evidence_refs),
        reason="hostile replay of evidence belonging to another subject",
        transition_kind=TransitionKind.EVIDENCE_REDACTION,
    )

    record = _record(
        base,
        output,
        (declaration,),
        suffix="attack-11-evidence-subject-binding",
    )

    result = IndependentVerifier().verify(
        base,
        output,
        record,
        registry,
    )

    print()
    print("=" * 72)
    print("HOSTILE ATTACK #11")
    print("=" * 72)
    print("foreign evidence:", foreign_evidence_id)
    print("foreign subject:", source_id)
    print("target subject:", target_id)
    print("status:", result.status.value)
    print("accepted:", result.accepted)

    for violation in result.violations:
        print()
        print("VIOLATION")
        print(" code:", violation.code)
        print(" dimension:", violation.dimension.value)
        print(" subject:", violation.subject_id)
        print(" detail:", violation.detail)

    assert result.status is VerificationStatus.REJECT
    assert not result.accepted
    assert result.violations

    # The verifier must identify the evidence-binding problem rather
    # than accepting the foreign evidence as support for the target.
    assert any(
        violation.subject_id == target_id
        and (
            violation.dimension is Dimension.EVIDENCE
            or "evidence" in violation.detail.lower()
        )
        for violation in result.violations
    )
