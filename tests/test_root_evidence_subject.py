"""A root's fact or observation that cites evidence must cite evidence about that proposition.

Evidence records name the proposition they support (`subject_id`). Root admission checked that a cited record exists,
so a FACT about one thing could stand on evidence recorded for another. The verifier already matches the subject for a
transformation (the proposition and its parents); a root has no parents, so its own id is the only subject that counts.
"""
from __future__ import annotations

from conservation_kernel import (
    Actor, Artifact, ConservationKernel, EpistemicStatus, EvidenceRecord, OriginStatus, Proposition,
)
from conservation_kernel.enums import EvidenceKind


def kernel_with_evidence_about(subject: str) -> ConservationKernel:
    kernel = ConservationKernel(allow_unguarded_roots=True)
    kernel.registry.add_evidence(EvidenceRecord(evidence_id="ev-1", subject_id=subject, kind=EvidenceKind.SOURCE_OBSERVATION,
                                                provided_by=Actor.system("tie")))
    return kernel


def root_with(proposition_id: str, status: EpistemicStatus, evidence=("ev-1",), sources=("doc-1",)) -> Artifact:
    proposition = Proposition(proposition_id=proposition_id, text="The invoice came to $412.00.", epistemic_status=status,
                              origin=OriginStatus.MACHINE_ORIGINATED, evidence_refs=evidence, source_refs=sources)
    return Artifact(artifact_id="root:doc-1", content="Invoice came to $412.00.", propositions=(proposition,),
                    producer=Actor.system("tie"))


def test_a_fact_citing_evidence_about_another_proposition_is_refused():
    reasons = kernel_with_evidence_about("p0").admit_root(root_with("p7", EpistemicStatus.FACT))
    assert any(r.startswith("p7: ") and "ev-1" in r and "about this proposition" in r for r in reasons), reasons


def test_an_observation_citing_evidence_about_another_proposition_is_refused():
    reasons = kernel_with_evidence_about("p0").admit_root(root_with("p7", EpistemicStatus.OBSERVATION))
    assert any("about this proposition" in r for r in reasons), reasons


def test_the_same_fact_citing_evidence_about_itself_is_admitted():
    assert kernel_with_evidence_about("p7").admit_root(root_with("p7", EpistemicStatus.FACT)) == ()


def test_one_matching_record_among_several_is_enough():
    kernel = kernel_with_evidence_about("p7")
    kernel.registry.add_evidence(EvidenceRecord(evidence_id="ev-2", subject_id="p0", kind=EvidenceKind.CITATION,
                                                provided_by=Actor.system("tie")))
    assert kernel.admit_root(root_with("p7", EpistemicStatus.FACT, evidence=("ev-1", "ev-2"))) == ()


def test_a_wildcard_subject_does_not_stand_for_every_proposition():
    assert kernel_with_evidence_about("*").admit_root(root_with("p7", EpistemicStatus.FACT))


def test_an_inference_may_cite_evidence_about_something_else():
    """The rule binds strong claims only, as the verifier's does."""
    assert kernel_with_evidence_about("p0").admit_root(root_with("p7", EpistemicStatus.INFERENCE)) == ()


def test_an_observation_that_cites_only_a_source_is_unaffected():
    assert kernel_with_evidence_about("p0").admit_root(root_with("p7", EpistemicStatus.OBSERVATION, evidence=())) == ()


def test_a_missing_reference_is_reported_as_missing_and_not_as_about_another_proposition():
    reasons = kernel_with_evidence_about("p0").admit_root(root_with("p7", EpistemicStatus.FACT, evidence=("ev-9",)))
    assert any("not in registry" in r for r in reasons) and not any("about this proposition" in r for r in reasons)


def test_a_snapshot_holding_such_a_root_does_not_restore():
    """Unlike withdrawn evidence, a mismatch never changes: the root was never about its evidence. Restore re-admits
    every root so that a ledger written by hand or by an older kernel fails as it would have failed live."""
    import pytest

    from conservation_kernel.errors import SnapshotIntegrityError
    kernel = kernel_with_evidence_about("p0")
    kernel.ledger.add_initial(root_with("p7", EpistemicStatus.FACT))  # planted past admission
    with pytest.raises(SnapshotIntegrityError, match="about this proposition"):
        ConservationKernel.from_snapshot(kernel.snapshot(), allow_unguarded_roots=True)
