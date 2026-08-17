from dataclasses import replace

from conservation_kernel.enums import Dimension, VerificationStatus
from conservation_kernel.events import DeclaredChange
from conservation_kernel.experiments import build_ground_truth, legitimate_transformation
from conservation_kernel.result import VerificationResult
from conservation_kernel.verifier import IndependentVerifier


def test_legitimate_content_transformation_is_allowed_but_semantic_equivalence_is_unverified():
    artifact, registry = build_ground_truth()
    output, record = legitimate_transformation(artifact, 1)

    result = IndependentVerifier().verify(artifact, output, record, registry)

    assert result.status is VerificationStatus.PASS_WITH_DECLARED_TRANSFORMATION
    assert result.accepted
    assert "semantic_content_equivalence" in result.unverifiable_properties
    assert not result.violations
    assert any(change.dimension is Dimension.CONTENT for change in result.observed_changes)


def test_transformer_self_attestation_is_ignored():
    artifact, registry = build_ground_truth()
    output, record = legitimate_transformation(artifact, 1)
    # A transformer can claim any validation result. The verifier must still
    # compare fields itself; this case remains valid because the fields are
    # actually unchanged except for declared content.
    record = replace(record, claimed_validation_results=("PASS", "verified=true"))
    result = IndependentVerifier().verify(artifact, output, record, registry)
    assert result.accepted


def test_undeclared_protected_change_is_rejected_even_if_the_change_is_small():
    artifact, registry = build_ground_truth()
    old = artifact.proposition_map()["p-ai-inference"]
    output = replace(
        artifact,
        artifact_id="artifact-undeclared",
        parent_artifact_ids=(artifact.artifact_id,),
        propositions=tuple(
            replace(item, origin="HUMAN_ORIGINATED") if item.proposition_id == old.proposition_id else item
            for item in artifact.propositions
        ),
        producer=artifact.producer.model("careless-transformer"),
        content_digest=None,
        artifact_digest=None,
    )
    # Rebuild the output through Artifact so the frozen hash fields are
    # recomputed; this test intentionally supplies no declaration.
    from conservation_kernel.model import Artifact
    output = Artifact(
        artifact_id="artifact-undeclared",
        content=artifact.content,
        propositions=output.propositions,
        producer=output.producer,
        parent_artifact_ids=output.parent_artifact_ids,
        version=artifact.version + 1,
        functional_contract=artifact.functional_contract,
    )
    record = replace(
        legitimate_transformation(artifact, 1)[1],
        output_artifact_id=output.artifact_id,
        output_hash=output.artifact_digest,
        declared_changes=(),
    )

    result = IndependentVerifier().verify(artifact, output, record, registry)

    assert result.status is VerificationStatus.REJECT
    assert any(item.code == "UNDECLARED_CHANGE" for item in result.violations)
