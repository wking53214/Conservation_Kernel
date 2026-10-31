"""Audit defect 8: `ledger.record_rejection` took any result, so a hand-written verdict could sit in the history.

Nothing decides from reports, but an auditor reads them as what the verifier said. A report now has to carry the
verifier's proof for the record and output it names, and a ledger a kernel owns takes only its own registry's.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from conservation_kernel import (
    Actor, ActorKind, Artifact, ConservationKernel, EpistemicStatus, OriginStatus, Proposition, TransformationRecord,
)
from conservation_kernel.enums import VerificationStatus
from conservation_kernel.errors import LedgerError
from conservation_kernel.experiments import build_ground_truth, legitimate_transformation
from conservation_kernel.result import VerificationResult
from conservation_kernel.verifier import IndependentVerifier

BOT = Actor("bot", ActorKind.SYSTEM)


def _kernel_with_a_real_result():
    base, registry = build_ground_truth()
    kernel = ConservationKernel(registry=registry, root_guard=lambda artifact: True, allow_unguarded_evidence=True)
    kernel.register_root(base)
    output, record = legitimate_transformation(base, 1)
    result = kernel.verifier.verify(base, output, record, kernel.registry.at(kernel._now()))
    return kernel, output, record, result


def test_a_hand_written_verdict_is_not_taken_as_a_report():
    kernel, output, record, _ = _kernel_with_a_real_result()
    forged = VerificationResult("t-forged", ("root-1",), "child-x", VerificationStatus.PASS)
    with pytest.raises(LedgerError):
        kernel.ledger.record_rejection(forged, record, output)
    assert kernel.ledger.reports() == ()


def test_a_real_result_edited_afterwards_is_not_taken():
    kernel, output, record, result = _kernel_with_a_real_result()
    with pytest.raises(LedgerError):
        kernel.ledger.record_rejection(replace(result, status=VerificationStatus.REJECT), record, output)


def test_a_verdict_from_another_registry_is_not_this_kernels_report():
    kernel, output, record, _ = _kernel_with_a_real_result()
    base, other_registry = build_ground_truth()
    foreign = IndependentVerifier().verify(base, output, record, other_registry)
    with pytest.raises(LedgerError):
        kernel.ledger.record_rejection(foreign, record, output)


def test_the_verifiers_own_result_is_recorded():
    kernel, output, record, result = _kernel_with_a_real_result()
    kernel.ledger.record_rejection(result, record, output)
    assert kernel.ledger.reports() == (result,)


def test_the_kernels_submit_still_leaves_a_report_of_a_rejection():
    kernel = ConservationKernel(root_guard=lambda artifact: True, allow_unguarded_evidence=True)
    root = Artifact("root-1", "x", (Proposition("p-1", "T.", EpistemicStatus.INFERENCE, OriginStatus.MACHINE_ORIGINATED,
                                                source_refs=("log",)),), BOT)
    kernel.register_root(root)
    lifted = Artifact("child-1", "x", (Proposition("p-1", "T.", EpistemicStatus.FACT, OriginStatus.MACHINE_ORIGINATED,
                                                   source_refs=("log",)),), BOT, parent_artifact_ids=("root-1",))
    record = TransformationRecord("t-1", ("root-1",), "child-1", BOT, "x", (), (root.artifact_digest,),
                                  lifted.artifact_digest, reason="lift")
    assert not kernel.submit(root, lifted, record).accepted
    assert len(kernel.ledger.reports()) == 1
