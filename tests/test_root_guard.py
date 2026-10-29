"""A root guard makes registering a root depend on a permission the caller holds."""

from __future__ import annotations

import pytest

from conservation_kernel import Actor, ActorKind, Artifact, ConservationKernel, Proposition
from conservation_kernel.enums import EpistemicStatus, OriginStatus
from conservation_kernel.errors import LedgerError, RootAdmissionError
from conservation_kernel.ledger import ConservationLedger


def root(artifact_id="root-1"):
    p = Proposition("p-1", "The kettle boiled.", EpistemicStatus.OBSERVATION, OriginStatus.EXTERNAL_ORIGINATED,
                    source_refs=("kitchen-log",))
    return Artifact(artifact_id, "x", (p,), Actor("bot", ActorKind.SYSTEM))


class Guard:
    """Answers `answer`, and counts what it was asked."""

    def __init__(self, answer=True):
        self.answer, self.asked = answer, []

    def __call__(self, artifact):
        self.asked.append(artifact.artifact_id)
        if isinstance(self.answer, Exception):
            raise self.answer
        return self.answer


def test_without_a_guard_registration_is_unchanged():
    kernel = ConservationKernel()
    kernel.register_root(root())
    assert [a.artifact_id for a in kernel.ledger.artifacts()] == ["root-1"]


def test_a_root_the_guard_authorizes_is_registered():
    guard = Guard(True)
    kernel = ConservationKernel(root_guard=guard)
    kernel.register_root(root())
    assert guard.asked == ["root-1"] and [a.artifact_id for a in kernel.ledger.artifacts()] == ["root-1"]


@pytest.mark.parametrize("answer", [False, None, 1, "yes", RuntimeError("no")])
def test_a_root_the_guard_does_not_authorize_is_refused_and_leaves_no_trace(answer):
    """Only True permits: a raise, a falsy answer, or a truthy non-True answer never does."""
    kernel = ConservationKernel(root_guard=Guard(answer))
    with pytest.raises(RootAdmissionError, match="root guard did not authorize"):
        kernel.register_root(root())
    assert kernel.ledger.artifacts() == ()


def test_the_ledger_called_directly_is_guarded_too():
    kernel = ConservationKernel(root_guard=Guard(False))
    with pytest.raises(RootAdmissionError, match="root guard did not authorize"):
        kernel.ledger.add_initial(root())
    assert kernel.ledger.artifacts() == ()


def test_the_guard_is_not_asked_when_the_kernel_already_refuses_the_root():
    """An authorization that is used up (a one-shot guard) is not spent on a root that would be refused anyway."""
    guard = Guard(True)
    kernel = ConservationKernel(root_guard=guard)
    forged = Proposition("p-f", "The board approved.", EpistemicStatus.FACT, OriginStatus.HUMAN_ORIGINATED, source_refs=("minutes",))
    with pytest.raises(RootAdmissionError, match="must cite evidence"):
        kernel.register_root(Artifact("root-f", "x", (forged,), Actor("bot", ActorKind.SYSTEM)))
    assert guard.asked == []
    kernel.register_root(root("root-2"))
    guard.asked.clear()
    with pytest.raises(LedgerError, match="duplicate"):
        kernel.register_root(root("root-2"))
    assert guard.asked == []


def test_a_snapshot_still_restores_with_a_guard_in_place():
    """Restoring rebuilds a ledger that was already registered; it does not ask for permission again."""
    source = ConservationKernel()
    source.register_root(root())
    restored = ConservationLedger.restore(source.ledger.snapshot())
    assert [a.artifact_id for a in restored.artifacts()] == ["root-1"]


def test_a_guard_and_a_supplied_ledger_cannot_both_be_given_to_the_kernel():
    with pytest.raises(ValueError, match="to the ledger you supply"):
        ConservationKernel(ledger=ConservationLedger(), root_guard=Guard())
    kernel = ConservationKernel(ledger=ConservationLedger(root_guard=Guard(False)))
    with pytest.raises(RootAdmissionError):
        kernel.register_root(root())
