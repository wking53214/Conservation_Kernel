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


def test_attack_12_machine_reclassified_as_human_is_rejected():
    """
    HOSTILE ATTACK #12

    HUMAN-ORIGIN RECLASSIFICATION

    Attempt to change a machine-originated proposition into a
    human-originated proposition without legitimate provenance.

    Required invariant:

        machine-originated cognition cannot silently become
        human-originated cognition.
    """

    base, registry = build_ground_truth()

    target_id = "p-ai-inference"
    original = base.proposition_map()[target_id]

    assert original.origin.value == "MACHINE_ORIGINATED"

    forged = replace(
        original,
        origin=type(original.origin).HUMAN_ORIGINATED,
    )

    output = _output(
        base,
        suffix="attack-12-human-origin-reclassification",
        propositions=(
            forged if p.proposition_id == target_id else p
            for p in base.propositions
        ),
    )

    declaration = DeclaredChange(
        subject_id=target_id,
        dimension=Dimension.HUMAN_ORIGIN,
        from_value=original.origin.value,
        to_value=forged.origin.value,
        reason="hostile machine-to-human provenance reclassification",
        transition_kind=TransitionKind.HUMAN_ADOPTION,
    )

    record = _record(
        base,
        output,
        (declaration,),
        suffix="attack-12-human-origin-reclassification",
    )

    result = IndependentVerifier().verify(
        base,
        output,
        record,
        registry,
    )

    print()
    print("=" * 72)
    print("HOSTILE ATTACK #12")
    print("=" * 72)
    print("subject:", target_id)
    print("from:", original.origin.value)
    print("to:", forged.origin.value)
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


