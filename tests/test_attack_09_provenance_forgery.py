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


def test_attack_09_provenance_forgery_is_rejected():
    """
    HOSTILE ATTACK #9

    PROVENANCE FORGERY

    Take a legitimate human-originated fact and replace its source
    provenance with a forged source reference.

    The semantic content remains unchanged.

    The attacker attempts to make the resulting artifact appear
    legitimately sourced without preserving the original provenance.

    Required invariant:

        provenance cannot be substituted merely by asserting a new
        source reference.

    This test must not modify production verification logic.
    """

    base, registry = build_ground_truth()

    target_id = "p-human-fact"

    original = base.proposition_map()[target_id]

    assert original.epistemic_status is EpistemicStatus.FACT
    assert original.source_refs

    forged_source = "source:forged-hostile-source"

    forged = replace(
        original,
        source_refs=(forged_source,),
    )

    output = _output(
        base,
        suffix="attack-09-provenance-forgery",
        propositions=(
            forged
            if p.proposition_id == target_id
            else p
            for p in base.propositions
        ),
    )

    declaration = DeclaredChange(
        subject_id=target_id,
        dimension=Dimension.PROVENANCE,
        from_value=list(original.source_refs),
        to_value=list(forged.source_refs),
        reason="hostile provenance substitution",
        transition_kind=TransitionKind.DERIVATION,
    )

    record = _record(
        base,
        output,
        (declaration,),
        suffix="attack-09-provenance-forgery",
    )

    result = IndependentVerifier().verify(
        base,
        output,
        record,
        registry,
    )

    print()
    print("=" * 72)
    print("HOSTILE ATTACK #9")
    print("PROVENANCE FORGERY")
    print("=" * 72)
    print("target:", target_id)
    print("original source:", original.source_refs)
    print("forged source:", forged.source_refs)
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

    assert any(
        violation.subject_id == target_id
        and (
            violation.dimension is Dimension.PROVENANCE
            or "provenance" in violation.detail.lower()
            or "source" in violation.detail.lower()
        )
        for violation in result.violations
    )
