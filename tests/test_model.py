import json

import pytest

from conservation_kernel.errors import InvalidArtifact
from conservation_kernel.experiments import build_ground_truth
from conservation_kernel.model import Artifact


def test_ground_truth_contains_mixed_states_and_typed_envelope():
    artifact, registry = build_ground_truth()

    statuses = {item.epistemic_status.value for item in artifact.propositions}
    origins = {item.origin.value for item in artifact.propositions}

    assert {"FACT", "INFERENCE", "ESTIMATED", "UNKNOWN", "CONFLICTED", "SIMULATED", "RECOMMENDATION", "DECISION", "OBSERVATION"} <= statuses
    assert {"HUMAN_ORIGINATED", "MACHINE_ORIGINATED", "EXTERNAL_ORIGINATED"} <= origins
    assert artifact.artifact_digest
    assert artifact.content_digest
    assert artifact.envelope_summary()["output_hash"] == artifact.artifact_digest
    assert registry.evidence("ev-human-fact") is not None


def test_artifact_round_trip_is_semantic_not_byte_identity():
    artifact, _ = build_ground_truth()
    encoded = artifact.to_json()
    restored = Artifact.from_json(encoded)

    assert restored == artifact
    assert json.loads(encoded)["artifact_digest"] == artifact.artifact_digest


def test_malformed_artifact_is_not_silently_repaired():
    artifact, _ = build_ground_truth()
    payload = artifact.to_dict()
    del payload["propositions"][0]["epistemic_status"]

    with pytest.raises(InvalidArtifact, match="no silent repair"):
        Artifact.from_dict(payload)


def test_hash_mismatch_is_rejected():
    artifact, _ = build_ground_truth()
    payload = artifact.to_dict()
    payload["content_digest"] = "forged"

    with pytest.raises(InvalidArtifact, match="content_digest mismatch"):
        Artifact.from_dict(payload)
