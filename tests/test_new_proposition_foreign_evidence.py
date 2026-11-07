"""Foreign evidence on a brand-new proposition (follow-up to attack #10).

Attack #10 covered evidence attached to an existing proposition. A new proposition in a transformation
could carry evidence about an unrelated subject and skip that check.
"""

from conservation_kernel.enums import EpistemicStatus, OriginStatus, VerificationStatus
from conservation_kernel.experiments import _output, _record, build_ground_truth
from conservation_kernel.model import Proposition
from conservation_kernel.verifier import IndependentVerifier


def _new_proposition(evidence_refs):
    return Proposition(
        "p-new-note", "A note added by the transformer.", EpistemicStatus.ASSUMPTION,
        OriginStatus.MACHINE_ORIGINATED, evidence_refs=evidence_refs,
        parent_proposition_ids=("p-human-fact",), source_refs=("source:transformer-note",),
        metadata={"kind": "new_note"},
    )


def _verify(evidence_refs, suffix):
    base, registry = build_ground_truth()
    output = _output(base, suffix=suffix, propositions=(*base.propositions, _new_proposition(evidence_refs)))
    record = _record(base, output, (), suffix=suffix)
    return IndependentVerifier().verify(base, output, record, registry)


def test_new_proposition_with_foreign_evidence_is_rejected():
    # ev-human-assumption belongs to p-human-assumption, which is neither the new proposition nor its parent.
    result = _verify(("ev-human-assumption",), "new-prop-foreign-evidence")

    assert result.status is VerificationStatus.REJECT
    assert any(
        violation.code == "FOREIGN_EVIDENCE_ADDED" and violation.subject_id == "p-new-note"
        for violation in result.violations
    )


def test_new_proposition_with_parent_evidence_is_not_flagged_as_foreign():
    # ev-human-fact belongs to the parent, p-human-fact, which the new proposition may cite.
    result = _verify(("ev-human-fact",), "new-prop-parent-evidence")

    assert not any(violation.code == "FOREIGN_EVIDENCE_ADDED" for violation in result.violations)
