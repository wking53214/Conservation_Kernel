"""Audit defect 2: `ledger.add_initial` skipped `admit_root`.

`ConservationKernel.register_root` refuses a root that cites evidence or authorizations the registry does not hold, but
`kernel.ledger.add_initial` went straight to the ledger, so the same root registered there and became ancestry for
everything derived from it. A ledger a kernel owns now applies the same admission, whichever door the root comes through.
"""

from __future__ import annotations

import pytest

from conservation_kernel import (
    Actor, ActorKind, Artifact, AuthorityStatus, CanonicalState, ConservationKernel, EpistemicStatus, EvidenceKind,
    EvidenceRecord, OriginStatus, Proposition,
)
from conservation_kernel.errors import RootAdmissionError
from conservation_kernel.ledger import ConservationLedger

BOT = Actor("bot", ActorKind.SYSTEM)


def _kernel():
    return ConservationKernel(root_guard=lambda artifact: True, allow_unguarded_evidence=True)


def _cites_missing_evidence():
    p = Proposition("p-1", "Water boils at 100C at sea level.", EpistemicStatus.FACT, OriginStatus.EXTERNAL_ORIGINATED,
                    source_refs=("textbook",), evidence_refs=("ev-does-not-exist",))
    return Artifact("root-1", "x", (p,), BOT)


def test_a_root_citing_nonexistent_evidence_is_refused_through_the_ledger_door():
    kernel = _kernel()
    with pytest.raises(RootAdmissionError, match="evidence_refs not in registry"):
        kernel.ledger.add_initial(_cites_missing_evidence())
    assert kernel.ledger.artifacts() == ()


def test_the_two_doors_give_the_same_answer():
    via_register, via_ledger = _kernel(), _kernel()
    with pytest.raises(RootAdmissionError) as register_error:
        via_register.register_root(_cites_missing_evidence())
    with pytest.raises(RootAdmissionError) as ledger_error:
        via_ledger.ledger.add_initial(_cites_missing_evidence())
    assert str(register_error.value) == str(ledger_error.value)


def test_a_forged_authoritative_root_is_refused_through_the_ledger_door():
    kernel = _kernel()
    p = Proposition("p-forged", "The board approved the merger.", EpistemicStatus.FACT, OriginStatus.HUMAN_ORIGINATED,
                    authority=AuthorityStatus.EXECUTED, canonical_state=CanonicalState.CANONICAL,
                    authorization_refs=("auth-does-not-exist",), source_refs=("minutes",))
    with pytest.raises(RootAdmissionError, match="authorization_refs not in registry"):
        kernel.ledger.add_initial(Artifact("root-forged", "x", (p,), BOT))
    assert kernel.ledger.artifacts() == ()


def test_the_registry_is_asked_before_the_root_guard_so_a_one_use_permission_is_not_spent():
    asked = []
    kernel = ConservationKernel(root_guard=lambda artifact: asked.append(artifact.artifact_id) or True, allow_unguarded_evidence=True)
    with pytest.raises(RootAdmissionError, match="evidence_refs not in registry"):
        kernel.ledger.add_initial(_cites_missing_evidence())
    assert asked == []


def test_a_root_the_registry_backs_is_admitted_through_the_ledger_door_and_stamped():
    kernel = _kernel()
    kernel.registry.add_evidence(EvidenceRecord("ev-textbook", "p-1", EvidenceKind.SOURCE_OBSERVATION, BOT))
    p = Proposition("p-1", "Water boils at 100C at sea level.", EpistemicStatus.FACT, OriginStatus.EXTERNAL_ORIGINATED,
                    source_refs=("textbook",), evidence_refs=("ev-textbook",))
    kernel.ledger.add_initial(Artifact("root-1", "x", (p,), BOT))
    assert [a.artifact_id for a in kernel.ledger.artifacts()] == ["root-1"]


def test_a_ledger_no_kernel_owns_has_no_registry_to_check_against_and_is_unchanged():
    ledger = ConservationLedger()
    ledger.add_initial(_cites_missing_evidence())
    assert [a.artifact_id for a in ledger.artifacts()] == ["root-1"]
