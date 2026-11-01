"""A proposition's text must be the statement of the evidence it cites, when that evidence records a statement digest.

Shown: a root whose claim matches the cited statement is admitted; one whose claim differs is refused by admit_root and
by register_root (the audit's B3: a root saying $4,120.00 while citing TIE's record of $412.00). Evidence with no digest
keeps the old behaviour unless the CNS gate is told to require one. The digest is computed by statement_digest, which
matches tie.models.EvidenceRecord.statement_sha256 byte for byte (the shared vector is asserted in both repositories).
"""

import hashlib

import pytest

from conservation_kernel import ConservationKernel, EvidenceRecord, Actor, Proposition, Artifact
from conservation_kernel.enums import EpistemicStatus, EvidenceKind, OriginStatus
from conservation_kernel.kernel import STATEMENT_DIGEST_KEY, statement_digest

STATEMENT = "amount: $412.00"


def kernel_with(detail):
    kernel = ConservationKernel(root_guard=lambda artifact: True, evidence_guard=lambda record: True)
    kernel.registry.add_evidence(EvidenceRecord(
        evidence_id="ev-1", subject_id="p0", kind=EvidenceKind.SOURCE_OBSERVATION,
        provided_by=Actor.model("herald"), detail=detail))
    return kernel


def root(text):
    prop = Proposition(proposition_id="p0", text=text, epistemic_status=EpistemicStatus.INFERENCE,
                       origin=OriginStatus.MACHINE_ORIGINATED, evidence_refs=("ev-1",), source_refs=("doc-1",))
    return Artifact(artifact_id="root:doc-1", content="invoice", propositions=(prop,), producer=Actor.system("tie"))


def test_the_digest_is_the_sha256_of_the_utf8_statement():
    assert statement_digest(STATEMENT) == hashlib.sha256(STATEMENT.encode("utf-8")).hexdigest()


def test_a_root_whose_claim_is_the_cited_statement_is_admitted():
    kernel = kernel_with({STATEMENT_DIGEST_KEY: statement_digest(STATEMENT)})
    assert kernel.admit_root(root(STATEMENT)) == ()
    kernel.register_root(root(STATEMENT))


def test_a_root_whose_claim_differs_from_the_cited_statement_is_refused():
    kernel = kernel_with({STATEMENT_DIGEST_KEY: statement_digest(STATEMENT)})
    reasons = kernel.admit_root(root("amount: $4,120.00"))
    assert reasons and "not the statement of evidence ev-1" in reasons[0]
    with pytest.raises(Exception, match="not the statement"):
        kernel.register_root(root("amount: $4,120.00"))


def test_evidence_without_a_digest_keeps_the_old_behaviour():
    kernel = kernel_with({})
    assert kernel.admit_root(root("amount: $4,120.00")) == ()


def test_the_cns_gate_can_require_a_digest_on_every_cited_record():
    pytest.importorskip("cns.gate")
    from conservation_kernel.cns_connector import CnsRootAdmissionGate
    unbound = CnsRootAdmissionGate(kernel_with({}), require_statement_binding=True)
    result = unbound.check(root(STATEMENT))
    assert "carries no statement digest" in str(result.reason if hasattr(result, "reason") else result)
    bound = CnsRootAdmissionGate(kernel_with({STATEMENT_DIGEST_KEY: statement_digest(STATEMENT)}),
                                 require_statement_binding=True)
    assert "carries no statement digest" not in str(bound.check(root(STATEMENT)))
