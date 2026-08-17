from conservation_kernel import ConservationKernel
from conservation_kernel.experiments import build_ground_truth, legitimate_transformation
from conservation_kernel.enums import VerificationStatus


def test_public_kernel_facade_commits_only_accepted_transformations():
    artifact, registry = build_ground_truth()
    kernel = ConservationKernel(registry=registry)
    kernel.register_root(artifact)
    output, record = legitimate_transformation(artifact, 1)

    result = kernel.submit(artifact, output, record)

    assert result.status is VerificationStatus.PASS_WITH_DECLARED_TRANSFORMATION
    assert kernel.ledger.artifact(output.artifact_id) == output
    assert kernel.reconstruct(output.artifact_id).root_artifact_ids == (artifact.artifact_id,)
