"""Audit defect 5: `evidence_guard` defaulted to None, so a kernel with a root guard still took caller-made evidence.

Any caller could add an INDEPENDENT_VERIFICATION record that declares itself independent, and the verifier would count it.
A kernel now refuses to be built without an evidence guard unless `allow_unguarded_evidence=True` says that is
deliberate, the way `allow_unguarded_roots` works for roots.
"""

from __future__ import annotations

import pytest

from conservation_kernel import Actor, ActorKind, ConservationKernel
from conservation_kernel.enums import EvidenceKind
from conservation_kernel.errors import UnguardedKernelError
from conservation_kernel.events import EvidenceRecord
from conservation_kernel.registry import EvidenceRegistry

MACHINE = Actor("bot", ActorKind.SYSTEM)


def allow(record):
    return True


def test_a_kernel_with_a_root_guard_and_no_evidence_guard_cannot_be_built():
    with pytest.raises(UnguardedKernelError, match="evidence_guard"):
        ConservationKernel(root_guard=allow)


def test_so_caller_made_independent_evidence_never_reaches_a_registry_nobody_guards():
    with pytest.raises(UnguardedKernelError):
        kernel = ConservationKernel(root_guard=allow)
        kernel.registry.add_evidence(
            EvidenceRecord("ev-1", "p-1", EvidenceKind.INDEPENDENT_VERIFICATION, MACHINE, independent=True))


def test_saying_so_builds_it_and_it_reports_no_guard():
    kernel = ConservationKernel(root_guard=allow, allow_unguarded_evidence=True)
    assert kernel.has_evidence_guard is False


def test_an_evidence_guard_builds_it_without_the_flag():
    kernel = ConservationKernel(root_guard=allow, evidence_guard=allow)
    assert kernel.has_evidence_guard is True


def test_a_supplied_registry_is_held_to_the_same_rule():
    with pytest.raises(UnguardedKernelError, match="evidence_guard"):
        ConservationKernel(registry=EvidenceRegistry(), root_guard=allow)
    ConservationKernel(registry=EvidenceRegistry(evidence_guard=allow), root_guard=allow)
    ConservationKernel(registry=EvidenceRegistry(), root_guard=allow, allow_unguarded_evidence=True)


def test_the_two_flags_are_independent():
    with pytest.raises(UnguardedKernelError, match="root_guard"):
        ConservationKernel(evidence_guard=allow)
    with pytest.raises(UnguardedKernelError, match="evidence_guard"):
        ConservationKernel(allow_unguarded_roots=True)


def test_a_restored_kernel_is_held_to_it_too():
    snapshot = ConservationKernel(allow_unguarded_roots=True, allow_unguarded_evidence=True).snapshot()
    with pytest.raises(UnguardedKernelError, match="evidence_guard"):
        ConservationKernel.from_snapshot(snapshot, allow_unguarded_roots=True)
    ConservationKernel.from_snapshot(snapshot, allow_unguarded_roots=True, evidence_guard=allow)
    ConservationKernel.from_snapshot(snapshot, allow_unguarded_roots=True, allow_unguarded_evidence=True)
