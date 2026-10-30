"""Audit defect 4: a snapshot's evidence was loaded before the evidence guard was attached.

`EvidenceRegistry.restore` added every evidence record to an unguarded registry and only then set the guard, so planted
INDEPENDENT_VERIFICATION evidence in a snapshot file loaded under a deny-all guard while `has_evidence_guard` reported
True. When a guard is configured, the evidence a snapshot restores must pass it like any other.
"""

from __future__ import annotations

import pytest

from conservation_kernel import Actor, ActorKind, ConservationKernel
from conservation_kernel.enums import EvidenceKind
from conservation_kernel.errors import InvalidEvent
from conservation_kernel.events import EvidenceRecord
from conservation_kernel.registry import EvidenceRegistry

MACHINE = Actor("bot", ActorKind.SYSTEM)


def planted(evidence_id="ev-planted", subject="p-1"):
    return EvidenceRecord(evidence_id, subject, EvidenceKind.INDEPENDENT_VERIFICATION, MACHINE, independent=True)


def snapshot_with(*records):
    source = ConservationKernel(allow_unguarded_roots=True, allow_unguarded_evidence=True)
    for record in records:
        source.registry.add_evidence(record)
    return source.snapshot()


def test_planted_evidence_does_not_load_under_a_deny_all_guard():
    snapshot = snapshot_with(planted())
    with pytest.raises(InvalidEvent, match="evidence guard did not authorize"):
        ConservationKernel.from_snapshot(snapshot, allow_unguarded_roots=True, evidence_guard=lambda record: False)


def test_the_registry_alone_refuses_it_too_and_names_the_record():
    with pytest.raises(InvalidEvent, match="ev-planted"):
        EvidenceRegistry.restore(EvidenceRegistry().snapshot() | {"evidence": [planted().to_dict()]},
                                 evidence_guard=lambda record: False)


@pytest.mark.parametrize("answer", [None, 1, "yes", RuntimeError("no")])
def test_only_true_permits_on_restore_as_it_does_live(answer):
    def guard(record):
        if isinstance(answer, Exception):
            raise answer
        return answer
    with pytest.raises(InvalidEvent, match="evidence guard did not authorize"):
        EvidenceRegistry.restore(snapshot_with(planted())["registry"], evidence_guard=guard)


def test_the_guard_is_asked_about_each_restored_record_once_and_what_it_allows_loads():
    asked = []

    def guard(record):
        asked.append(record.evidence_id)
        return True

    restored = EvidenceRegistry.restore(snapshot_with(planted("ev-a"), planted("ev-b"))["registry"], evidence_guard=guard)
    assert asked == ["ev-a", "ev-b"]
    assert restored.evidence("ev-a") is not None and restored.evidence("ev-b") is not None
    assert restored.has_evidence_guard is True


def test_one_refused_record_refuses_the_whole_restore_rather_than_loading_the_rest():
    snapshot = snapshot_with(planted("ev-ok"), planted("ev-planted"))
    with pytest.raises(InvalidEvent, match="ev-planted"):
        ConservationKernel.from_snapshot(snapshot, allow_unguarded_roots=True,
                                         evidence_guard=lambda record: record.evidence_id == "ev-ok")


def test_a_snapshot_restores_unchanged_when_no_guard_is_configured():
    snapshot = snapshot_with(planted())
    restored = ConservationKernel.from_snapshot(snapshot, allow_unguarded_roots=True, allow_unguarded_evidence=True)
    assert restored.has_evidence_guard is False and restored.registry.evidence("ev-planted") is not None
    assert restored.snapshot() == snapshot
