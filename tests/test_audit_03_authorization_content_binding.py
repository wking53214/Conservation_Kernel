"""Audit defect 3: an authorization named a subject, a kind of change and a target value, but not what it was about.

One authorization for p-1 becoming HUMAN_AUTHORIZED admitted both "Refund customer $10." and "Refund customer
$10,000,000.", because nothing tied it to the words the human actually approved. `subject_digest` is that tie: when an
authorization carries one it must equal the digest of the proposition it is used for, and a kernel can require every
authorization to carry one (`require_content_bound`).
"""

from __future__ import annotations

from hashlib import sha256

import pytest

from conservation_kernel import (
    Actor, ActorKind, Artifact, AuthorityStatus, AuthorizationEvent, ConservationKernel, DeclaredChange, Dimension,
    EpistemicStatus, EvidenceRegistry, OriginStatus, Proposition, TransformationRecord, TransitionKind,
)
from conservation_kernel.errors import InvalidEvent, RootAdmissionError

BOT = Actor("bot", ActorKind.SYSTEM)
REVIEWER = Actor("reviewer-1", ActorKind.HUMAN)
SMALL, LARGE = "Refund customer $10.", "Refund customer $10,000,000."


def prop(text=SMALL, authority=AuthorityStatus.HUMAN_AUTHORIZED, refs=("auth-1",), conditions=()):
    return Proposition("p-1", text, EpistemicStatus.DECISION, OriginStatus.HUMAN_ORIGINATED, authority=authority,
                       authorization_refs=refs if authority is not AuthorityStatus.NONE else (), conditions=conditions)


def authorization(auth_id="auth-1", digest=None, text=SMALL):
    """A human approving p-1 becoming HUMAN_AUTHORIZED. With `digest` set to True, bound to the words of `text`."""
    bound = {} if digest is None else {"subject_digest": prop(text).canonical_digest if digest is True else digest}
    return AuthorizationEvent(
        authorization_id=auth_id, authorized_by=REVIEWER, subject_id="p-1",
        transition_kind=TransitionKind.AUTHORITY_ESCALATION, from_value="NONE", to_value="HUMAN_AUTHORIZED",
        reason="approved", **bound,
    )


def kernel(**options):
    return ConservationKernel(root_guard=lambda artifact: True, **options, allow_unguarded_evidence=True)


def root(text, artifact_id):
    return Artifact(artifact_id, "x", (prop(text),), BOT)


# ---------------------------------------------------------------- the attack, at root admission

def test_without_a_digest_one_authorization_still_admits_both_amounts_as_before():
    k = kernel()
    k.registry.add_authorization(authorization())
    k.register_root(root(SMALL, "root-small"))
    k.register_root(root(LARGE, "root-large"))                       # the defect, unchanged for an unbound authorization
    assert len(k.ledger.artifacts()) == 2


def test_an_authorization_bound_to_the_small_refund_does_not_admit_the_large_one():
    k = kernel()
    k.registry.add_authorization(authorization(digest=True))
    k.register_root(root(SMALL, "root-small"))
    with pytest.raises(RootAdmissionError, match="has no authorization for this proposition"):
        k.register_root(root(LARGE, "root-large"))
    assert [a.artifact_id for a in k.ledger.artifacts()] == ["root-small"]


# ---------------------------------------------------------------- the attack, through the verifier

def _escalate(k, text):
    before = Artifact("before", "x", (prop(SMALL, authority=AuthorityStatus.NONE),), BOT)
    k.register_root(before)
    after = Artifact("after", "x", (prop(text),), BOT, parent_artifact_ids=("before",))
    declared = [DeclaredChange("p-1", Dimension.AUTHORITY, "NONE", "HUMAN_AUTHORIZED", "approved",
                               TransitionKind.AUTHORITY_ESCALATION)]
    if text != SMALL:                                               # the words changed too, and the change is declared
        declared.append(DeclaredChange("p-1", Dimension.CONTENT, sha256(SMALL.encode()).hexdigest(),
                                       sha256(text.encode()).hexdigest(), "reworded", TransitionKind.DERIVATION))
    record = TransformationRecord("t-1", ("before",), "after", BOT, "x", tuple(declared), (before.artifact_digest,),
                                  after.artifact_digest, authorization_refs=("auth-1",), reason="approve")
    return k.submit(before, after, record)


def test_the_verifier_accepts_the_escalation_the_human_approved():
    k = kernel()
    k.registry.add_authorization(authorization(digest=True))
    assert _escalate(k, SMALL).accepted


def test_the_verifier_refuses_the_same_escalation_for_words_the_human_did_not_approve():
    k = kernel()
    k.registry.add_authorization(authorization(digest=True))
    result = _escalate(k, LARGE)
    assert not result.accepted
    assert "UNAUTHORIZED_AUTHORITY_ESCALATION" in {v.code for v in result.violations}


def test_an_unbound_authorization_is_unchanged_in_the_verifier():
    k = kernel()
    k.registry.add_authorization(authorization())
    assert _escalate(k, LARGE).accepted


def _born_authoritative(k, text):
    """The codes the verifier gives a transformation that adds p-1, already authorized, beside an observed parent."""
    parent = Proposition("p-0", "Customer asked for a refund.", EpistemicStatus.OBSERVATION,
                         OriginStatus.EXTERNAL_ORIGINATED, source_refs=("ticket",))
    before = Artifact("before", "x", (parent,), BOT)
    k.register_root(before)
    born = Proposition("p-1", text, EpistemicStatus.DECISION, OriginStatus.MACHINE_ORIGINATED,
                       authority=AuthorityStatus.HUMAN_AUTHORIZED, authorization_refs=("auth-1",),
                       parent_proposition_ids=("p-0",))
    after = Artifact("after", "x", (parent, born), BOT, parent_artifact_ids=("before",))
    record = TransformationRecord("t-1", ("before",), "after", BOT, "x", (), (before.artifact_digest,),
                                  after.artifact_digest, authorization_refs=("auth-1",), reason="add")
    return {v.code for v in k.verifier.verify(before, after, record, k.registry.at(k._now())).violations}


def test_a_new_proposition_born_authoritative_needs_an_authorization_bound_to_its_words():
    bound = kernel()
    bound.registry.add_authorization(authorization(digest=True))
    assert "NEW_AUTHORITY_UNVERIFIED" not in _born_authoritative(bound, SMALL)
    refused = kernel()
    refused.registry.add_authorization(authorization(digest=True))
    assert "NEW_AUTHORITY_UNVERIFIED" in _born_authoritative(refused, LARGE)
    unbound = kernel()
    unbound.registry.add_authorization(authorization())
    assert "NEW_AUTHORITY_UNVERIFIED" not in _born_authoritative(unbound, LARGE)


# ---------------------------------------------------------------- the digest itself

def test_the_digest_covers_the_claim_and_not_the_status_an_authorization_is_about_to_change():
    assert prop(SMALL).canonical_digest == prop(SMALL, authority=AuthorityStatus.NONE).canonical_digest
    assert prop(SMALL).canonical_digest != prop(LARGE).canonical_digest
    assert prop(SMALL).canonical_digest != prop(SMALL, conditions=("only for queue X",)).canonical_digest


def test_a_bound_authorization_is_used_only_by_a_caller_that_names_the_content():
    """Fail closed: a path that does not say what it is authorizing cannot use an authorization that is about content."""
    registry = EvidenceRegistry()
    registry.add_authorization(authorization(digest=True))
    ask = dict(subject_id="p-1", transition_kind=TransitionKind.AUTHORITY_ESCALATION, from_value="NONE",
               to_value="HUMAN_AUTHORIZED")
    assert registry.has_authorization(("auth-1",), subject_digest=prop(SMALL).canonical_digest, **ask)
    assert not registry.has_authorization(("auth-1",), subject_digest=prop(LARGE).canonical_digest, **ask)
    assert not registry.has_authorization(("auth-1",), **ask)


# ---------------------------------------------------------------- require_content_bound

def test_a_kernel_that_requires_content_binding_refuses_an_authorization_with_no_digest():
    k = kernel(require_content_bound=True)
    with pytest.raises(InvalidEvent, match="subject_digest"):
        k.registry.add_authorization(authorization())
    k.registry.add_authorization(authorization(digest=True))
    k.register_root(root(SMALL, "root-small"))
    assert k.require_content_bound is True


def test_content_binding_is_not_required_by_default():
    k = kernel()
    k.registry.add_authorization(authorization())
    assert k.require_content_bound is False


def test_the_option_belongs_to_the_registry_a_caller_supplies_not_to_the_kernel_as_well():
    with pytest.raises(ValueError, match="registry you supply"):
        ConservationKernel(registry=EvidenceRegistry(), root_guard=lambda artifact: True, require_content_bound=True, allow_unguarded_evidence=True)


# ---------------------------------------------------------------- snapshot round trip

def test_the_digest_survives_a_snapshot_and_an_unbound_authorization_keeps_its_old_shape():
    k = kernel()
    k.registry.add_authorization(authorization("auth-bound", digest=True))
    k.registry.add_authorization(authorization("auth-plain"))
    stored = {item["authorization_id"]: item for item in k.snapshot()["registry"]["authorizations"]}
    assert stored["auth-bound"]["subject_digest"] == prop(SMALL).canonical_digest
    assert "subject_digest" not in stored["auth-plain"]
    restored = ConservationKernel.from_snapshot(k.snapshot(), root_guard=lambda artifact: True, allow_unguarded_evidence=True)
    assert restored.registry.authorization("auth-bound").subject_digest == prop(SMALL).canonical_digest
    assert restored.registry.authorization("auth-plain").subject_digest is None
    assert restored.snapshot() == k.snapshot()


def test_a_restore_that_requires_content_binding_refuses_an_unbound_authorization_in_the_file():
    k = kernel()
    k.registry.add_authorization(authorization("auth-plain"))
    with pytest.raises(InvalidEvent, match="subject_digest"):
        ConservationKernel.from_snapshot(k.snapshot(), root_guard=lambda artifact: True, require_content_bound=True, allow_unguarded_evidence=True)


def test_an_empty_digest_is_not_a_digest():
    with pytest.raises(InvalidEvent):
        authorization(digest="  ")
