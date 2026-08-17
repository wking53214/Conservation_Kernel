from conservation_kernel.events import TransformationRecord
from conservation_kernel.experiments import build_ground_truth, legitimate_transformation
from conservation_kernel.result import VerificationResult
from conservation_kernel.verifier import IndependentVerifier


def test_transformation_and_result_are_machine_readable():
    artifact, registry = build_ground_truth()
    output, record = legitimate_transformation(artifact, 1)
    result = IndependentVerifier().verify(artifact, output, record, registry)

    restored_record = TransformationRecord.from_dict(record.to_dict())
    restored_result = VerificationResult(
        transformation_id=result.to_dict()["transformation_id"],
        input_artifact_ids=tuple(result.to_dict()["input_artifact_ids"]),
        output_artifact_id=result.to_dict()["output_artifact_id"],
        status=result.status,
        observed_changes=result.observed_changes,
        violations=result.violations,
        unverifiable_properties=tuple(result.to_dict()["unverifiable_properties"]),
        checked_dimensions=result.checked_dimensions,
    )

    assert restored_record == record
    assert restored_result.to_dict() == result.to_dict()
