"""An authorization can hold for a stated window, and outside it it does not count.

`valid_from` and `valid_until` are optional (ISO 8601 with a UTC offset; the window is
half-open, so `valid_until` itself is outside it). An authorization with neither behaves
exactly as before. The window is judged as of the deciding kernel's clock (see
test_decision_time.py), never the transformer's own timestamp, and a lineage accepted inside
a window still reloads after the window has closed.
"""
from __future__ import annotations

from dataclasses import replace

import pytest

from conservation_kernel import (
    Actor, ActorKind, Artifact, AuthorityStatus, AuthorizationEvent, ConservationKernel, DeclaredChange, Dimension,
    EpistemicStatus, EvidenceRegistry, IndependentVerifier, OriginStatus, Proposition, TransformationRecord,
    TransitionKind,
)
from conservation_kernel.errors import InvalidEvent, RootAdmissionError
from conservation_kernel.experiments import build_ground_truth

OPENS = "2026-10-01T00:00:00+00:00"
INSIDE = "2026-10-15T12:00:00+00:00"
CLOSES = "2026-11-01T00:00:00+00:00"
AFTER = "2026-11-02T00:00:00+00:00"
BEFORE = "2026-09-30T00:00:00+00:00"
SUBJECT = "p-ai-inference"


class _Clock:
    def __init__(self, now: str) -> None:
        self.now = now

    def __call__(self) -> str:
        return self.now


def _adoption_auth(**window):
    return AuthorizationEvent(
        authorization_id="auth-adopt", authorized_by=Actor.human("adopter"), subject_id=SUBJECT,
        transition_kind=TransitionKind.HUMAN_ADOPTION, from_value=OriginStatus.MACHINE_ORIGINATED.value,
        to_value=OriginStatus.HUMAN_ADOPTED_MACHINE_OUTPUT.value, reason="adopted", **window)


def _adoption(registry, base, *, created_at=None):
    """A machine output adopted by a human: needs a HUMAN_ADOPTION authorization for SUBJECT."""
    old = base.proposition_map()[SUBJECT]
    new = replace(old, origin=OriginStatus.HUMAN_ADOPTED_MACHINE_OUTPUT, authorization_refs=("auth-adopt",))
    output = Artifact(
        artifact_id=f"{base.artifact_id}-adopted", content=base.content,
        propositions=tuple(new if p.proposition_id == SUBJECT else p for p in base.propositions),
        producer=Actor.model("transformer"), parent_artifact_ids=(base.artifact_id,), version=base.version + 1,
        functional_contract=base.functional_contract)
    extra = {"created_at": created_at} if created_at else {}
    record = TransformationRecord(
        transformation_id="tx-adopt", input_artifact_ids=(base.artifact_id,), output_artifact_id=output.artifact_id,
        transformer=output.producer, transformation_type="EXPLICIT_TRANSITION",
        declared_changes=(DeclaredChange(SUBJECT, Dimension.HUMAN_ORIGIN, old.origin.value, new.origin.value,
                                         "explicit human adoption", TransitionKind.HUMAN_ADOPTION),),
        input_hashes=(base.artifact_digest,), output_hash=output.artifact_digest,
        authorization_refs=("auth-adopt",), reason="adoption", **extra)
    return output, record


def _verdict(as_of, **window):
    base, registry = build_ground_truth()
    registry.add_authorization(_adoption_auth(**window))
    output, record = _adoption(registry, base)
    view = registry.at(as_of) if as_of is not None else registry
    return IndependentVerifier().verify(base, output, record, view)


def _codes(result):
    return {v.code for v in result.violations}


# ---------------------------------------------------------------- the window

def test_an_authorization_used_inside_its_window_counts():
    assert _verdict(INSIDE, valid_from=OPENS, valid_until=CLOSES).accepted


def test_an_authorization_used_after_its_window_does_not_count():
    result = _verdict(AFTER, valid_from=OPENS, valid_until=CLOSES)
    assert not result.accepted and "MISSING_HUMAN_ADOPTION" in _codes(result)


def test_the_end_of_the_window_is_already_outside_it():
    assert not _verdict(CLOSES, valid_until=CLOSES).accepted


def test_an_authorization_used_before_its_window_opens_does_not_count():
    assert not _verdict(BEFORE, valid_from=OPENS).accepted


def test_with_no_time_a_windowed_authorization_does_not_count_but_an_open_ended_one_still_does():
    assert not _verdict(None, valid_until=CLOSES).accepted
    assert _verdict(None).accepted                       # unchanged behaviour for every existing authorization


def test_the_view_hides_an_authorization_outside_its_window_from_every_lookup():
    registry = EvidenceRegistry()
    registry.add_authorization(_adoption_auth(valid_until=CLOSES))
    assert registry.at(INSIDE).authorization("auth-adopt") is not None
    assert registry.at(AFTER).authorization("auth-adopt") is None
    assert registry.authorization("auth-adopt") is not None      # the raw lookup still finds it, for the record


# ---------------------------------------------------------------- whose clock

def test_the_transformers_own_timestamp_cannot_extend_an_authorization():
    base, registry = build_ground_truth()
    registry.add_authorization(_adoption_auth(valid_until=CLOSES))
    clock = _Clock(INSIDE)
    k = ConservationKernel(allow_unguarded_roots=True, registry=registry, clock=clock)
    k.register_root(base)
    clock.now = AFTER
    output, record = _adoption(registry, base, created_at=INSIDE)      # claims to be from inside the window
    assert not k.submit(base, output, record).accepted


def test_a_lineage_accepted_inside_the_window_still_reloads_after_it_closes(tmp_path):
    base, registry = build_ground_truth()
    registry.add_authorization(_adoption_auth(valid_from=OPENS, valid_until=CLOSES))
    clock = _Clock(INSIDE)
    k = ConservationKernel(allow_unguarded_roots=True, registry=registry, clock=clock)
    k.register_root(base)
    output, record = _adoption(registry, base)
    assert k.submit(base, output, record).accepted
    k.save(tmp_path / "kernel.json")
    restored = ConservationKernel.load(tmp_path / "kernel.json", allow_unguarded_roots=True, clock=_Clock(AFTER))
    assert restored.reconstruct(output.artifact_id).transformation_ids_in_order == ("tx-adopt",)


# ---------------------------------------------------------------- roots

def _authoritative_root():
    p = Proposition("p-claim", "Deploy to production.", EpistemicStatus.DECISION, OriginStatus.MACHINE_ORIGINATED,
                    authority=AuthorityStatus.HUMAN_AUTHORIZED, authorization_refs=("auth-root",))
    return Artifact("root-claim", "x", (p,), Actor("bot", ActorKind.SYSTEM))


def _root_auth(**window):
    return AuthorizationEvent(
        authorization_id="auth-root", authorized_by=Actor.human("approver"), subject_id="p-claim",
        transition_kind=TransitionKind.AUTHORITY_ESCALATION, from_value="NONE", to_value="HUMAN_AUTHORIZED",
        reason="approved", **window)


def test_a_root_claim_whose_authorization_has_ended_is_refused():
    registry = EvidenceRegistry()
    registry.add_authorization(_root_auth(valid_until=CLOSES))
    k = ConservationKernel(allow_unguarded_roots=True, registry=registry, clock=_Clock(AFTER))
    with pytest.raises(RootAdmissionError, match="no authorization for this proposition"):
        k.register_root(_authoritative_root())


def test_a_root_admitted_inside_the_window_still_reloads_after_it_closes(tmp_path):
    registry = EvidenceRegistry()
    registry.add_authorization(_root_auth(valid_until=CLOSES))
    k = ConservationKernel(allow_unguarded_roots=True, registry=registry, clock=_Clock(INSIDE))
    k.register_root(_authoritative_root())
    k.save(tmp_path / "kernel.json")
    restored = ConservationKernel.load(tmp_path / "kernel.json", allow_unguarded_roots=True, clock=_Clock(AFTER))
    assert [a.artifact_id for a in restored.ledger.artifacts()] == ["root-claim"]


# ---------------------------------------------------------------- shape and strictness

@pytest.mark.parametrize("window", [
    {"valid_until": "2026-11-01T00:00:00"},              # no offset: whose midnight?
    {"valid_until": "next tuesday"},
    {"valid_from": CLOSES, "valid_until": OPENS},          # ends before it starts
    {"valid_from": OPENS, "valid_until": OPENS},           # an empty window
])
def test_a_malformed_window_is_refused(window):
    with pytest.raises(InvalidEvent):
        _adoption_auth(**window)


def test_an_open_ended_authorization_keeps_its_old_shape_and_a_windowed_one_round_trips():
    assert "valid_until" not in _adoption_auth().to_dict() and "valid_from" not in _adoption_auth().to_dict()
    windowed = _adoption_auth(valid_from=OPENS, valid_until=CLOSES)
    assert AuthorizationEvent.from_dict(windowed.to_dict()) == windowed


def test_a_registry_that_requires_an_end_refuses_an_open_ended_authorization(tmp_path):
    strict = EvidenceRegistry(require_bounded=True)
    with pytest.raises(InvalidEvent, match="end"):
        strict.add_authorization(_adoption_auth())
    strict.add_authorization(_adoption_auth(valid_until=CLOSES))

    lax = ConservationKernel(allow_unguarded_roots=True, registry=EvidenceRegistry())
    lax.registry.add_authorization(_root_auth())
    lax.save(tmp_path / "kernel.json")
    with pytest.raises(InvalidEvent, match="end"):
        ConservationKernel.load(tmp_path / "kernel.json", allow_unguarded_roots=True, require_bounded=True)
