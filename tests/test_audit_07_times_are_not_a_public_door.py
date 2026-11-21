"""Audit defect 7: `ledger.record_times` let any caller stamp history with a time of their choosing.

A restore judges each root and transformation as of its stamp, so an unstamped root given a stamp in the year 2000
sat outside every revocation or expiry recorded after it. Only the kernel's own reload stamps history now, once.
"""

from __future__ import annotations

import pytest

from conservation_kernel import Actor, ActorKind, Artifact, ConservationKernel, EpistemicStatus, OriginStatus, Proposition
from conservation_kernel.errors import LedgerError

BOT = Actor("bot", ActorKind.SYSTEM)


def _root():
    return Artifact("root-1", "x", (Proposition("p-1", "T.", EpistemicStatus.INFERENCE, OriginStatus.MACHINE_ORIGINATED,
                                                source_refs=("log",)),), BOT)


def _clock():
    return "2026-01-02T00:00:00+00:00"


def test_a_caller_cannot_backdate_a_root_through_the_public_ledger():
    kernel = ConservationKernel(root_guard=lambda artifact: True, allow_unguarded_evidence=True)
    kernel.ledger.add_initial(_root())                              # added with no stamp
    assert not hasattr(kernel.ledger, "record_times")
    assert kernel.ledger.admitted_at("root-1") is None


def test_the_kernels_own_reload_still_stamps_unstamped_history_once_with_its_clock():
    source = ConservationKernel(root_guard=lambda artifact: True, allow_unguarded_evidence=True)
    source.ledger.add_initial(_root())
    restored = ConservationKernel.from_snapshot(source.snapshot(), root_guard=lambda artifact: True,
                                                allow_unguarded_evidence=True, clock=_clock)
    assert restored.ledger.admitted_at("root-1") == "2026-01-02T00:00:00+00:00"


def _second_root():
    return Artifact("root-2", "y", (Proposition("p-2", "U.", EpistemicStatus.INFERENCE, OriginStatus.MACHINE_ORIGINATED,
                                                source_refs=("log",)),), BOT)


def test_a_root_cannot_be_given_a_time_earlier_than_one_the_ledger_already_holds():
    kernel = ConservationKernel(root_guard=lambda artifact: True, allow_unguarded_evidence=True)
    kernel.ledger.add_initial(_root(), admitted_at="2026-01-02T00:00:00+00:00")
    with pytest.raises(LedgerError):
        kernel.ledger.add_initial(_second_root(), admitted_at="2026-01-01T00:00:00+00:00")
    assert kernel.ledger.admitted_at("root-2") is None
    kernel.ledger.add_initial(_second_root(), admitted_at="2026-01-02T00:00:00+00:00")  # the same moment is not earlier
    assert kernel.ledger.admitted_at("root-2") == "2026-01-02T00:00:00+00:00"
