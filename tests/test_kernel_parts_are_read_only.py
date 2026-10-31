"""A kernel's registry and ledger are fixed when it is built.

`has_root_guard` and `has_evidence_guard` read the ledger and the registry the kernel holds. They were plain attributes,
so reassigning either one after the kernel was built (no private name needed) replaced a guarded part with an unguarded
one, and the guards the kernel advertised were gone. They are read-only now.
"""
from __future__ import annotations

import pytest

from conservation_kernel import ConservationKernel, EvidenceRegistry
from conservation_kernel.ledger import ConservationLedger


def guarded_kernel() -> ConservationKernel:
    return ConservationKernel(root_guard=lambda artifact: True, evidence_guard=lambda record: True)


def test_the_ledger_cannot_be_replaced_after_construction():
    kernel = guarded_kernel()
    ledger = kernel.ledger
    with pytest.raises(AttributeError):
        kernel.ledger = ConservationLedger()
    assert kernel.ledger is ledger and kernel.has_root_guard


def test_the_registry_cannot_be_replaced_after_construction():
    kernel = guarded_kernel()
    registry = kernel.registry
    with pytest.raises(AttributeError):
        kernel.registry = EvidenceRegistry()
    assert kernel.registry is registry and kernel.has_evidence_guard


def test_the_parts_are_still_there_to_read_and_use():
    kernel = ConservationKernel(allow_unguarded_roots=True)
    assert isinstance(kernel.ledger, ConservationLedger) and isinstance(kernel.registry, EvidenceRegistry)


def test_a_kernel_restored_from_a_snapshot_keeps_the_parts_it_was_given():
    kernel = ConservationKernel(allow_unguarded_roots=True)
    again = ConservationKernel.from_snapshot(kernel.snapshot(), allow_unguarded_roots=True)
    with pytest.raises(AttributeError):
        again.ledger = ConservationLedger()
