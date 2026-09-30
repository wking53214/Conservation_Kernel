"""The connected half: what the kernel's verdicts become when CNS is installed.

Skipped when CNS is absent. The independence half, which must hold in both
environments, is in ``test_cns_independence.py`` and never skips.
"""

from __future__ import annotations

import traceback
from dataclasses import replace

import pytest

cns_gate = pytest.importorskip(
    "cns.gate",
    reason="cns not installed; run in an environment with conservation-kernel[cns]",
)

from conservation_kernel import (  # noqa: E402
    Actor,
    ActorKind,
    Artifact,
    AuthorityStatus,
    CanonicalState,
    ConservationKernel,
    DeclaredChange,
    Dimension,
    EpistemicStatus,
    EvidenceKind,
    EvidenceRecord,
    IndependentVerifier,
    OriginStatus,
    Proposition,
    TransformationRecord,
    Uncertainty,
    UncertaintyState,
    VerificationStatus,
    Violation,
)
from conservation_kernel.cns_connector import (  # noqa: E402
    CnsGate,
    CnsRootAdmissionGate,
    TransformationCandidate,
    admission_to_cns_result,
    cns_available,
    cns_chain,
    root_digest,
    root_refusals,
    submit_to_cns,
    to_cns_result,
    transformation_digest,
    verify_to_cns,
)
from conservation_kernel.errors import LedgerError, RootAdmissionError  # noqa: E402
from conservation_kernel.experiments import (  # noqa: E402
    build_ground_truth,
    hostile_cases,
    legitimate_transformation,
)

PASS = cns_gate.GateOutcome.PASS
BREACH = cns_gate.GateOutcome.TERMINAL_BREACH
ALPHA = cns_gate.GatePosition.ALPHA
OMEGA = cns_gate.GatePosition.OMEGA

FIXED = "2026-01-01T00:00:00+00:00"


# ---------------------------------------------------------------- fixtures


def _derive(base, suffix, *, declared=()):
    """A new artifact identity over the same content: no protected change."""
    output = Artifact(
        artifact_id=f"{base.artifact_id}-{suffix}",
        content=base.content,
        propositions=base.propositions,
        producer=Actor.model(f"transformer-{suffix}"),
        parent_artifact_ids=(base.artifact_id,),
        version=base.version + 1,
        functional_contract=base.functional_contract,
    )
    record = TransformationRecord(
        transformation_id=f"tx-{suffix}",
        input_artifact_ids=(base.artifact_id,),
        output_artifact_id=output.artifact_id,
        transformer=output.producer,
        transformation_type="FIXTURE",
        declared_changes=tuple(declared),
        input_hashes=(base.artifact_digest,),
        output_hash=output.artifact_digest,
        reason="connector fixture",
    )
    return output, record


def _samples():
    """One clean PASS, one PASS_WITH_DECLARED_TRANSFORMATION, every hostile REJECT."""
    base, registry = build_ground_truth()
    samples = []
    output, record = _derive(base, "same")
    samples.append(("unchanged", base, output, record, registry))
    output, record = legitimate_transformation(base, 1)
    samples.append(("legitimate", base, output, record, registry))
    for case in hostile_cases():
        output, record, case_registry = case.build(base)
        samples.append((case.name, base, output, record, case_registry))
    return samples


SAMPLES = _samples()
SAMPLE_IDS = [sample[0] for sample in SAMPLES]
SAMPLE_ARGS = "label,base,output,record,registry"


def _two_inputs():
    """Two independent roots merged into one output: a multi-input candidate."""
    base, registry = build_ground_truth()
    side = Artifact(
        artifact_id="artifact-side",
        content="A second source artifact.",
        propositions=(
            Proposition(
                "p-side",
                "The side channel was quiet.",
                EpistemicStatus.UNKNOWN,
                OriginStatus.MACHINE_ORIGINATED,
                uncertainty=Uncertainty(UncertaintyState.UNKNOWN, "unobserved"),
            ),
        ),
        producer=Actor.system("side-source"),
    )
    output = Artifact(
        artifact_id="artifact-merged",
        content="merged",
        propositions=base.propositions + side.propositions,
        producer=Actor.model("merger"),
        parent_artifact_ids=(base.artifact_id, side.artifact_id),
        version=2,
    )
    record = TransformationRecord(
        transformation_id="tx-merge",
        input_artifact_ids=(base.artifact_id, side.artifact_id),
        output_artifact_id=output.artifact_id,
        transformer=output.producer,
        transformation_type="MERGE",
        declared_changes=(),
        input_hashes=(base.artifact_digest, side.artifact_digest),
        output_hash=output.artifact_digest,
        reason="merge fixture",
    )
    return (base, side), output, record, registry


def _pinned_candidate():
    """Fixed timestamps, so the digest is the same on every machine and run."""
    prop = Proposition(
        "p-1",
        "The queue fell.",
        EpistemicStatus.UNKNOWN,
        OriginStatus.MACHINE_ORIGINATED,
        uncertainty=Uncertainty(UncertaintyState.UNKNOWN, "unobserved"),
    )
    source = Artifact("pin-in", "input", (prop,), Actor.system("pin"), created_at=FIXED)
    output = Artifact(
        "pin-out", "output", (prop,), Actor.model("pin-model"),
        parent_artifact_ids=("pin-in",), version=2, created_at=FIXED,
    )
    record = TransformationRecord(
        transformation_id="pin-tx",
        input_artifact_ids=("pin-in",),
        output_artifact_id="pin-out",
        transformer=output.producer,
        transformation_type="PIN",
        declared_changes=(
            DeclaredChange(
                "pin-out", Dimension.CONTENT, source.content_digest,
                output.content_digest, "reworded",
            ),
        ),
        input_hashes=(source.artifact_digest,),
        output_hash=output.artifact_digest,
        reason="pin",
        created_at=FIXED,
    )
    return TransformationCandidate(source, output, record)


def _twin(base, registry):
    kernel = ConservationKernel(registry=registry)
    kernel.register_root(base)
    return kernel


def _forged_root():
    prop = Proposition(
        "p-forged", "The board approved the merger.", EpistemicStatus.FACT,
        OriginStatus.HUMAN_ORIGINATED, authority=AuthorityStatus.EXECUTED,
        canonical_state=CanonicalState.CANONICAL,
        authorization_refs=("auth-does-not-exist",), source_refs=("minutes",),
    )
    return Artifact("root-forged", "x", (prop,), Actor("bot", ActorKind.SYSTEM))


def _unsourced_fact_root():
    prop = Proposition(
        "p-fact", "Water boils at 100C at sea level.", EpistemicStatus.FACT,
        OriginStatus.EXTERNAL_ORIGINATED,
    )
    return Artifact("root-unsourced", "x", (prop,), Actor("bot", ActorKind.SYSTEM))


def _plain_root(artifact_id, content, *, created_at=FIXED):
    """A root that admit_root accepts: nothing it asserts needs backing."""
    prop = Proposition(
        "p-plain",
        "The queue fell.",
        EpistemicStatus.UNKNOWN,
        OriginStatus.MACHINE_ORIGINATED,
        uncertainty=Uncertainty(UncertaintyState.UNKNOWN, "unobserved"),
    )
    return Artifact(artifact_id, content, (prop,), Actor.system("plain"), created_at=created_at)


def _refusing_verifier():
    """A verifier that refuses everything and records that it was asked."""
    calls = []

    class Refusing(IndependentVerifier):
        def verify(self, input_artifacts, output, record, registry):
            calls.append(record.transformation_id)
            native = super().verify(input_artifacts, output, record, registry)
            return replace(
                native,
                status=VerificationStatus.REJECT,
                violations=(Violation("CUSTOM_VERIFIER", None, None, "the supplied verifier decided"),),
            )

    return Refusing(), calls


# ---------------------------------------------------------------- availability


def test_cns_is_seen_as_available():
    assert cns_available() is True


# ---------------------------------------------------------------- the mapping


def test_an_unchanged_transformation_maps_to_pass_at_the_omega_end():
    base, registry = build_ground_truth()
    output, record = _derive(base, "same")
    native = IndependentVerifier().verify(base, output, record, registry)
    assert native.status is VerificationStatus.PASS
    verdict = verify_to_cns(base, output, record, registry)
    assert verdict.outcome is PASS
    assert verdict.position is OMEGA
    assert verdict.gate == "conservation"
    assert not verdict.blocking()
    assert verdict.reason == "PASS"


def test_a_declared_transformation_maps_to_pass_and_keeps_what_was_left_unverified():
    base, registry = build_ground_truth()
    output, record = legitimate_transformation(base, 1)
    native = IndependentVerifier().verify(base, output, record, registry)
    assert native.status is VerificationStatus.PASS_WITH_DECLARED_TRANSFORMATION
    verdict = verify_to_cns(base, output, record, registry)
    assert verdict.outcome is PASS
    assert "PASS_WITH_DECLARED_TRANSFORMATION" in verdict.reason
    assert "semantic_content_equivalence" in verdict.reason


def test_a_rejection_maps_to_terminal_breach_and_names_every_violation_code():
    base, registry = build_ground_truth()
    output, record, case_registry = hostile_cases()[0].build(base)
    native = IndependentVerifier().verify(base, output, record, case_registry)
    assert native.status is VerificationStatus.REJECT and len(native.violations) > 1
    verdict = verify_to_cns(base, output, record, case_registry)
    assert verdict.outcome is BREACH
    assert verdict.blocking()
    assert verdict.reason.startswith("REJECT: ")
    for violation in native.violations:
        assert violation.code in verdict.reason


@pytest.mark.parametrize("status", list(VerificationStatus), ids=lambda s: s.value)
def test_only_an_accepted_status_maps_to_pass(status):
    """Covers UNVERIFIABLE, which the verifier defines but which no current
    path through ``verify`` produces, by handing the connector a result."""
    base, registry = build_ground_truth()
    output, record = legitimate_transformation(base, 1)
    candidate = TransformationCandidate(base, output, record)
    native = IndependentVerifier().verify(base, output, record, registry)
    hand_built = replace(
        native,
        status=status,
        unverifiable_properties=("independent_source_identity",),
    )
    verdict = to_cns_result(hand_built, candidate)
    assert (verdict.outcome is PASS) is hand_built.accepted
    assert verdict.outcome in (PASS, BREACH)
    if status is VerificationStatus.UNVERIFIABLE:
        assert verdict.outcome is BREACH
        assert "UNVERIFIABLE" in verdict.reason
        assert "independent_source_identity" in verdict.reason


@pytest.mark.parametrize(SAMPLE_ARGS, SAMPLES, ids=SAMPLE_IDS)
def test_the_connector_agrees_with_the_kernels_own_verdict(label, base, output, record, registry):
    """The translation must not change what the kernel decided."""
    native = IndependentVerifier().verify(base, output, record, registry)
    candidate = TransformationCandidate(base, output, record)
    verdict = CnsGate(registry).check(candidate)
    assert (verdict.outcome is PASS) is native.accepted
    assert verdict.blocking() is (not native.accepted)
    assert cns_gate.resolve([verdict]) is verdict.outcome
    # The kernel models no retry, so none is ever invented.
    assert verdict.outcome in (PASS, BREACH)
    assert verdict.outcome is not cns_gate.GateOutcome.RETRY
    # The verdict is about this transformation and nothing else.
    assert verdict.bound()
    assert verdict.binds(
        "transformation", transformation_digest(candidate)
    )


@pytest.mark.parametrize(SAMPLE_ARGS, SAMPLES, ids=SAMPLE_IDS)
def test_submit_to_cns_leaves_the_kernel_exactly_as_a_direct_submit_does(
    label, base, output, record, registry
):
    native_kernel = _twin(base, registry)
    connected_kernel = _twin(base, registry)
    native = native_kernel.submit(base, output, record)
    verdict = submit_to_cns(connected_kernel, base, output, record)
    assert (verdict.outcome is PASS) is native.accepted
    assert connected_kernel.ledger.snapshot() == native_kernel.ledger.snapshot()
    assert len(connected_kernel.ledger.reports()) == 1


def test_a_ledger_refusal_is_a_terminal_breach_and_the_kernel_keeps_its_report():
    base, registry = build_ground_truth()
    output, record = legitimate_transformation(base, 1)
    native_kernel = _twin(base, registry)
    connected_kernel = _twin(base, registry)

    assert native_kernel.submit(base, output, record).accepted
    assert submit_to_cns(connected_kernel, base, output, record).outcome is PASS

    # A replay: verification accepts it again and the ledger refuses the commit.
    with pytest.raises(LedgerError, match="duplicate artifact ID"):
        native_kernel.submit(base, output, record)
    verdict = submit_to_cns(connected_kernel, base, output, record)
    assert verdict.outcome is BREACH
    assert verdict.position is OMEGA
    assert "ledger refused" in verdict.reason
    assert "duplicate artifact ID" in verdict.reason
    assert verdict.binds("transformation", transformation_digest(
        TransformationCandidate(base, output, record)))
    assert connected_kernel.ledger.snapshot() == native_kernel.ledger.snapshot()
    assert len(connected_kernel.ledger.reports()) == 2


def test_submit_to_cns_labels_the_verdict_with_the_subject_on_every_path():
    base, registry = build_ground_truth()
    output, record = legitimate_transformation(base, 1)
    digest = transformation_digest(TransformationCandidate(base, output, record))
    kernel = _twin(base, registry)

    accepted = submit_to_cns(kernel, base, output, record, subject="summary-7")
    assert accepted.outcome is PASS
    assert accepted.subject == "summary-7" and accepted.binds("summary-7", digest)

    # The ledger refuses the replay: the verdict made on that path is labelled too.
    refused = submit_to_cns(kernel, base, output, record, subject="summary-8")
    assert refused.outcome is BREACH and "ledger refused" in refused.reason
    assert refused.subject == "summary-8" and refused.binds("summary-8", digest)

    bad_output, bad_record, bad_registry = hostile_cases()[0].build(base)
    rejected = submit_to_cns(
        _twin(base, bad_registry), base, bad_output, bad_record, subject="summary-9"
    )
    assert rejected.outcome is BREACH
    assert rejected.subject == "summary-9"

    assert submit_to_cns(_twin(base, registry), base, output, record).subject == "transformation"


def test_submit_to_cns_lets_a_kernel_error_that_is_not_a_ledger_refusal_propagate():
    """Only LedgerError is a refusal. Anything else is not relabelled as one."""
    base, registry = build_ground_truth()
    output, good = legitimate_transformation(base, 1)

    # The kernel's own ValueError for a non-finite declaration it cannot compare.
    record = _with_non_finite_declaration(good, float("nan"), matching=True)
    kernel = _twin(base, registry)
    before = kernel.ledger.snapshot()
    with pytest.raises(ValueError, match="non-finite"):
        submit_to_cns(kernel, base, output, record)
    assert kernel.ledger.snapshot() == before
    assert kernel.ledger.reports() == ()

    # An error from a verifier the kernel was given.
    class Exploding(IndependentVerifier):
        def verify(self, input_artifacts, output, record, registry):
            raise RuntimeError("the verifier failed")

    broken = ConservationKernel(registry=registry, verifier=Exploding())
    broken.register_root(base)
    with pytest.raises(RuntimeError, match="the verifier failed"):
        submit_to_cns(broken, base, output, good)
    assert broken.ledger.reports() == ()


def test_an_unregistered_parent_is_a_terminal_breach_not_a_raise():
    base, registry = build_ground_truth()
    output, record = legitimate_transformation(base, 1)
    native_kernel = ConservationKernel(registry=registry)
    connected_kernel = ConservationKernel(registry=registry)
    with pytest.raises(LedgerError, match="not in the ledger"):
        native_kernel.submit(base, output, record)
    verdict = submit_to_cns(connected_kernel, base, output, record)
    assert verdict.outcome is BREACH
    assert "not in the ledger" in verdict.reason
    assert connected_kernel.ledger.snapshot() == native_kernel.ledger.snapshot()
    assert connected_kernel.ledger.artifacts() == ()


def test_a_multi_input_transformation_is_judged_and_bound_to_both_inputs():
    inputs, output, record, registry = _two_inputs()
    native = IndependentVerifier().verify(inputs, output, record, registry)
    assert native.status is VerificationStatus.PASS
    verdict = verify_to_cns(inputs, output, record, registry)
    assert verdict.outcome is PASS
    candidate = TransformationCandidate(inputs, output, record)
    assert verdict.binds("transformation", transformation_digest(candidate))
    # Dropping an input is a different candidate, and the kernel rejects it.
    short = verify_to_cns(inputs[:1], output, record, registry)
    assert short.outcome is BREACH
    assert not short.binds("transformation", transformation_digest(candidate))


# ---------------------------------------------------------------- binding


def test_every_verdict_is_bound_to_the_transformation_it_judged():
    base, registry = build_ground_truth()
    output, record, case_registry = hostile_cases()[0].build(base)
    candidate = TransformationCandidate(base, output, record)
    verdict = verify_to_cns(base, output, record, case_registry, subject="proposal-1")
    assert verdict.bound()
    assert cns_gate.unbound([verdict]) == ()
    digest = transformation_digest(candidate)
    assert len(digest) == 64 and verdict.subject_digest == digest
    assert verdict.binds("proposal-1", digest)
    # Not transplantable onto a different transformation, or a different label.
    other_output, other_record = legitimate_transformation(base, 1)
    other = transformation_digest(TransformationCandidate(base, other_output, other_record))
    assert not verdict.binds("proposal-1", other)
    assert not verdict.binds("proposal-2", digest)


def test_the_digest_is_the_cns_digest_of_the_judged_content_and_is_stable():
    candidate = _pinned_candidate()
    artifacts = list(candidate.inputs)
    expected = cns_gate.subject_digest({
        "kind": "transformation",
        "transformation_id": candidate.record.transformation_id,
        "input_artifacts": [
            {"artifact_id": a.artifact_id, "artifact_digest": a.artifact_digest}
            for a in artifacts
        ],
        "output_artifact": {
            "artifact_id": candidate.output.artifact_id,
            "artifact_digest": candidate.output.artifact_digest,
        },
        "record_digest": candidate.record.canonical_digest(),
    })
    assert transformation_digest(candidate) == expected
    # Pinned: a change to what the kernel calls "the same transformation"
    # must be a decision somebody makes, not something that slips through.
    assert expected == "40bc2eced706163477d555a811bfa34c2d9dd5f011c1d07fb098fa5fc2a93320"


def test_the_digest_moves_when_anything_judged_moves():
    candidate = _pinned_candidate()
    base_digest = transformation_digest(candidate)
    record = candidate.record

    def digest(**changes):
        return transformation_digest(replace(candidate, **changes))

    (declared,) = record.declared_changes
    variants = {
        "transformation_id": digest(record=replace(record, transformation_id="pin-tx-2")),
        "declared reason": digest(record=replace(
            record, declared_changes=(replace(declared, reason="reworded again"),))),
        "declared changes dropped": digest(record=replace(record, declared_changes=())),
        "authorization refs": digest(record=replace(record, authorization_refs=("auth-x",))),
        "output content": digest(output=Artifact(
            "pin-out", "different output", candidate.output.propositions,
            candidate.output.producer, parent_artifact_ids=("pin-in",), version=2,
            created_at=FIXED)),
        "input content": digest(inputs=Artifact(
            "pin-in", "different input", candidate.inputs[0].propositions,
            candidate.inputs[0].producer, created_at=FIXED)),
    }
    for what, value in variants.items():
        assert value != base_digest, what
    assert len(set(variants.values())) == len(variants)


def test_the_order_of_the_inputs_is_part_of_what_is_judged():
    inputs, output, record, _ = _two_inputs()
    forward = transformation_digest(TransformationCandidate(inputs, output, record))
    backward = transformation_digest(TransformationCandidate(inputs[::-1], output, record))
    assert forward != backward


def test_a_single_artifact_and_a_one_element_sequence_are_the_same_candidate():
    candidate = _pinned_candidate()
    source = candidate.inputs[0]
    same = TransformationCandidate([source], candidate.output, candidate.record)
    assert transformation_digest(same) == transformation_digest(candidate)


def test_the_registry_is_the_witness_not_the_judged_content():
    """The digest binds the transformation. The registry it was judged against
    is deliberately outside it (see the module docstring)."""
    base, registry = build_ground_truth()
    output, record = legitimate_transformation(base, 1)
    candidate = TransformationCandidate(base, output, record)
    before = transformation_digest(candidate)
    registry.add_evidence(EvidenceRecord(
        evidence_id="ev-extra", subject_id="p-human-fact",
        kind=EvidenceKind.SOURCE_OBSERVATION, provided_by=Actor.external("witness"),
    ))
    assert transformation_digest(candidate) == before


def test_a_verdict_cannot_be_lifted_onto_a_different_candidate():
    base, registry = build_ground_truth()
    output, record = legitimate_transformation(base, 1)
    result = IndependentVerifier().verify(base, output, record, registry)
    other_output, other_record = _derive(base, "other")
    other = TransformationCandidate(base, other_output, other_record)
    with pytest.raises(ValueError, match="was not issued for this candidate"):
        to_cns_result(result, other)
    # And the same result still binds to the candidate it was issued for.
    own = TransformationCandidate(base, output, record)
    assert to_cns_result(result, own).outcome is PASS


def test_a_result_for_other_ids_is_refused_whichever_id_differs():
    """Each of the three ids is checked on its own, so a result that matches
    the candidate on two of them is still not that candidate's result."""
    base, registry = build_ground_truth()
    output, record = legitimate_transformation(base, 1)
    candidate = TransformationCandidate(base, output, record)
    native = IndependentVerifier().verify(base, output, record, registry)
    assert to_cns_result(native, candidate).outcome is PASS
    for field, value in (
        ("transformation_id", "tx-other"),
        ("output_artifact_id", "artifact-other"),
        ("input_artifact_ids", ("artifact-other",)),
        ("input_artifact_ids", ()),
    ):
        with pytest.raises(ValueError, match="was not issued for this candidate"):
            to_cns_result(replace(native, **{field: value}), candidate)


def test_a_result_for_the_inputs_in_another_order_is_refused():
    inputs, output, record, registry = _two_inputs()
    candidate = TransformationCandidate(inputs, output, record)
    native = IndependentVerifier().verify(inputs, output, record, registry)
    assert to_cns_result(native, candidate).outcome is PASS
    backward = replace(native, input_artifact_ids=native.input_artifact_ids[::-1])
    with pytest.raises(ValueError, match="was not issued for this candidate"):
        to_cns_result(backward, candidate)


def test_the_gate_refuses_altered_content_under_the_same_ids_because_it_runs_the_verifier():
    """``VerificationResult`` carries ids and no content digest, so
    ``to_cns_result`` cannot tell a result for the same ids over different
    content (its docstring says so). The gate never has to: it verifies the
    candidate it binds."""
    base, registry = build_ground_truth()
    output, record = legitimate_transformation(base, 1)
    assert verify_to_cns(base, output, record, registry).outcome is PASS
    tampered = Artifact(
        output.artifact_id,
        "tampered " + output.content,
        output.propositions,
        output.producer,
        parent_artifact_ids=output.parent_artifact_ids,
        version=output.version,
        functional_contract=output.functional_contract,
        created_at=output.created_at,
    )
    assert tampered.artifact_id == output.artifact_id
    assert tampered.artifact_digest != output.artifact_digest
    verdict = verify_to_cns(base, tampered, record, registry)
    assert verdict.outcome is BREACH
    assert verdict.bound()
    assert not verdict.binds(
        "transformation", transformation_digest(TransformationCandidate(base, output, record))
    )


def test_an_accepted_result_that_lists_violations_fails_closed():
    """The kernel never produces one, but ``accepted`` alone would read it as a pass."""
    base, registry = build_ground_truth()
    output, record = legitimate_transformation(base, 1)
    candidate = TransformationCandidate(base, output, record)
    native = IndependentVerifier().verify(base, output, record, registry)
    hand_built = replace(
        native,
        status=VerificationStatus.PASS,
        violations=(Violation("UNDECLARED_CHANGE", Dimension.CONTENT, "p-x", "hand built"),),
    )
    assert hand_built.accepted
    verdict = to_cns_result(hand_built, candidate)
    assert verdict.outcome is BREACH
    assert verdict.bound()
    assert "inconsistent" in verdict.reason and "UNDECLARED_CHANGE" in verdict.reason


def test_a_root_verdict_binds_the_content_of_the_root_not_only_its_id():
    """Two different roots with one id must not share a digest, or a PASS for one
    could be carried onto the other."""
    first = _plain_root("root-same-id", "first content")
    second = _plain_root("root-same-id", "second content")
    assert first.artifact_id == second.artifact_id
    assert first.artifact_digest != second.artifact_digest
    assert root_digest(first) != root_digest(second)
    verdict = CnsRootAdmissionGate(ConservationKernel()).check(first)
    assert verdict.outcome is PASS
    assert verdict.binds("root", root_digest(first))
    assert not verdict.binds("root", root_digest(second))


def test_the_root_digest_is_the_cns_digest_of_the_judged_content_and_is_stable():
    root = _plain_root("pin-root", "pinned root content")
    expected = cns_gate.subject_digest({
        "kind": "root_artifact",
        "artifact_id": root.artifact_id,
        "artifact_digest": root.artifact_digest,
    })
    assert root_digest(root) == expected
    # Pinned, like the transformation digest: a decision, not a slip.
    assert expected == "69bac9b60ce9910a399e45b8b37bb82c27083978423a6b234bda4afb1b00ccc1"


# ---------------------------------------------------------------- content CNS cannot bind


def _with_non_finite_declaration(record, value, *, matching):
    """A record the kernel constructs fine but cannot canonicalize."""
    if matching:
        (declared,) = record.declared_changes
        return replace(record, declared_changes=(replace(declared, from_value=value),))
    extra = DeclaredChange("p-elsewhere", Dimension.CONTENT, value, 1, "non-finite")
    return replace(record, declared_changes=record.declared_changes + (extra,))


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")], ids=repr)
def test_a_non_finite_declaration_the_kernel_rejects_is_an_unbound_terminal_breach(value):
    base, registry = build_ground_truth()
    output, good = legitimate_transformation(base, 1)
    record = _with_non_finite_declaration(good, value, matching=False)
    native = IndependentVerifier().verify(base, output, record, registry)
    assert native.status is VerificationStatus.REJECT

    verdict = verify_to_cns(base, output, record, registry)
    assert verdict.outcome is BREACH
    assert not verdict.bound()
    assert verdict.subject_digest == ""
    assert cns_gate.unbound([verdict]) == ("conservation",)
    assert "unbound" in verdict.reason and "DECLARED_CHANGE_NOT_OBSERVED" in verdict.reason
    with pytest.raises(ValueError):
        transformation_digest(TransformationCandidate(base, output, record))


def test_an_unbindable_candidate_is_never_a_pass_even_for_an_accepted_result():
    base, registry = build_ground_truth()
    output, good = legitimate_transformation(base, 1)
    record = _with_non_finite_declaration(good, float("nan"), matching=False)
    candidate = TransformationCandidate(base, output, record)
    accepted = replace(
        IndependentVerifier().verify(base, output, good, registry),
        status=VerificationStatus.PASS,
        violations=(),
    )
    assert accepted.accepted
    verdict = to_cns_result(accepted, candidate)
    assert verdict.outcome is BREACH
    assert not verdict.bound()


def test_where_the_kernel_itself_raises_on_a_non_finite_declaration_so_does_the_connector():
    """No kernel verdict exists to translate, so none is invented."""
    base, registry = build_ground_truth()
    output, good = legitimate_transformation(base, 1)
    record = _with_non_finite_declaration(good, float("nan"), matching=True)
    with pytest.raises(ValueError, match="non-finite"):
        IndependentVerifier().verify(base, output, record, registry)
    with pytest.raises(ValueError, match="non-finite"):
        verify_to_cns(base, output, record, registry)
    with pytest.raises(ValueError, match="non-finite"):
        CnsGate(registry).check(TransformationCandidate(base, output, record))


def _nested(depth):
    value = 1
    for _ in range(depth):
        value = [value]
    return value


def _accepted_with_a_duplicate_non_finite_declaration():
    """The verifier stops at the first matching declaration, so a second one
    for the same subject and dimension may hold NaN and still be accepted."""
    base, registry = build_ground_truth()
    output, good = legitimate_transformation(base, 1)
    (declared,) = good.declared_changes
    record = replace(
        good,
        declared_changes=(declared, replace(declared, from_value=float("nan"))),
    )
    return base, output, record, registry


def test_a_non_finite_duplicate_declaration_the_verifier_accepts_is_still_an_unbound_breach():
    base, output, record, registry = _accepted_with_a_duplicate_non_finite_declaration()
    native = IndependentVerifier().verify(base, output, record, registry)
    assert native.status is VerificationStatus.PASS_WITH_DECLARED_TRANSFORMATION
    assert native.accepted
    with pytest.raises(ValueError, match="non-finite"):
        transformation_digest(TransformationCandidate(base, output, record))

    verdict = verify_to_cns(base, output, record, registry)
    assert verdict.outcome is BREACH
    assert not verdict.bound()
    assert cns_gate.unbound([verdict]) == ("conservation",)
    assert "unbound" in verdict.reason and "PASS_WITH_DECLARED_TRANSFORMATION" in verdict.reason
    # verify alone writes nothing, so the "committed" note belongs to submit only.
    assert "ledger" not in verdict.reason


def test_submit_to_cns_says_when_the_ledger_holds_what_the_verdict_refuses():
    base, output, record, registry = _accepted_with_a_duplicate_non_finite_declaration()
    native_kernel = _twin(base, registry)
    connected_kernel = _twin(base, registry)
    assert native_kernel.submit(base, output, record).accepted

    verdict = submit_to_cns(connected_kernel, base, output, record)
    assert verdict.outcome is BREACH
    assert not verdict.bound()
    assert "committed the output to the ledger" in verdict.reason
    # The kernel did exactly what a direct submit does, and holds the output.
    for kernel in (native_kernel, connected_kernel):
        assert [t.transformation_id for t in kernel.ledger.transformations()] == [
            record.transformation_id
        ]
        assert output.artifact_id in [a.artifact_id for a in kernel.ledger.artifacts()]
        assert len(kernel.ledger.reports()) == 1


def test_a_rejection_that_cannot_be_digested_does_not_claim_the_ledger_holds_it():
    base, registry = build_ground_truth()
    output, good = legitimate_transformation(base, 1)
    record = _with_non_finite_declaration(good, float("nan"), matching=False)
    kernel = _twin(base, registry)
    verdict = submit_to_cns(kernel, base, output, record)
    assert verdict.outcome is BREACH and not verdict.bound()
    assert "ledger" not in verdict.reason
    assert kernel.ledger.transformations() == ()


def test_content_nested_past_the_recursion_limit_is_an_unbound_breach_not_a_crash(monkeypatch):
    """Deterministic: make the canonical form overflow, wherever the stack is."""
    base, registry = build_ground_truth()
    output, record = legitimate_transformation(base, 1)

    def overflow(self):
        raise RecursionError("maximum recursion depth exceeded")

    monkeypatch.setattr(TransformationRecord, "canonical_digest", overflow)
    verdict = verify_to_cns(base, output, record, registry)
    assert verdict.outcome is BREACH
    assert not verdict.bound()
    assert "unbound" in verdict.reason and "nested too deeply" in verdict.reason
    kernel = _twin(base, registry)
    submitted = submit_to_cns(kernel, base, output, record)
    assert submitted.outcome is BREACH and not submitted.bound()


def test_a_really_deep_declared_value_is_a_verdict_wherever_the_kernel_returns_one():
    """With real input. How deep is "too deep" depends on the interpreter and the
    stack, so scan for the window in which the kernel can still build and judge
    the record but its canonical form overflows. There, the connector must
    return the unbound breach, not raise. (Where the kernel's own ``verify``
    raises there is no verdict to translate, and the error is the kernel's.)"""
    base, registry = build_ground_truth()
    output, good = legitimate_transformation(base, 1)
    (declared,) = good.declared_changes
    overflowing = 0
    for depth in range(200, 3000):
        try:
            record = replace(
                good,
                declared_changes=(replace(declared, subject_id="p-elsewhere", to_value=_nested(depth)),),
            )
        except RecursionError:
            break
        try:
            record.canonical_digest()
        except RecursionError:
            pass
        else:
            continue
        overflowing += 1
        try:
            native = IndependentVerifier().verify(base, output, record, registry)
        except RecursionError:
            continue
        assert not native.accepted  # the content change it leaves undeclared is refused
        try:
            verdict = verify_to_cns(base, output, record, registry)
        except RecursionError as exc:
            frames = {frame.name for frame in traceback.extract_tb(exc.__traceback__)}
            assert "verify" in frames, f"depth {depth}: the connector let the overflow escape"
            continue
        assert verdict.outcome is BREACH and not verdict.bound(), depth
    if not overflowing:
        pytest.skip("no depth on this interpreter builds a record whose canonical form overflows")


# ---------------------------------------------------------------- the gate classes


def test_the_transformation_gate_satisfies_the_cns_gate_protocol_at_omega():
    _, registry = build_ground_truth()
    gate = CnsGate(registry)
    assert isinstance(gate, cns_gate.Gate)
    assert gate.name == "conservation"
    assert gate.position is OMEGA


def test_the_root_admission_gate_satisfies_the_cns_gate_protocol_at_alpha():
    gate = CnsRootAdmissionGate(ConservationKernel())
    assert isinstance(gate, cns_gate.Gate)
    assert gate.name == "root_admission"
    assert gate.position is ALPHA


@pytest.mark.parametrize(SAMPLE_ARGS, SAMPLES, ids=SAMPLE_IDS)
def test_the_gate_judges_the_same_way_as_the_verifier_it_wraps(label, base, output, record, registry):
    verifier = IndependentVerifier()
    candidate = TransformationCandidate(base, output, record)
    gate = CnsGate(registry, verifier)
    assert gate.check(candidate) == to_cns_result(
        verifier.verify(base, output, record, registry), candidate
    )


def test_the_gate_honours_a_verifier_it_is_given_and_the_chain_and_helper_pass_it_on():
    base, registry = build_ground_truth()
    output, record = legitimate_transformation(base, 1)
    candidate = TransformationCandidate(base, output, record)
    assert CnsGate(registry).check(candidate).outcome is PASS

    verifier, calls = _refusing_verifier()
    verdict = CnsGate(registry, verifier).check(candidate)
    assert verdict.outcome is BREACH and "CUSTOM_VERIFIER" in verdict.reason
    assert calls == [record.transformation_id]

    verifier, calls = _refusing_verifier()
    assert verify_to_cns(base, output, record, registry, verifier=verifier).outcome is BREACH
    assert calls == [record.transformation_id]

    verifier, calls = _refusing_verifier()
    (gate,) = cns_chain(registry, verifier).omega
    assert gate.check(candidate).outcome is BREACH
    assert calls == [record.transformation_id]


def test_the_subject_given_to_a_gate_or_a_chain_labels_the_verdict():
    base, registry = build_ground_truth()
    output, record = legitimate_transformation(base, 1)
    candidate = TransformationCandidate(base, output, record)
    digest = transformation_digest(candidate)
    assert CnsGate(registry).check(candidate).subject == "transformation"
    labelled = CnsGate(registry, subject="gate-subject").check(candidate)
    assert labelled.subject == "gate-subject" and labelled.binds("gate-subject", digest)
    (gate,) = cns_chain(registry, subject="chain-subject").omega
    chained = gate.check(candidate)
    assert chained.subject == "chain-subject" and chained.binds("chain-subject", digest)


def test_judging_a_candidate_writes_nothing():
    base, registry = build_ground_truth()
    output, record = legitimate_transformation(base, 1)
    before = registry.snapshot()
    CnsGate(registry).check(TransformationCandidate(base, output, record))
    assert registry.snapshot() == before


def test_the_gates_refuse_a_candidate_of_the_wrong_kind():
    base, registry = build_ground_truth()
    with pytest.raises(TypeError, match="TransformationCandidate"):
        CnsGate(registry).check(base)
    with pytest.raises(TypeError, match="Artifact"):
        CnsRootAdmissionGate(ConservationKernel()).check("not an artifact")
    output, record = legitimate_transformation(base, 1)
    with pytest.raises(TypeError):
        TransformationCandidate(base, "not an artifact", record)
    with pytest.raises(TypeError):
        TransformationCandidate(base, output, "not a record")
    with pytest.raises(TypeError):
        TransformationCandidate([base, object()], output, record)


def test_an_unlabelled_verdict_is_refused_rather_than_issued_unbound():
    base, registry = build_ground_truth()
    output, record = legitimate_transformation(base, 1)
    with pytest.raises(ValueError, match="subject"):
        CnsGate(registry, subject="")
    with pytest.raises(ValueError, match="subject"):
        verify_to_cns(base, output, record, registry, subject="")
    with pytest.raises(ValueError, match="subject"):
        submit_to_cns(_twin(base, registry), base, output, record, subject="")


def test_the_chain_is_outcome_only_and_says_so():
    _, registry = build_ground_truth()
    chain = cns_chain(registry)
    assert chain.misplaced() == ()
    assert chain.alpha == ()
    assert len(chain.omega) == 1
    assert chain.complete() is False  # the two kernel gates are not one request


def test_the_chain_runs_through_cns_resolution():
    base, registry = build_ground_truth()
    chain = cns_chain(registry)
    (gate,) = chain.omega
    good_output, good_record = legitimate_transformation(base, 1)
    assert cns_gate.resolve(
        [gate.check(TransformationCandidate(base, good_output, good_record))]
    ) is PASS
    bad_output, bad_record, bad_registry = hostile_cases()[0].build(base)
    (bad_gate,) = cns_chain(bad_registry).omega
    assert cns_gate.resolve(
        [bad_gate.check(TransformationCandidate(base, bad_output, bad_record))]
    ) is BREACH


# ---------------------------------------------------------------- root admission (ALPHA)


def test_an_admissible_root_maps_to_pass_at_the_alpha_end():
    base, registry = build_ground_truth()
    kernel = ConservationKernel(registry=registry)
    verdict = CnsRootAdmissionGate(kernel).check(base)
    assert kernel.admit_root(base) == ()
    assert verdict.outcome is PASS
    assert verdict.position is ALPHA
    assert verdict.gate == "root_admission"
    assert verdict.reason == "root admitted"
    assert verdict.binds("root", root_digest(base))


def test_a_forged_root_maps_to_terminal_breach_with_the_kernels_reasons():
    kernel = ConservationKernel()
    forged = _forged_root()
    reasons = kernel.admit_root(forged)
    assert reasons
    verdict = CnsRootAdmissionGate(kernel).check(forged)
    assert verdict.outcome is BREACH
    assert verdict.position is ALPHA
    assert verdict.blocking()
    for reason in reasons:
        assert reason in verdict.reason
    assert "authorization_refs not in registry" in verdict.reason


def _root_scenarios():
    """(label, root, registry, roots registered first). Some of these are refused
    by ``admit_root``; some only by the ledger, which ``admit_root`` never sees."""
    base, registry = build_ground_truth()
    derived, _ = _derive(base, "child")
    forged = _forged_root()
    forged_child = Artifact(
        "root-forged-child", "x", forged.propositions, Actor("bot", ActorKind.SYSTEM),
        parent_artifact_ids=(forged.artifact_id,), version=2,
    )
    same_id_other_content = Artifact(
        base.artifact_id, "other content under a registered id", base.propositions,
        base.producer,
    )
    return [
        ("fresh parentless root", base, registry, ()),
        ("forged root", forged, registry, ()),
        ("unsourced fact", _unsourced_fact_root(), registry, ()),
        ("derived artifact, not a root", derived, registry, ()),
        ("already registered", base, registry, (base,)),
        ("registered id, other content", same_id_other_content, registry, (base,)),
        ("forged and derived", forged_child, registry, ()),
    ]


ROOT_SCENARIOS = _root_scenarios()


@pytest.mark.parametrize(
    "label,root,registry,preregistered",
    ROOT_SCENARIOS,
    ids=[scenario[0] for scenario in ROOT_SCENARIOS],
)
def test_the_root_gate_refuses_exactly_what_register_root_refuses_and_registers_nothing(
    label, root, registry, preregistered
):
    kernel = ConservationKernel(registry=registry)
    for existing in preregistered:
        kernel.register_root(existing)
    before = kernel.ledger.snapshot()

    verdict = CnsRootAdmissionGate(kernel).check(root)
    assert kernel.ledger.snapshot() == before  # judging is not registering
    assert verdict.position is ALPHA and verdict.bound()

    try:
        kernel.register_root(root)
    except LedgerError as refused:  # RootAdmissionError is one
        assert verdict.outcome is BREACH, f"{label}: the kernel refuses it, the gate did not"
        assert verdict.blocking()
        assert str(refused) in verdict.reason
        assert root_refusals(kernel, root) != ()
        # RootAdmissionError is admit_root's refusal; the rest are the ledger's.
        assert isinstance(refused, RootAdmissionError) is bool(kernel.admit_root(root))
    else:
        assert verdict.outcome is PASS, f"{label}: the kernel accepts it, the gate refused"
        assert verdict.reason == "root admitted"


def test_admit_root_alone_does_not_see_what_the_ledger_refuses_but_the_gate_does():
    """The reason ``root_refusals`` exists. ``admit_root`` inspects propositions
    only, so a PASS made from its reasons would say the kernel accepts a root
    that ``register_root`` refuses."""
    base, registry = build_ground_truth()
    derived, _ = _derive(base, "child")
    kernel = ConservationKernel(registry=registry)
    kernel.register_root(base)
    gate = CnsRootAdmissionGate(kernel)

    assert kernel.admit_root(derived) == ()
    with pytest.raises(LedgerError, match="cannot already have parents"):
        kernel.register_root(derived)
    verdict = gate.check(derived)
    assert verdict.outcome is BREACH
    assert "cannot already have parents" in verdict.reason

    assert kernel.admit_root(base) == ()
    with pytest.raises(LedgerError, match="duplicate artifact ID"):
        kernel.register_root(base)
    verdict = gate.check(base)
    assert verdict.outcome is BREACH
    assert "duplicate artifact ID artifact-ground-truth" in verdict.reason

    # admission_to_cns_result translates the reasons it is given, no more.
    assert admission_to_cns_result(kernel.admit_root(base), base).outcome is PASS
    assert admission_to_cns_result(root_refusals(kernel, base), base).outcome is BREACH


def test_root_refusals_lists_the_propositions_reasons_first_then_the_ledgers():
    base, registry = build_ground_truth()
    forged = _forged_root()
    child = Artifact(
        "root-forged-child", "x", forged.propositions, Actor("bot", ActorKind.SYSTEM),
        parent_artifact_ids=(forged.artifact_id,), version=2,
    )
    kernel = ConservationKernel(registry=registry)
    reasons = root_refusals(kernel, child)
    assert reasons[: len(kernel.admit_root(child))] == kernel.admit_root(child)
    assert reasons[-1] == "an initial artifact cannot already have parents"
    assert root_refusals(kernel, base) == ()
    with pytest.raises(TypeError, match="Artifact"):
        root_refusals(kernel, "not an artifact")


def test_a_root_verdict_is_bound_to_the_root_it_judged():
    kernel = ConservationKernel()
    forged, other = _forged_root(), _unsourced_fact_root()
    verdict = CnsRootAdmissionGate(kernel, subject="root-a").check(forged)
    assert verdict.bound()
    assert verdict.binds("root-a", root_digest(forged))
    assert not verdict.binds("root-a", root_digest(other))
    assert not verdict.binds("root-b", root_digest(forged))
    # A root and a transformation over the same ids never share a digest.
    assert root_digest(forged) != transformation_digest(_pinned_candidate())


def test_admission_reasons_given_as_a_bare_string_are_refused():
    """tuple("") is empty, which would read as "no reasons": a PASS."""
    with pytest.raises(TypeError, match="sequence"):
        admission_to_cns_result("", _forged_root())
    with pytest.raises(TypeError, match="Artifact"):
        admission_to_cns_result((), "not an artifact")


def test_each_end_is_placed_where_cns_expects_it_and_resolves_fail_closed():
    base, registry = build_ground_truth()
    kernel = ConservationKernel(registry=registry)
    chain = cns_gate.GateChain(
        alpha=(CnsRootAdmissionGate(kernel),),
        omega=(CnsGate(registry),),
    )
    assert chain.misplaced() == ()
    # CNS calls this complete because both ends are filled, but the ends share no
    # request: each gate refuses the other's candidate. That false completeness
    # is why cns_chain holds the omega gate only and the README says to run the
    # root gate on its own.
    assert chain.complete() is True
    with pytest.raises(TypeError, match="TransformationCandidate"):
        chain.omega[0].check(base)
    with pytest.raises(TypeError, match="Artifact"):
        chain.alpha[0].check(TransformationCandidate(base, *legitimate_transformation(base, 1)))

    output, record = legitimate_transformation(base, 1)
    clean = chain.omega[0].check(TransformationCandidate(base, output, record))
    refused = chain.alpha[0].check(_forged_root())
    admitted = chain.alpha[0].check(base)
    assert cns_gate.resolve([admitted, clean]) is PASS
    assert cns_gate.resolve([refused, clean]) is BREACH
