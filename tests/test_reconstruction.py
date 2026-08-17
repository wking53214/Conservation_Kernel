from conservation_kernel.experiments import build_ground_truth, legitimate_transformation
from conservation_kernel.ledger import ConservationLedger
from conservation_kernel.reconstruction import ReconstructionEngine
from conservation_kernel.verifier import IndependentVerifier


def test_ten_transformations_remain_reconstructible_without_copying_original_content():
    original, registry = build_ground_truth()
    ledger = ConservationLedger()
    ledger.add_initial(original)
    verifier = IndependentVerifier()
    current = original

    for step in range(1, 11):
        output, record = legitimate_transformation(current, step)
        result = verifier.verify(current, output, record, registry)
        assert result.accepted
        ledger.commit(output, record, result)
        current = output

    reconstruction = ReconstructionEngine().reconstruct(ledger, current.artifact_id)

    assert reconstruction.root_artifact_ids == (original.artifact_id,)
    assert len(reconstruction.artifact_ids_in_order) == 11
    assert len(reconstruction.transformation_ids_in_order) == 10
    assert all(len(history) == 11 for history in reconstruction.proposition_histories.values())
    assert original.content not in current.content
    assert reconstruction.serialized_bytes > len(original.to_json().encode("utf-8"))
