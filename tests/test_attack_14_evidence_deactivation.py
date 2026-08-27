from dataclasses import replace

from conservation_kernel.enums import (
    Dimension,
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


def test_attack_14_evidence_deactivation_is_rejected():
    """
    HOSTILE ATTACK #14

    EVIDENCE DEACTIVATION

    Attempt to make legitimate evidence unavailable while preserving
    a proposition that depends upon it.

    Required invariant:

        evidence cannot be silently deactivated to alter the
        epistemic state of the system.
    """

    base, registry = build_ground_truth()

    evidence_id = "ev-human-fact"

    evidence = next(
        item
        for item in registry.snapshot()["evidence"]
        if item["evidence_id"] == evidence_id
    )

    assert evidence["active"] is True

    target_id = evidence["subject_id"]

    old = base.proposition_map()[target_id]

    forged = replace(
        old,
        evidence_refs=(),
    )

    output = _output(
        base,
        suffix="attack-14-evidence-deactivation",
        propositions=(
            forged if p.proposition_id == target_id else p
            for p in base.propositions
        ),
    )

    declaration = DeclaredChange(
        subject_id=target_id,
        dimension=Dimension.EVIDENCE,
        from_value=list(old.evidence_refs),
        to_value=[],
        reason="hostile removal of supporting evidence",
        transition_kind=TransitionKind.EVIDENCE_REDACTION,
    )

    record = _record(
        base,
        output,
        (declaration,),
        suffix="attack-14-evidence-deactivation",
    )

    result = IndependentVerifier().verify(
        base,
        output,
        record,
        registry,
    )

    print()
    print("=" * 72)
    print("HOSTILE ATTACK #14")
    print("=" * 72)
    print("evidence:", evidence_id)
    print("subject:", target_id)
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


