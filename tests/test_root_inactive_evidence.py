"""A root that states a fact, an observation, an authority or a canonical state may not cite evidence that is no longer active.

The verifier already refuses a transformation whose strong proposition keeps inactive evidence (INACTIVE_EVIDENCE).
Root admission is the other door into the ledger, and it checked that a cited record exists but not that it is still
active, so a root could assert what a transformation could not. Admission now applies the same rule, with the same
condition: strong epistemic status, any authority, or canonical state.
"""
from __future__ import annotations

import pytest

from conservation_kernel import (
    Actor, Artifact, ConservationKernel, EpistemicStatus, EvidenceRecord, OriginStatus, Proposition,
)
from conservation_kernel.enums import EvidenceKind
from conservation_kernel.errors import RootAdmissionError


def kernel_holding(*, active: bool) -> ConservationKernel:
    kernel = ConservationKernel(allow_unguarded_roots=True)
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


def test_a_snapshot_holding_such_a_root_no_longer_reverifies():
    """The stated behaviour change: a root planted past admission (an older or hand-made snapshot) is re-admitted on
    reload, and is now refused for the same reason a live registration is."""
    from conservation_kernel.errors import SnapshotIntegrityError
    kernel = kernel_holding(active=False)
    kernel.ledger.add_initial(root_citing(EpistemicStatus.FACT))
    with pytest.raises(SnapshotIntegrityError, match="inactive evidence"):
        ConservationKernel.from_snapshot(kernel.snapshot(), allow_unguarded_roots=True)
