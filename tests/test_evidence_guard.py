"""An evidence guard makes adding evidence depend on a permission the caller holds.

Evidence is what the verifier trusts to approve strong claims, and `add_evidence` used to ask nobody. The guard is
optional: with none, behaviour is exactly as before.
"""

from __future__ import annotations

import pytest

from conservation_kernel import Actor, ActorKind, ConservationKernel
from conservation_kernel.enums import EvidenceKind
from conservation_kernel.errors import InvalidEvent
from conservation_kernel.events import EvidenceRecord
from conservation_kernel.registry import EvidenceRegistry

HUMAN = Actor("alice", ActorKind.HUMAN)


def evidence(evidence_id="ev-1", subject="p-1"):
    return EvidenceRecord(evidence_id, subject, EvidenceKind.INDEPENDENT_VERIFICATION, HUMAN, independent=True)


class Guard:
    """Answers `answer`, and counts what it was asked."""

    def __init__(self, answer=True):
        self.answer, self.asked = answer, []

    def __call__(self, record):
        self.asked.append(record.evidence_id)
        if isinstance(self.answer, Exception):
            raise self.answer
        return self.answer


def test_without_a_guard_adding_evidence_is_unchanged():
    registry = EvidenceRegistry()
    registry.add_evidence(evidence())
    assert registry.evidence("ev-1") is not None
    assert registry.has_evidence_guard is False


def test_evidence_the_guard_authorizes_is_added_and_the_guard_was_asked_once():
    guard = Guard(True)
    registry = EvidenceRegistry(evidence_guard=guard)
    registry.add_evidence(evidence())
    assert guard.asked == ["ev-1"] and registry.evidence("ev-1") is not None


@pytest.mark.parametrize("answer", [False, None, 1, "yes", RuntimeError("no")])
def test_evidence_the_guard_does_not_authorize_is_refused_and_leaves_the_registry_byte_identical(answer):
    """Only True permits: a raise, a falsy answer, or a truthy non-True answer never does."""
    registry = EvidenceRegistry(evidence_guard=Guard(answer))
    before = registry.snapshot()
    with pytest.raises(InvalidEvent, match="evidence guard did not authorize"):
        registry.add_evidence(evidence())
    assert registry.evidence("ev-1") is None
    assert registry.snapshot() == before


def test_a_duplicate_is_refused_before_the_guard_is_asked_so_a_one_use_permission_is_not_spent():
    guard = Guard(True)
    registry = EvidenceRegistry(evidence_guard=guard)
    registry.add_evidence(evidence())
    with pytest.raises(InvalidEvent, match="duplicate evidence ID"):
        registry.add_evidence(evidence())
    assert guard.asked == ["ev-1"]


def test_the_guard_is_asked_about_each_record_and_can_say_yes_to_one_and_no_to_another():
    registry = EvidenceRegistry(evidence_guard=lambda record: record.evidence_id == "ev-ok")
    registry.add_evidence(evidence("ev-ok"))
    with pytest.raises(InvalidEvent):
        registry.add_evidence(evidence("ev-no"))
    assert registry.evidence("ev-ok") is not None and registry.evidence("ev-no") is None


def test_a_kernel_hands_its_guard_to_the_registry_it_builds_and_says_so():
    guard = Guard(False)
    kernel = ConservationKernel(allow_unguarded_roots=True, evidence_guard=guard)
    assert kernel.has_evidence_guard is True
    with pytest.raises(InvalidEvent, match="evidence guard did not authorize"):
        kernel.registry.add_evidence(evidence())
    assert guard.asked == ["ev-1"] and kernel.registry.evidence("ev-1") is None
    assert ConservationKernel(allow_unguarded_roots=True).has_evidence_guard is False


def test_a_guard_and_a_supplied_registry_cannot_both_be_given_to_the_kernel():
    with pytest.raises(ValueError, match="evidence guard to the registry you supply"):
        ConservationKernel(registry=EvidenceRegistry(), allow_unguarded_roots=True, evidence_guard=Guard())


def test_a_registry_you_supply_with_its_own_guard_is_used_as_it_is():
    guard = Guard(True)
    kernel = ConservationKernel(registry=EvidenceRegistry(evidence_guard=guard), allow_unguarded_roots=True)
    assert kernel.has_evidence_guard is True
    kernel.registry.add_evidence(evidence())
    assert guard.asked == ["ev-1"]


def test_a_snapshot_restores_with_a_guard_in_place_and_the_guard_governs_only_later_evidence():
    source = EvidenceRegistry()
    source.add_evidence(evidence("ev-old"))
    guard = Guard(True)
    restored = EvidenceRegistry.restore(source.snapshot(), evidence_guard=guard)
    assert restored.evidence("ev-old") is not None and guard.asked == []
    restored.add_evidence(evidence("ev-new"))
    assert guard.asked == ["ev-new"]


def test_a_kernel_restored_from_a_snapshot_can_be_given_a_guard_for_later_evidence():
    kernel = ConservationKernel(allow_unguarded_roots=True)
    kernel.registry.add_evidence(evidence("ev-old"))
    guard = Guard(False)
    restored = ConservationKernel.from_snapshot(kernel.snapshot(), allow_unguarded_roots=True, evidence_guard=guard)
    assert restored.has_evidence_guard is True and restored.registry.evidence("ev-old") is not None
    with pytest.raises(InvalidEvent):
        restored.registry.add_evidence(evidence("ev-new"))
    assert guard.asked == ["ev-new"]


def test_a_refused_record_cannot_support_a_root_that_cites_it():
    """End to end: the verifier only counts evidence the registry holds, so a refused record supports nothing."""
    from conservation_kernel import Artifact, Proposition
    from conservation_kernel.enums import EpistemicStatus, OriginStatus

    kernel = ConservationKernel(allow_unguarded_roots=True, evidence_guard=Guard(False))
    with pytest.raises(InvalidEvent):
        kernel.registry.add_evidence(evidence("ev-1", "p-1"))
    proposition = Proposition("p-1", "The kettle boiled.", EpistemicStatus.FACT, OriginStatus.EXTERNAL_ORIGINATED,
                              evidence_refs=("ev-1",))
    artifact = Artifact("root-1", "x", (proposition,), Actor("bot", ActorKind.SYSTEM))
    assert any("evidence_refs not in registry" in reason for reason in kernel.admit_root(artifact))
