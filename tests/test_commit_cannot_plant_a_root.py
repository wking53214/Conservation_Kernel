"""The root guard cannot be walked around by committing a parentless artifact as if it were a transformation's output.

An artifact with no parents is a root. `add_initial` asks the root guard before taking one; `commit` used to take any
output whose result said PASS, and a result is a plain object the caller can write by hand.
"""

from __future__ import annotations

import pytest

from conservation_kernel import Actor, ActorKind, Artifact, ConservationKernel, Proposition
from conservation_kernel.enums import EpistemicStatus, OriginStatus
from conservation_kernel.errors import LedgerError
from conservation_kernel.events import TransformationRecord
from conservation_kernel.ledger import ConservationLedger
from conservation_kernel.result import VerificationResult, VerificationStatus

BOT = Actor("bot", ActorKind.SYSTEM)


def root(artifact_id="forged-1"):
    p = Proposition("p-1", "The kettle boiled.", EpistemicStatus.OBSERVATION, OriginStatus.EXTERNAL_ORIGINATED,
                    source_refs=("kitchen-log",))
    return Artifact(artifact_id, "x", (p,), BOT)


def handmade(artifact):
    """A transformation record and a PASS result written by hand, the way a caller with the ledger could write them."""
    record = TransformationRecord("t-1", (), artifact.artifact_id, BOT, "x", (), (), "h")
    return record, VerificationResult("t-1", (), artifact.artifact_id, VerificationStatus.PASS)


def test_a_parentless_artifact_cannot_be_committed_past_a_closed_root_guard():
    kernel = ConservationKernel(root_guard=lambda artifact: False, allow_unguarded_evidence=True)
    artifact = root()
    record, result = handmade(artifact)
    with pytest.raises(LedgerError, match="no parents"):
        kernel.ledger.commit(artifact, record, result)
    assert kernel.ledger.artifacts() == ()
    assert kernel.ledger.transformations() == ()
    assert kernel.ledger.reports() == ()


def test_the_refusal_leaves_the_ledger_byte_identical():
    kernel = ConservationKernel(root_guard=lambda artifact: False, allow_unguarded_evidence=True)
    before = kernel.snapshot()
    artifact = root()
    record, result = handmade(artifact)
    with pytest.raises(LedgerError):
        kernel.ledger.commit(artifact, record, result)
    assert kernel.snapshot() == before


def test_a_ledger_with_no_guard_refuses_it_too_because_a_root_has_its_own_door():
    ledger = ConservationLedger()
    artifact = root()
    record, result = handmade(artifact)
    with pytest.raises(LedgerError, match="add_initial"):
        ledger.commit(artifact, record, result)
    assert ledger.artifacts() == ()


def test_the_door_for_roots_still_works_and_still_asks_the_guard():
    allowed = ConservationKernel(root_guard=lambda artifact: True, allow_unguarded_evidence=True)
    allowed.register_root(root("ok-1"))
    assert [a.artifact_id for a in allowed.ledger.artifacts()] == ["ok-1"]
    shut = ConservationKernel(root_guard=lambda artifact: False, allow_unguarded_evidence=True)
    with pytest.raises(LedgerError, match="root guard did not authorize"):
        shut.ledger.add_initial(root("no-1"))
    assert shut.ledger.artifacts() == ()


def test_a_child_of_a_registered_root_cannot_commit_on_a_hand_written_result():
    ledger = ConservationLedger(root_guard=lambda artifact: True)
    ledger.add_initial(root("parent-1"))
    child = Artifact("child-1", "x", root("c").propositions, BOT, parent_artifact_ids=("parent-1",))
    record = TransformationRecord("t-2", ("parent-1",), "child-1", BOT, "x", (), ("h",), "h")
    result = VerificationResult("t-2", ("parent-1",), "child-1", VerificationStatus.PASS)
    with pytest.raises(LedgerError, match="not produced by the verifier"):
        ledger.commit(child, record, result)
    assert [a.artifact_id for a in ledger.artifacts()] == ["parent-1"]


def test_the_kernels_own_submit_with_no_inputs_is_still_rejected_and_adds_nothing():
    kernel = ConservationKernel(root_guard=lambda artifact: False, allow_unguarded_evidence=True)
    artifact = root("via-submit")
    record = TransformationRecord("t-9", (), artifact.artifact_id, BOT, "x", (), (), "h")
    result = kernel.submit((), artifact, record)
    assert not result.accepted
    assert kernel.ledger.artifacts() == ()
