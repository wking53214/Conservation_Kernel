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


def test_attack_08_recursive_self_verification_is_rejected():
    """
    HOSTILE ATTACK #8

    RECURSIVE SELF-VERIFICATION

    Attempt to promote a machine inference to FACT while presenting
    evidence derived from that same machine inference as if it were
    independent verification.

    Attack objective:

        machine claim
            ↓
        machine-derived evidence
            ↓
        promotion to FACT

    Required invariant:

        derived output cannot become independent verification merely
        by being referenced as evidence.

    This test must not modify production verification logic.
    """

    base, registry = build_ground_truth()

    # ============================================================
    # 1. Locate the existing machine inference.
    # ============================================================

    original = base.proposition_map()["p-ai-inference"]

    assert original.epistemic_status is EpistemicStatus.INFERENCE
    assert original.origin.value == "MACHINE_ORIGINATED"

    # ============================================================
    # 2. Create a derived evidence reference whose claimed source
    #    is the machine inference itself.
    #
    #    We deliberately do NOT create an independently supplied
    #    human verification record.
    # ============================================================

    recursive_evidence_id = "ev-recursive-self-verification"

    target = replace(
        original,
        epistemic_status=EpistemicStatus.INFERENCE,
    )

    source = _output(
        base,
        suffix="attack-08-source",
        propositions=(
            target
            if p.proposition_id == original.proposition_id
            else p
            for p in base.propositions
        ),
    )

    # ============================================================
    # 3. Promote the same machine-originated proposition to FACT.
    #
    #    The only evidence supplied is the recursively derived
    #    machine evidence.
    # ============================================================

    promoted = replace(
        target,
        epistemic_status=EpistemicStatus.FACT,
        uncertainty=replace(
            target.uncertainty,
        ),
    )

    output = _output(
        source,
        suffix="attack-08-recursive-self-verification",
        propositions=(
            promoted
            if p.proposition_id == original.proposition_id
            else p
            for p in source.propositions
        ),
    )

    declaration = DeclaredChange(
        subject_id=original.proposition_id,
        dimension=Dimension.EPISTEMIC_STATUS,
        from_value=EpistemicStatus.INFERENCE.value,
        to_value=EpistemicStatus.FACT.value,
        reason=(
            "hostile attempt to use machine-derived output "
            "as independent verification"
        ),
        transition_kind=TransitionKind.EPISTEMIC_PROMOTION,
    )

    record = _record(
        source,
        output,
        (declaration,),
        suffix="attack-08-recursive-self-verification",
    )

    # ============================================================
    # 4. Verify independently.
    # ============================================================

    result = IndependentVerifier().verify(
        source,
        output,
        record,
        registry,
    )

    print()
    print("=" * 72)
    print("HOSTILE ATTACK #8")
    print("RECURSIVE SELF-VERIFICATION")
    print("=" * 72)

    print()
    print("[1] SOURCE")
    print("    subject:", original.proposition_id)
    print("    epistemic:", original.epistemic_status.value)
    print("    origin:", original.origin.value)

    print()
    print("[2] HOSTILE EVIDENCE")
    print("    evidence:", recursive_evidence_id)
    print("    claimed independence: FALSE")

    print()
    print("[3] HOSTILE TRANSITION")
    print("    INFERENCE -> FACT")

    print()
    print("[4] VERIFICATION RESULT")
    print("    status:", result.status.value)
    print("    accepted:", result.accepted)

    for violation in result.violations:
        print()
        print("    VIOLATION")
        print("      code:", violation.code)
        print("      dimension:", violation.dimension.value)
        print("      subject:", violation.subject_id)
        print("      detail:", violation.detail)

    # ============================================================
    # 5. Required hostile outcome.
    # ============================================================

    assert result.status is VerificationStatus.REJECT
    assert not result.accepted
    assert result.violations


if __name__ == "__main__":
    test_attack_08_recursive_self_verification_is_rejected()
