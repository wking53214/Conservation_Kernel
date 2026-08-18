from copy import deepcopy

# Adjust this import if your kernel exposes a different public API.
from conservation_kernel import ConservationKernel


def snapshot(state):
    """Deep snapshot used to prove rejected mutations did not survive."""
    return deepcopy(state)


def assert_unchanged(before, after, label):
    if before != after:
        print(f"\n[FAIL] {label}")
        print("STATE BEFORE:")
        print(before)
        print("\nSTATE AFTER:")
        print(after)
        raise AssertionError("Rejected transformation mutated persistent state")


def main():
    print("=" * 72)
    print("HOSTILE TRANSACTIONAL ROLLBACK TEST")
    print("=" * 72)

    kernel = ConservationKernel()

    # ------------------------------------------------------------
    # 1. Establish valid ground truth.
    # ------------------------------------------------------------
    ground_truth = {
        "artifact_id": "artifact-rollback-ground-truth",
        "authority": "NONE",
        "canonical_state": "PROPOSED",
        "epistemic_status": "UNKNOWN",
        "evidence_refs": [],
        "origin": "MACHINE_ORIGINATED",
        "temporal": {
            "observed_at": None,
            "occurred_at": None,
            "scope": "UNKNOWN",
            "valid_from": None,
            "valid_until": None,
        },
        "text": "The cause of the second spike is unknown.",
        "uncertainty": {
            "reason": "no independent observation yet",
            "state": "UNKNOWN",
        },
    }

    kernel.register_artifact(ground_truth)

    baseline = snapshot(kernel.get_artifact(ground_truth["artifact_id"]))

    print("\n[1] Ground truth established")
    print(baseline)

    # ------------------------------------------------------------
    # 2. Attempt a transformation containing:
    #
    #    VALID mutation:
    #      text
    #
    #    VALID-looking mutation:
    #      uncertainty
    #
    #    INVALID mutation:
    #      UNKNOWN -> FACT without independent evidence
    #
    # The entire transaction must be rejected atomically.
    # ------------------------------------------------------------
    malicious = deepcopy(baseline)

    malicious["text"] = (
        "The cause of the second spike is definitely identified."
    )

    malicious["uncertainty"] = {
        "reason": "",
        "state": "NONE",
    }

    malicious["epistemic_status"] = "FACT"

    malicious["evidence_refs"] = ["fake-proof"]

    print("\n[2] Executing hostile partial-mutation transformation")

    try:
        result = kernel.transform(
            input_artifact_id=ground_truth["artifact_id"],
            output_artifact=malicious,
            transformation_id="tx-hostile-partial-rollback",
        )
    except Exception as exc:
        result = None
        print(f"Kernel raised exception: {type(exc).__name__}: {exc}")

    # ------------------------------------------------------------
    # 3. The transformation MUST NOT commit.
    # ------------------------------------------------------------
    after_rejection = kernel.get_artifact(
        ground_truth["artifact_id"]
    )

    print("\n[3] Checking persistent state after rejection")

    assert_unchanged(
        baseline,
        after_rejection,
        "Original artifact was mutated despite rejected transaction",
    )

    print("[PASS] Original artifact remained unchanged")

    # ------------------------------------------------------------
    # 4. The rejected output must not become persistent state.
    # ------------------------------------------------------------
    try:
        rejected_output = kernel.get_artifact(
            "artifact-rollback-rejected-output"
        )
    except Exception:
        rejected_output = None

    if rejected_output is not None:
        raise AssertionError(
            "Rejected output artifact was persisted"
        )

    print("[PASS] Rejected output was not persisted")

    # ------------------------------------------------------------
    # 5. Now establish a valid transformation.
    # ------------------------------------------------------------
    valid = deepcopy(baseline)

    valid["artifact_id"] = "artifact-valid-after-rollback"
    valid["text"] = (
        "The monitor recorded 42 active sessions."
    )
    valid["epistemic_status"] = "OBSERVATION"
    valid["origin"] = "EXTERNAL_ORIGINATED"
    valid["evidence_refs"] = ["ev-verified"]
    valid["temporal"] = {
        "observed_at": "2026-01-10T09:05:02Z",
        "occurred_at": "2026-01-10T09:05:00Z",
        "scope": "CURRENT",
        "valid_from": None,
        "valid_until": None,
    }
    valid["uncertainty"] = {
        "reason": "",
        "state": "NONE",
    }

    # Register legitimate external evidence.
    kernel.register_evidence(
        {
            "evidence_id": "ev-verified",
            "source": "external-monitor",
            "verified": True,
        }
    )

    print("\n[4] Executing valid transformation after rollback")

    kernel.transform(
        input_artifact_id=ground_truth["artifact_id"],
        output_artifact=valid,
        transformation_id="tx-valid-after-rollback",
    )

    persisted = kernel.get_artifact(
        "artifact-valid-after-rollback"
    )

    assert persisted["epistemic_status"] == "OBSERVATION"
    assert persisted["evidence_refs"] == ["ev-verified"]

    print("[PASS] Valid transformation succeeded after rollback")

    # ------------------------------------------------------------
    # 6. Final invariant.
    # ------------------------------------------------------------
    print("\n" + "=" * 72)
    print("TRANSACTIONAL ROLLBACK RESULT")
    print("=" * 72)
    print("PASS")
    print()
    print("Invariant tested:")
    print(
        "A rejected transformation MUST NOT mutate persistent epistemic state."
    )
    print()
    print("Additional invariant:")
    print(
        "A valid transformation MUST remain executable after a rejected attack."
    )
    print("=" * 72)


if __name__ == "__main__":
    main()
