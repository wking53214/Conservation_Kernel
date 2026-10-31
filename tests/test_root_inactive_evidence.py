"""A kernel can refuse a new root whose strong or canonical proposition cites evidence that is no longer active.

The verifier already refuses a transformation whose strong proposition keeps inactive evidence (INACTIVE_EVIDENCE).
Root admission checked that a cited record exists, not that it is active, so a root could assert what a transformation
could not. A deployer turns the same rule on with `refuse_inactive_root_evidence=True`, the way `require_bounded` is
turned on: off by default, so nothing changes until it is asked for.

It applies to a root being registered now. It never applies when a snapshot is restored: a root admitted while its
evidence was active stays admitted if the evidence is withdrawn later, and restoring it must not fail for that.
"""
from __future__ import annotations

import pytest

from conservation_kernel import (
    Actor, Artifact, ConservationKernel, EpistemicStatus, EvidenceRecord, OriginStatus, Proposition,
)
from conservation_kernel.enums import EvidenceKind
from conservation_kernel.errors import RootAdmissionError


def kernel_holding(*, active: bool, refuse: bool = True) -> ConservationKernel:
    kernel = ConservationKernel(allow_unguarded_roots=True, refuse_inactive_root_evidence=refuse)
    kernel.registry.add_evidence(EvidenceRecord(
        evidence_id="ev-1", subject_id="p0", kind=EvidenceKind.SOURCE_OBSERVATION, provided_by=Actor.system("tie"),
        active=active))
    return kernel


def root_citing(status: EpistemicStatus, *, evidence=("ev-1",)) -> Artifact:
    proposition = Proposition(proposition_id="p0", text="The invoice came to $412.00.", epistemic_status=status,
                              origin=OriginStatus.MACHINE_ORIGINATED, evidence_refs=evidence, source_refs=("doc-1",))
    return Artifact(artifact_id="root:doc-1", content="Invoice came to $412.00.", propositions=(proposition,),
                    producer=Actor.system("tie"))


@pytest.mark.parametrize("status", [EpistemicStatus.FACT, EpistemicStatus.OBSERVATION])
def test_a_strong_root_citing_inactive_evidence_is_refused(status):
    kernel = kernel_holding(active=False)
    reasons = kernel.admit_root(root_citing(status))
    assert any("inactive" in reason and "ev-1" in reason for reason in reasons), reasons
    with pytest.raises(RootAdmissionError, match="inactive"):
        kernel.register_root(root_citing(status))


@pytest.mark.parametrize("status", [EpistemicStatus.FACT, EpistemicStatus.OBSERVATION])
def test_the_same_root_citing_active_evidence_is_admitted(status):
    kernel = kernel_holding(active=True)
    assert kernel.admit_root(root_citing(status)) == ()
    kernel.register_root(root_citing(status))


def test_an_inference_may_still_cite_inactive_evidence():
    """The rule is the verifier's: it binds strong claims, not every claim. An inference that cites withdrawn evidence
    is a weaker statement and is left as it was."""
    assert kernel_holding(active=False).admit_root(root_citing(EpistemicStatus.INFERENCE)) == ()


def test_a_missing_reference_is_still_reported_as_missing_and_not_as_inactive():
    reasons = kernel_holding(active=False).admit_root(root_citing(EpistemicStatus.FACT, evidence=("ev-9",)))
    assert any("not in registry" in reason for reason in reasons)
    assert not any("inactive" in reason for reason in reasons)


def test_the_refusal_names_the_proposition_and_the_record():
    reasons = kernel_holding(active=False).admit_root(root_citing(EpistemicStatus.FACT))
    assert any(reason.startswith("p0: ") and "['ev-1']" in reason for reason in reasons), reasons


def test_it_is_off_by_default_so_an_existing_kernel_judges_roots_as_before():
    kernel = kernel_holding(active=False, refuse=False)
    assert kernel.admit_root(root_citing(EpistemicStatus.FACT)) == ()
    assert ConservationKernel(allow_unguarded_roots=True).refuse_inactive_root_evidence is False


def test_restoring_a_snapshot_never_applies_it_so_withdrawn_evidence_cannot_brick_a_ledger():
    """A root admitted while its evidence was active stays admitted if the evidence is withdrawn afterwards. Restoring
    it, even into a kernel that refuses such roots now, must succeed."""
    kernel = kernel_holding(active=False)
    kernel.ledger.add_initial(root_citing(EpistemicStatus.FACT))  # stands for a root admitted before the withdrawal
    restored = ConservationKernel.from_snapshot(kernel.snapshot(), allow_unguarded_roots=True,
                                                refuse_inactive_root_evidence=True)
    assert restored.refuse_inactive_root_evidence is True
    assert restored.ledger.artifact("root:doc-1") is not None
    with pytest.raises(RootAdmissionError, match="inactive"):
        restored.register_root(root_citing(EpistemicStatus.FACT).__class__(
            artifact_id="root:doc-2", content="Another invoice.", propositions=root_citing(EpistemicStatus.FACT).propositions,
            producer=Actor.system("tie")))
