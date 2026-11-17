"""Backlog items 1 and 2: proposition metadata is frozen at every depth, and a stored digest is re-checked.

Before this, only the top level of `Proposition.metadata` was read-only. A nested list or dictionary could be changed
in place, and the digest taken when the artifact was built kept vouching for content that had since changed. The
kernel copied the caller's dictionary shallowly too, so the caller could reach in through the original.
"""

from __future__ import annotations

import json

import pytest

from conservation_kernel import (
    Actor, ActorKind, Artifact, ConservationKernel, EpistemicStatus, OriginStatus, Proposition, TransformationRecord,
)
from conservation_kernel.cns_connector import _artifact_ref
from conservation_kernel.errors import InvalidArtifact, LedgerError

BOT = Actor("bot", ActorKind.SYSTEM)


def _meta():
    return {"top": 1, "outer": {"inner": ["a", {"deep": [1, 2]}]}, "items": [{"k": "v"}]}


def _prop(metadata=None, pid="p-1"):
    return Proposition(pid, "Queue is slow.", EpistemicStatus.INFERENCE, OriginStatus.MACHINE_ORIGINATED,
                       source_refs=("log",), metadata=_meta() if metadata is None else metadata)


def _artifact(metadata=None, aid="a-1", parents=()):
    return Artifact(aid, "x", (_prop(metadata),), BOT, parent_artifact_ids=parents)


def _kernel():
    return ConservationKernel(root_guard=lambda artifact: True, allow_unguarded_evidence=True)


def _tamper(artifact):
    """Stand in for any route that gets a change past the freeze: swap in different metadata, keep the stored digest."""
    object.__setattr__(artifact.propositions[0], "metadata", {"top": "TAMPERED"})


@pytest.mark.parametrize("change", [
    lambda m: m.__setitem__("top", 2),
    lambda m: m["outer"].__setitem__("new", 1),
    lambda m: m["outer"]["inner"].append("x"),
    lambda m: m["outer"]["inner"][1]["deep"].append(3),
    lambda m: m["items"][0].__setitem__("k", "changed"),
    lambda m: m["items"].append({}),
])
def test_no_depth_of_metadata_can_be_changed(change):
    metadata = _prop().metadata
    with pytest.raises((TypeError, AttributeError)):
        change(metadata)


def test_changing_the_callers_original_cannot_reach_the_proposition():
    original = _meta()
    artifact = _artifact(original)
    digest = artifact.artifact_digest
    original["outer"]["inner"].append("TAMPERED")
    original["items"][0]["k"] = "changed"
    original["top"] = 99
    assert artifact.propositions[0].metadata["top"] == 1
    assert "TAMPERED" not in artifact.propositions[0].metadata["outer"]["inner"]
    artifact.verify_digest()
    assert artifact.artifact_digest == digest


def test_the_digest_and_json_round_trip_are_unchanged_by_freezing():
    artifact = _artifact()
    again = Artifact.from_json(artifact.to_json())
    assert again.artifact_digest == artifact.artifact_digest
    assert again == artifact
    assert json.loads(artifact.to_json())["propositions"][0]["metadata"] == _meta()


def test_metadata_in_to_dict_is_plain_and_editing_it_does_not_touch_the_artifact():
    artifact = _artifact()
    out = artifact.to_dict()["propositions"][0]["metadata"]
    out["outer"]["inner"].append("x")
    artifact.verify_digest()
    assert "x" not in artifact.propositions[0].metadata["outer"]["inner"]


def test_a_self_referencing_metadata_is_refused_not_crashed():
    loop = {}
    loop["me"] = loop
    with pytest.raises(InvalidArtifact):
        _prop(loop)


def test_a_stale_digest_is_caught_by_verify_digest():
    artifact = _artifact()
    _tamper(artifact)
    with pytest.raises(InvalidArtifact, match="no longer matches"):
        artifact.verify_digest()


def test_register_root_refuses_a_stale_digest():
    kernel = _kernel()
    artifact = _artifact()
    _tamper(artifact)
    with pytest.raises(LedgerError, match="no longer matches"):
        kernel.register_root(artifact)
    assert kernel.ledger.artifacts() == ()


def _setup_pair():
    kernel = _kernel()
    root = _artifact(aid="root-1")
    kernel.register_root(root)
    child = _artifact(aid="child-1", parents=("root-1",))
    record = TransformationRecord("t-1", ("root-1",), "child-1", BOT, "x", (), (root.artifact_digest,),
                                  child.artifact_digest, reason="noop")
    return kernel, root, child, record


def test_submit_rejects_an_output_changed_after_its_digest_was_taken():
    kernel, root, child, record = _setup_pair()
    _tamper(child)
    result = kernel.submit(root, child, record)
    assert not result.accepted
    assert any(v.code == "ARTIFACT_DIGEST_STALE" for v in result.violations)
    assert [a.artifact_id for a in kernel.ledger.artifacts()] == ["root-1"]


def test_submit_rejects_an_input_changed_after_its_digest_was_taken():
    kernel, root, child, record = _setup_pair()
    _tamper(root)
    result = kernel.submit(root, child, record)  # the ledger holds this very object, so only the digest re-check sees it
    assert not result.accepted
    assert any(v.code == "ARTIFACT_DIGEST_STALE" and v.subject_id == "root-1" for v in result.violations)


def test_the_honest_submission_is_still_accepted():
    kernel, root, child, record = _setup_pair()
    assert kernel.submit(root, child, record).accepted


def test_snapshot_refuses_when_a_held_artifact_no_longer_matches_its_digest():
    kernel = _kernel()
    artifact = _artifact()
    kernel.register_root(artifact)
    kernel.snapshot()
    _tamper(artifact)
    with pytest.raises(LedgerError, match="no longer matches"):
        kernel.snapshot()


def test_the_cns_hand_off_refuses_a_stale_digest():
    artifact = _artifact()
    assert _artifact_ref(artifact)["artifact_digest"] == artifact.artifact_digest
    _tamper(artifact)
    with pytest.raises(InvalidArtifact):
        _artifact_ref(artifact)
