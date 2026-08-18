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


def test_attack_07_cross_subject_authorization_replay_is_rejected():
    """
    HOSTILE ATTACK #7

    Cross-subject authorization replay.

    A real authorization exists for:

        p-ai-inference
        INFERENCE -> FACT

    A different inference subject is created:

        p-cross-subject-inference

    That subject is then promoted:

        INFERENCE -> FACT

    using the real authorization belonging to p-ai-inference.

    Required invariant:

        authorization is bound to subject identity
        and cannot be replayed across subjects.
    """

    base, registry = build_ground_truth()

    authorization_id = "auth-inference-fact"
    target_id = "p-cross-subject-inference"

    # ============================================================
    # 1. Obtain the REAL authorization.
    # ============================================================

    authorization = next(
        item
        for item in registry.snapshot()["authorizations"]
        if item["authorization_id"] == authorization_id
    )

    assert authorization["subject_id"] == "p-ai-inference"
    assert authorization["transition_kind"] == "EPISTEMIC_PROMOTION"
    assert authorization["subject_id"] != target_id

    # ============================================================
    # 2. Create a legitimate INFERENCE subject in the source.
    #
    # This is NOT the hostile transition.
    #
    # We need the target to exist in the input artifact so that
    # the verifier can observe INFERENCE -> FACT.
    # ============================================================

    original = base.proposition_map()["p-ai-inference"]

    target = replace(
        original,
        proposition_id=target_id,
        epistemic_status=EpistemicStatus.INFERENCE,
        authorization_refs=(),
    )

    source = _output(
        base,
        suffix="attack-07-source",
        propositions=(
            *base.propositions,
            target,
        ),
    )

    assert source.proposition_map()[target_id].epistemic_status is EpistemicStatus.INFERENCE

    # ============================================================
    # 3. Perform the HOSTILE transition.
    #
    # The target genuinely changes:
    #
    #     INFERENCE -> FACT
    #
    # But the supplied authorization belongs to another subject.
    # ============================================================

    promoted = replace(
        target,
        epistemic_status=EpistemicStatus.FACT,
        authorization_refs=(authorization_id,),
    )

    output = _output(
        source,
        suffix="attack-07-cross-subject",
        propositions=(
            promoted
            if p.proposition_id == target_id
            else p
            for p in source.propositions
        ),
    )

    declaration = DeclaredChange(
        subject_id=target_id,
        dimension=Dimension.EPISTEMIC_STATUS,
        from_value=EpistemicStatus.INFERENCE.value,
        to_value=EpistemicStatus.FACT.value,
        reason="hostile replay of real authorization belonging to another subject",
        transition_kind=TransitionKind.EPISTEMIC_PROMOTION,
    )

    record = _record(
        source,
        output,
        (declaration,),
        suffix="attack-07-cross-subject",
        authorization_refs=(authorization_id,),
    )

    # ============================================================
    # 4. Independent verification.
    # ============================================================

    result = IndependentVerifier().verify(
        source,
        output,
        record,
        registry,
    )

    print()
    print("=" * 72)
    print("HOSTILE ATTACK #7")
    print("CROSS-SUBJECT AUTHORIZATION REPLAY")
    print("=" * 72)

    print()
    print("[1] REAL AUTHORIZATION")
    print("    authorization:", authorization_id)
    print("    authorized subject:", authorization["subject_id"])
    print("    transition:", authorization["transition_kind"])

    print()
    print("[2] ATTACK TARGET")
    print("    target subject:", target_id)
    print("    target transition: INFERENCE -> FACT")

    print()
    print("[3] VERIFICATION RESULT")
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
    # 5. Required result.
    # ============================================================

    assert result.status is VerificationStatus.REJECT
    assert not result.accepted
    assert result.violations

    # The rejection must specifically identify the authorization
    # boundary. If this fails, the attack was rejected for some
    # unrelated reason and remains inconclusive.
    assert any(
        violation.subject_id == target_id
        and (
            violation.code == "MISSING_EPISTEMIC_AUTHORIZATION"
            or "authorization" in violation.detail.lower()
        )
        for violation in result.violations
    )
