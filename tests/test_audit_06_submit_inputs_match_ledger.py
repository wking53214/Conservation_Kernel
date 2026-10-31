"""Audit defect 6: `submit` verified a "before" artifact the caller handed in, not the one the ledger holds.

The ledger only checked that the output's parent ids were registered. A caller could hand in a doctored "before" with a
registered root's id (here an INFERENCE shown as a FACT with real evidence), have the kernel verify against it, and
commit a FACT child of an INFERENCE root with no escalation declared. The honest submission of the same change is
rejected, and a restore re-verifies against the ledger's real artifacts and refuses the whole file. An input that
shares an id with a ledger artifact must now be that artifact.
"""

from __future__ import annotations

import pytest

from conservation_kernel import (
    Actor, ActorKind, Artifact, ConservationKernel, EpistemicStatus, EvidenceKind, EvidenceRecord, OriginStatus,
    Proposition, TransformationRecord,
)
from conservation_kernel.errors import LedgerError

BOT = Actor("bot", ActorKind.SYSTEM)


def _kernel():
    kernel = ConservationKernel(root_guard=lambda artifact: True, allow_unguarded_evidence=True)
    kernel.registry.add_evidence(EvidenceRecord("ev-x", "p-1", EvidenceKind.SOURCE_OBSERVATION, BOT))
    return kernel


def _prop(status, evidence=()):
    return Proposition("p-1", "Queue is slow.", status, OriginStatus.MACHINE_ORIGINATED, source_refs=("log",),
                       evidence_refs=evidence)


def _setup():
    kernel = _kernel()
    real = Artifact("root-1", "x", (_prop(EpistemicStatus.INFERENCE),), BOT)
    kernel.register_root(real)
    fact = _prop(EpistemicStatus.FACT, ("ev-x",))
    doctored = Artifact("root-1", "x", (fact,), BOT)               # the registered root's id, other content
    child = Artifact("child-1", "x", (fact,), BOT, parent_artifact_ids=("root-1",))
    return kernel, real, doctored, child


def _record(before, child):
    return TransformationRecord("t-1", ("root-1",), "child-1", BOT, "x", (), (before.artifact_digest,),
                                child.artifact_digest, reason="noop")


def test_a_doctored_before_cannot_carry_a_lift_into_the_ledger():
    kernel, real, doctored, child = _setup()
    with pytest.raises(LedgerError, match="root-1"):
        kernel.submit(doctored, child, _record(doctored, child))
    assert [a.artifact_id for a in kernel.ledger.artifacts()] == ["root-1"]
    assert kernel.ledger.transformations() == ()
    assert kernel.ledger.artifact("root-1") == real


def test_the_honest_submission_of_the_same_change_is_still_rejected_by_the_verifier():
    kernel, real, doctored, child = _setup()
    result = kernel.submit(real, child, _record(real, child))
    assert not result.accepted


def test_the_ledgers_own_artifact_is_accepted_as_an_input_as_before():
    kernel = _kernel()
    base = Artifact("root-1", "x", (_prop(EpistemicStatus.INFERENCE),), BOT)
    kernel.register_root(base)
    same = Artifact("child-1", "x", (_prop(EpistemicStatus.INFERENCE),), BOT, parent_artifact_ids=("root-1",))
    assert kernel.submit(base, same, _record(base, same)).accepted


def test_a_sequence_of_inputs_is_held_to_the_same_rule():
    kernel, real, doctored, child = _setup()
    with pytest.raises(LedgerError, match="root-1"):
        kernel.submit([doctored], child, _record(doctored, child))
