import json

import pytest

from conservation_kernel.errors import InvalidArtifact
from conservation_kernel.experiments import build_ground_truth
from conservation_kernel.model import Artifact, canonical_json


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


@pytest.mark.parametrize(
    ("metadata", "message"),
    [
        ({1: "numeric key"}, "canonical mappings require string keys"),
        ({"unordered": {"a", "b"}}, "sets are not supported"),
        ({"not-a-number": float("nan")}, "non-finite floats are not supported"),
    ],
)
def test_ambiguous_metadata_is_rejected_instead_of_normalized(metadata, message):
    artifact, _ = build_ground_truth()
    proposition = artifact.propositions[0]

    with pytest.raises(InvalidArtifact, match=message):
        type(proposition)(
            proposition_id=proposition.proposition_id,
            text=proposition.text,
            epistemic_status=proposition.epistemic_status,
            origin=proposition.origin,
            authority=proposition.authority,
            uncertainty=proposition.uncertainty,
            temporal=proposition.temporal,
            evidence_refs=proposition.evidence_refs,
            authorization_refs=proposition.authorization_refs,
            canonical_state=proposition.canonical_state,
            parent_proposition_ids=proposition.parent_proposition_ids,
            source_refs=proposition.source_refs,
            derivation_method=proposition.derivation_method,
            metadata=metadata,
        )


def test_mapping_order_is_canonical_but_list_order_remains_identity_relevant():
    artifact, _ = build_ground_truth()
    first = dict(artifact.propositions[0].metadata)
    reordered = dict(reversed(tuple(first.items())))
    assert canonical_json(first) == canonical_json(reordered)
    assert canonical_json(["a", "b"]) != canonical_json(["b", "a"])
