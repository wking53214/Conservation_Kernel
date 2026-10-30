"""Audit defect 1: `ConservationLedger.commit` took a hand-built VerificationResult(PASS).

A child that lifts an INFERENCE to a canonical FACT, citing authorizations and evidence that do not exist, is
REJECTED by the verifier. But `commit` trusted whatever result the caller handed it, so writing the PASS by hand put
that child in the ledger anyway. A commit must rest on a result the kernel's own verifier produced.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from conservation_kernel import (
    Actor, ActorKind, Artifact, AuthorityStatus, CanonicalState, ConservationKernel, EpistemicStatus,
    OriginStatus, Proposition, TransformationRecord,
)
from conservation_kernel.enums import VerificationStatus
from conservation_kernel.errors import LedgerError
from conservation_kernel.experiments import build_ground_truth, legitimate_transformation
from conservation_kernel.result import VerificationResult
from conservation_kernel.verifier import IndependentVerifier

BOT = Actor("bot", ActorKind.SYSTEM)


def _kernel():
    return ConservationKernel(root_guard=lambda artifact: True, allow_unguarded_evidence=True)


def _escalation(kernel):
    """A registered INFERENCE root, and a child that lifts it to a canonical FACT on references that do not exist."""
    root = Artifact("root-1", "x", (
        Proposition("p-1", "The queue is slow.", EpistemicStatus.INFERENCE, OriginStatus.MACHINE_ORIGINATED,
                    source_refs=("log",)),
    ), BOT)
    kernel.register_root(root)
    lifted = Proposition("p-1", "The queue is slow.", EpistemicStatus.FACT, OriginStatus.MACHINE_ORIGINATED,
                         authority=AuthorityStatus.CANONICAL, canonical_state=CanonicalState.CANONICAL,
                         source_refs=("log",), evidence_refs=("ev-nope",), authorization_refs=("auth-nope",))
    child = Artifact("child-1", "x", (lifted,), BOT, parent_artifact_ids=("root-1",))
    record = TransformationRecord("t-1", ("root-1",), "child-1", BOT, "x", (), (root.artifact_digest,),
                                  child.artifact_digest, reason="lift")
    return root, child, record


def test_the_verifier_rejects_the_escalation_and_a_hand_built_pass_cannot_overrule_it():
    kernel = _kernel()
    root, child, record = _escalation(kernel)
    assert not kernel.submit(root, child, record).accepted           # the kernel's own door says no
    assert [a.artifact_id for a in kernel.ledger.artifacts()] == ["root-1"]

    forged = VerificationResult("t-1", ("root-1",), "child-1", VerificationStatus.PASS)
    with pytest.raises(LedgerError):
        kernel.ledger.commit(child, record, forged)
    assert [a.artifact_id for a in kernel.ledger.artifacts()] == ["root-1"]
    assert kernel.ledger.transformations() == ()


def test_a_real_rejection_with_its_status_flipped_to_pass_is_refused():
    kernel = _kernel()
    root, child, record = _escalation(kernel)
    rejected = kernel.submit(root, child, record)
    assert not rejected.accepted
    flipped = replace(rejected, status=VerificationStatus.PASS, violations=())
    with pytest.raises(LedgerError):
        kernel.ledger.commit(child, record, flipped)
    assert [a.artifact_id for a in kernel.ledger.artifacts()] == ["root-1"]


def test_a_genuine_result_cannot_be_reused_for_a_record_that_was_changed_after_it_was_verified():
    """The proof is tied to the record and output it verified, so a genuine PASS cannot vouch for different bytes."""
    base, registry = build_ground_truth()
    kernel = ConservationKernel(registry=registry, root_guard=lambda artifact: True, allow_unguarded_evidence=True)
    kernel.register_root(base)
    output, record = legitimate_transformation(base, 1)
    genuine = kernel.verifier.verify(base, output, record, kernel.registry)
    assert genuine.accepted
    with pytest.raises(LedgerError):
        kernel.ledger.commit(output, replace(record, reason="edited after verification"), genuine)
    assert [a.artifact_id for a in kernel.ledger.artifacts()] == [base.artifact_id]


def test_a_pass_from_a_verifier_run_against_some_other_registry_is_not_the_kernels_verdict():
    base, kernel_registry = build_ground_truth()
    _, other_registry = build_ground_truth()
    kernel = ConservationKernel(registry=kernel_registry, root_guard=lambda artifact: True, allow_unguarded_evidence=True)
    kernel.register_root(base)
    output, record = legitimate_transformation(base, 1)
    result = IndependentVerifier().verify(base, output, record, other_registry)
    assert result.accepted                                          # it verifies, but against a registry of the caller's choosing
    with pytest.raises(LedgerError):
        kernel.ledger.commit(output, record, result)
    assert [a.artifact_id for a in kernel.ledger.artifacts()] == [base.artifact_id]


def test_the_kernels_own_submit_still_commits_a_legitimate_transformation():
    base, registry = build_ground_truth()
    kernel = ConservationKernel(registry=registry, root_guard=lambda artifact: True, allow_unguarded_evidence=True)
    kernel.register_root(base)
    output, record = legitimate_transformation(base, 1)
    assert kernel.submit(base, output, record).accepted
    assert [a.artifact_id for a in kernel.ledger.artifacts()] == [base.artifact_id, output.artifact_id]
    assert kernel.reconstruct(output.artifact_id).root_artifact_ids == (base.artifact_id,)
