"""Persistence and restart.

Before 2026-09-08 the ledger and registry were in memory only: a restart
lost every artifact, transformation, report, evidence record and
authorization, and afterwards nothing could tell a verified lineage from a
hand-registered one. A kernel now snapshots and restores, and on restore
re-admits every root and re-verifies every transformation.
"""
from __future__ import annotations

import json

import pytest

from conservation_kernel import (
    Actor, ActorKind, Artifact, AuthorityStatus, AuthorizationEvent, ConservationKernel, DeclaredChange,
    Dimension, EpistemicStatus, EvidenceRegistry, OriginStatus, Proposition, TransformationRecord, TransitionKind,
)
from conservation_kernel.errors import InvalidEvent, SnapshotIntegrityError


def _lineage(kernel=None):
    k = kernel or ConservationKernel()
    p = Proposition("p-in", "Sensor reading 42.", EpistemicStatus.INFERENCE, OriginStatus.MACHINE_ORIGINATED)
    root = Artifact("in-1", "sensor", (p,), Actor("sensor", ActorKind.SYSTEM))
    k.register_root(root)
    q = Proposition("p-out", "Reading is nominal.", EpistemicStatus.DECISION, OriginStatus.MACHINE_ORIGINATED,
                    parent_proposition_ids=("p-in",), derivation_method="rule")
    out = Artifact("out-1", "derived", (p, q), Actor("model", ActorKind.MODEL), parent_artifact_ids=("in-1",), version=2)
    record = TransformationRecord(
        transformation_id="t-1", input_artifact_ids=("in-1",), output_artifact_id="out-1",
        transformer=Actor("model", ActorKind.MODEL), transformation_type="DERIVE",
        declared_changes=(
            DeclaredChange("out-1", Dimension.CONTENT, root.content_digest, out.content_digest, "derived", TransitionKind.DERIVATION),
            DeclaredChange("p-out", Dimension.LINEAGE, "absent", "present", "new", TransitionKind.DERIVATION),
        ),
        input_hashes=(root.artifact_digest,), output_hash=out.artifact_digest, reason="test")
    result = k.submit(root, out, record)
    assert result.accepted, [v.to_dict() for v in result.violations]
    return k


def test_a_snapshot_round_trips_and_the_lineage_reconstructs_after_restart(tmp_path):
    k = _lineage()
    k.save(tmp_path / "kernel.json")
    restored = ConservationKernel.load(tmp_path / "kernel.json")            # "restart"
    rec = restored.reconstruct("out-1")
    assert rec.root_artifact_ids == ("in-1",) and rec.transformation_ids_in_order == ("t-1",)
    assert [r.transformation_id for r in restored.ledger.reports()] == ["t-1"]
    assert restored.snapshot()["ledger"] == k.snapshot()["ledger"]


def test_a_snapshot_whose_bytes_were_altered_is_refused(tmp_path):
    k = _lineage()
    path = tmp_path / "kernel.json"
    k.save(path)
    body = json.loads(path.read_text())
    body["ledger"]["artifacts"][0]["content"] = "rewritten"
    path.write_text(json.dumps(body))
    with pytest.raises(SnapshotIntegrityError, match="digest does not recompute"):
        ConservationKernel.load(path)


def test_a_hand_written_lineage_that_would_not_verify_is_refused_on_restore():
    k = _lineage()
    snap = k.snapshot()
    snap.pop("snapshot_digest")                                            # a writer who skips the digest
    # Upgrade the derived proposition's authority in the stored output artifact.
    out = next(a for a in snap["ledger"]["artifacts"] if a["artifact_id"] == "out-1")
    for prop in out["propositions"]:
        if prop["proposition_id"] == "p-out":
            prop["authority"] = AuthorityStatus.EXECUTED.value
            prop["authorization_refs"] = ["auth-nope"]
    out["content_digest"] = None
    out["artifact_digest"] = None            # let digests recompute
    with pytest.raises(SnapshotIntegrityError):
        ConservationKernel.from_snapshot(snap)


def test_a_forged_root_in_a_snapshot_is_refused_on_restore():
    k = _lineage()
    snap = k.snapshot()
    snap.pop("snapshot_digest")
    snap["ledger"]["artifacts"].append(Artifact(
        "root-forged", "x",
        (Proposition("p-forged", "Approved.", EpistemicStatus.DECISION, OriginStatus.HUMAN_ORIGINATED,
                     authority=AuthorityStatus.EXECUTED, authorization_refs=("auth-does-not-exist",)),),
        Actor("bot", ActorKind.HUMAN)).to_dict())
    with pytest.raises(SnapshotIntegrityError, match="root root-forged would not be admitted"):
        ConservationKernel.from_snapshot(snap)
    # Without re-verification the forged root is loaded: the flag exists for
    # offline forensics, and its name says what it skips.
    loaded = ConservationKernel.from_snapshot(snap, reverify=False)
    assert "root-forged" in [a.artifact_id for a in loaded.ledger.artifacts()]


def test_trusted_humans_are_enforced_on_restore_too():
    registry = EvidenceRegistry()
    registry.add_authorization(AuthorizationEvent(
        authorization_id="auth-1", authorized_by=Actor("autonomous-agent", ActorKind.HUMAN), subject_id="p",
        transition_kind=TransitionKind.EPISTEMIC_PROMOTION, from_value="UNKNOWN", to_value="FACT", reason="self"))
    snap = ConservationKernel(registry=registry).snapshot()
    with pytest.raises(InvalidEvent, match="does not recognise"):
        ConservationKernel.from_snapshot(snap, trusted_humans={"reviewer-1"})
    assert ConservationKernel.from_snapshot(snap).registry.authorization("auth-1") is not None


def test_work_continues_after_restart_on_the_restored_ledger():
    k = _lineage()
    restored = ConservationKernel.from_snapshot(k.snapshot())
    out = restored.ledger.artifact("out-1")
    p_in, p_out = out.propositions
    r = Proposition("p-next", "Escalate.", EpistemicStatus.DECISION, OriginStatus.MACHINE_ORIGINATED,
                    parent_proposition_ids=("p-out",), derivation_method="rule")
    nxt = Artifact("out-2", "next", (p_in, p_out, r), Actor("model", ActorKind.MODEL), parent_artifact_ids=("out-1",), version=3)
    record = TransformationRecord(
        transformation_id="t-2", input_artifact_ids=("out-1",), output_artifact_id="out-2",
        transformer=Actor("model", ActorKind.MODEL), transformation_type="DERIVE",
        declared_changes=(
            DeclaredChange("out-2", Dimension.CONTENT, out.content_digest, nxt.content_digest, "derived", TransitionKind.DERIVATION),
            DeclaredChange("p-next", Dimension.LINEAGE, "absent", "present", "new", TransitionKind.DERIVATION),
        ),
        input_hashes=(out.artifact_digest,), output_hash=nxt.artifact_digest, reason="test")
    assert restored.submit(out, nxt, record).accepted
    assert restored.reconstruct("out-2").transformation_ids_in_order == ("t-1", "t-2")
