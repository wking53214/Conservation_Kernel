"""The kernel records when it decided, and re-verifies its history as of then.

An authorization that can expire or be revoked is only meaningful against a time, and the
time has to be one the transformer cannot choose: `TransformationRecord.created_at` is the
transformer's own claim. So the kernel stamps each decision with its own clock (a
deployment hands it the ledger's), keeps the stamp in the ledger and the snapshot, and on
restore re-verifies every transformation and re-admits every root as of the moment it
was first accepted. Without the stamp a restore would judge history against today, and an
authorization that has since expired would make an accepted lineage fail to reload.
"""
from __future__ import annotations

import json

from conservation_kernel import (
    Actor, ActorKind, Artifact, ConservationKernel, DeclaredChange, Dimension, EpistemicStatus, IndependentVerifier,
    OriginStatus, Proposition, TransformationRecord, TransitionKind,
)
from conservation_kernel.model import _digest, canonical_json

T1 = "2026-10-01T09:00:00+00:00"
T2 = "2026-10-02T09:00:00+00:00"


class _Clock:
    """A kernel clock the test moves by hand."""

    def __init__(self, now: str) -> None:
        self.now = now

    def __call__(self) -> str:
        return self.now


def _lineage(clock):
    k = ConservationKernel(allow_unguarded_roots=True, clock=clock)
    p = Proposition("p-in", "Sensor reading 42.", EpistemicStatus.INFERENCE, OriginStatus.MACHINE_ORIGINATED)
    root = Artifact("in-1", "sensor", (p,), Actor("sensor", ActorKind.SYSTEM))
    k.register_root(root)
    clock.now = T2
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
        input_hashes=(root.artifact_digest,), output_hash=out.artifact_digest, reason="test",
        created_at="1999-01-01T00:00:00+00:00")        # the transformer's claim; the kernel does not use it
    result = k.submit(root, out, record)
    assert result.accepted, [v.to_dict() for v in result.violations]
    return k, root, out, record, result


def test_the_kernel_stamps_a_decision_with_its_own_clock_not_the_transformers():
    k, _, _, _, result = _lineage(_Clock(T1))
    assert result.verified_at == T2
    assert k.ledger.verified_at("t-1") == T2


def test_the_kernel_stamps_when_it_admitted_a_root():
    k, *_ = _lineage(_Clock(T1))
    assert k.ledger.admitted_at("in-1") == T1


def test_the_stamps_survive_a_snapshot_and_reverify_uses_them(tmp_path):
    k, *_ = _lineage(_Clock(T1))
    k.save(tmp_path / "kernel.json")
    seen = []

    class _Spy(IndependentVerifier):
        def verify(self, input_artifacts, output, record, registry):     # the pre-existing signature still works
            seen.append(registry.as_of)
            return super().verify(input_artifacts, output, record, registry)

    restored = ConservationKernel.load(tmp_path / "kernel.json", allow_unguarded_roots=True, reverify=False)
    restored.verifier = _Spy()
    restored.reverify()
    assert seen == [T2]
    assert restored.ledger.admitted_at("in-1") == T1 and restored.ledger.verified_at("t-1") == T2


def test_a_verifier_called_directly_reports_the_time_it_was_given_and_none_when_given_none():
    k, root, out, record, _ = _lineage(_Clock(T1))
    assert IndependentVerifier().verify(root, out, record, k.registry, as_of=T1).verified_at == T1
    unstamped = IndependentVerifier().verify(root, out, record, k.registry)
    assert unstamped.verified_at is None
    assert "verified_at" not in unstamped.to_dict()          # the result's shape is unchanged when there is no stamp


def test_a_snapshot_written_before_stamps_existed_still_restores(tmp_path):
    k, *_ = _lineage(_Clock(T1))
    body = k.snapshot()
    body.pop("snapshot_digest")
    body["ledger"].pop("root_admitted_at", None)
    body["ledger"].pop("transformation_verified_at", None)
    for report in body["ledger"]["reports"]:
        report.pop("verified_at", None)
    body["snapshot_digest"] = _digest(canonical_json(body))
    path = tmp_path / "old.json"
    path.write_text(json.dumps(body))
    reloaded_at = "2026-10-03T09:00:00+00:00"
    restored = ConservationKernel.load(path, allow_unguarded_roots=True, clock=_Clock(reloaded_at))
    # Judged as of the reload, and given that time once, so a revocation recorded later cannot reach back over it.
    assert restored.ledger.verified_at("t-1") == reloaded_at and restored.ledger.admitted_at("in-1") == reloaded_at
    assert restored.reconstruct("out-1").transformation_ids_in_order == ("t-1",)
