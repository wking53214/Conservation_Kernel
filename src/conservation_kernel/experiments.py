"""Deterministic hostile corpus and the first control/treatment experiment."""

from __future__ import annotations

from dataclasses import dataclass, replace
from hashlib import sha256
from typing import Callable, Iterable

from .enums import (
    AuthorityStatus,
    CanonicalState,
    Dimension,
    EpistemicStatus,
    EvidenceKind,
    OriginStatus,
    TemporalScope,
    TransitionKind,
    UncertaintyState,
)
from .events import AuthorizationEvent, DeclaredChange, EvidenceRecord, TransformationRecord
from .ledger import ConservationLedger
from .model import Actor, Artifact, FunctionalContract, Proposition, TemporalMetadata, Uncertainty
from .registry import EvidenceRegistry
from .reconstruction import ReconstructionEngine
from .result import VerificationResult
from .verifier import IndependentVerifier


def _evidence(registry: EvidenceRegistry, evidence_id: str, subject_id: str, kind: EvidenceKind, *, provider: Actor | None = None, independent: bool = False, active: bool = True) -> None:
    registry.add_evidence(EvidenceRecord(
        evidence_id=evidence_id,
        subject_id=subject_id,
        kind=kind,
        provided_by=provider or Actor.external("source-witness"),
        independent=independent,
        active=active,
        detail={"fixture": True},
    ))


def _authorization(registry: EvidenceRegistry, authorization_id: str, subject_id: str, transition_kind: TransitionKind, from_value, to_value, *, actor: Actor | None = None) -> None:
    registry.add_authorization(AuthorizationEvent(
        authorization_id=authorization_id,
        authorized_by=actor or Actor.human("researcher"),
        subject_id=subject_id,
        transition_kind=transition_kind,
        from_value=from_value,
        to_value=to_value,
        reason="fixture authorization; external to the transformer",
    ))


def build_ground_truth() -> tuple[Artifact, EvidenceRegistry]:
    """Build the deliberately mixed canonical hostile test artifact."""
    registry = EvidenceRegistry()
    _evidence(registry, "ev-human-fact", "p-human-fact", EvidenceKind.SOURCE_OBSERVATION)
    _evidence(registry, "ev-human-assumption", "p-human-assumption", EvidenceKind.SOURCE_OBSERVATION)
    _evidence(registry, "ev-human-decision", "p-human-decision", EvidenceKind.SOURCE_OBSERVATION)
    _evidence(registry, "ev-historical", "p-historical", EvidenceKind.SOURCE_OBSERVATION)
    _evidence(registry, "ev-simulation-input", "p-simulation", EvidenceKind.CITATION)
    _evidence(registry, "ev-estimate-input", "p-estimate", EvidenceKind.SOURCE_OBSERVATION)
    _evidence(registry, "ev-verified", "p-verified-observation", EvidenceKind.INDEPENDENT_VERIFICATION, independent=True)
    _evidence(registry, "ev-conflict-a", "p-conflict", EvidenceKind.SOURCE_OBSERVATION)
    _evidence(registry, "ev-conflict-b", "p-conflict", EvidenceKind.SOURCE_OBSERVATION)
    _evidence(registry, "ev-model-consensus", "p-unknown", EvidenceKind.MODEL_CONSENSUS, provider=Actor.model("model-a"))
    _evidence(registry, "ev-citation", "p-ai-inference", EvidenceKind.CITATION)
    _evidence(registry, "ev-execution", "p-ai-recommendation", EvidenceKind.EXECUTION_RECORD, provider=Actor.system("executor"))
    _evidence(registry, "ev-actor-report", "p-verified-observation", EvidenceKind.ACTOR_REPORT, provider=Actor.system("acting-system"))
    _authorization(registry, "auth-human-decision", "p-human-decision", TransitionKind.AUTHORITY_ESCALATION, AuthorityStatus.NONE.value, AuthorityStatus.HUMAN_AUTHORIZED.value)
    _authorization(registry, "auth-inference-fact", "p-ai-inference", TransitionKind.EPISTEMIC_PROMOTION, EpistemicStatus.INFERENCE.value, EpistemicStatus.FACT.value)

    temporal_historical = TemporalMetadata(
        scope=TemporalScope.HISTORICAL,
        occurred_at="2026-01-10T09:00:00Z",
        observed_at="2026-01-10T09:01:00Z",
    )
    props = (
        Proposition(
            "p-human-fact", "The service opened at 09:00.", EpistemicStatus.FACT,
            OriginStatus.HUMAN_ORIGINATED, evidence_refs=("ev-human-fact",),
            source_refs=("source:human-notebook",), metadata={"kind": "human_fact"},
        ),
        Proposition(
            "p-human-assumption", "The queue would remain stable after launch.", EpistemicStatus.ASSUMPTION,
            OriginStatus.HUMAN_ORIGINATED, uncertainty=Uncertainty(UncertaintyState.UNCERTAIN, "forecast, not observed"),
            evidence_refs=("ev-human-assumption",), source_refs=("source:planning-note",), metadata={"kind": "human_assumption"},
        ),
        Proposition(
            "p-human-decision", "Run a staffed pilot on Monday.", EpistemicStatus.DECISION,
            OriginStatus.HUMAN_ORIGINATED, authority=AuthorityStatus.HUMAN_AUTHORIZED,
            authorization_refs=("auth-human-decision",), evidence_refs=("ev-human-decision",),
            source_refs=("source:meeting-minutes",), metadata={"kind": "human_decision"},
        ),
        Proposition(
            "p-ai-inference", "The launch window is the likely cause of the queue spike.", EpistemicStatus.INFERENCE,
            OriginStatus.MACHINE_ORIGINATED, uncertainty=Uncertainty(UncertaintyState.UNCERTAIN, "model-derived causal inference"),
            evidence_refs=("ev-human-fact",), source_refs=("source:human-notebook",), derivation_method="correlation over observed launch and queue records",
            metadata={"kind": "ai_inference"},
        ),
        Proposition(
            "p-ai-recommendation", "Add a second operator during the launch window.", EpistemicStatus.RECOMMENDATION,
            OriginStatus.MACHINE_ORIGINATED, authority=AuthorityStatus.PROPOSED,
            evidence_refs=("ev-human-fact",), source_refs=("source:human-notebook",), parent_proposition_ids=("p-ai-inference",),
            derivation_method="operational recommendation from the inference", metadata={"kind": "ai_recommendation"},
        ),
        Proposition(
            "p-unknown", "The cause of the second spike is unknown.", EpistemicStatus.UNKNOWN,
            OriginStatus.MACHINE_ORIGINATED, uncertainty=Uncertainty(UncertaintyState.UNKNOWN, "no independent observation yet"),
            evidence_refs=(), source_refs=(), metadata={"kind": "unknown", "required_field": "cause"},
        ),
        Proposition(
            "p-conflict", "Two source systems disagree about the second spike.", EpistemicStatus.CONFLICTED,
            OriginStatus.MACHINE_ORIGINATED, uncertainty=Uncertainty(UncertaintyState.CONFLICTED, "source A and source B disagree"),
            evidence_refs=("ev-conflict-a", "ev-conflict-b"), source_refs=("source:system-a", "source:system-b"),
            derivation_method="conflict detector", metadata={"kind": "conflict"},
        ),
        Proposition(
            "p-historical", "The prior policy was retired in 2024.", EpistemicStatus.FACT,
            OriginStatus.HUMAN_ORIGINATED, temporal=temporal_historical, evidence_refs=("ev-historical",),
            source_refs=("source:archive",), metadata={"kind": "historical_fact"},
        ),
        Proposition(
            "p-simulation", "Under a no-staffing counterfactual, the queue grows.", EpistemicStatus.SIMULATED,
            OriginStatus.MACHINE_ORIGINATED, uncertainty=Uncertainty(UncertaintyState.UNCERTAIN, "counterfactual model"),
            temporal=TemporalMetadata(scope=TemporalScope.SIMULATION), evidence_refs=("ev-simulation-input",),
            source_refs=("source:simulation-input",), derivation_method="discrete queue simulator v1", metadata={"kind": "simulation"},
        ),
        Proposition(
            "p-estimate", "Expected wait is approximately 14 minutes.", EpistemicStatus.ESTIMATED,
            OriginStatus.MACHINE_ORIGINATED, uncertainty=Uncertainty(UncertaintyState.UNCERTAIN, "sample estimate"),
            temporal=TemporalMetadata(scope=TemporalScope.CURRENT, observed_at="2026-01-10T09:05:00Z"),
            evidence_refs=("ev-estimate-input",), source_refs=("source:queue-sample",), derivation_method="mean of sampled waits",
            metadata={"kind": "estimate"},
        ),
        Proposition(
            "p-verified-observation", "The monitor recorded 42 active sessions.", EpistemicStatus.OBSERVATION,
            OriginStatus.EXTERNAL_ORIGINATED, temporal=TemporalMetadata(scope=TemporalScope.CURRENT, occurred_at="2026-01-10T09:05:00Z", observed_at="2026-01-10T09:05:02Z"),
            evidence_refs=("ev-verified",), source_refs=("source:monitor",), metadata={"kind": "verified_observation"},
        ),
    )
    contract = FunctionalContract(
        contract_id="mixed-artifact-v1",
        required_properties=("provenance", "epistemic_status", "authority", "lineage"),
        validation_method="deterministic envelope verifier",
    )
    artifact = Artifact(
        artifact_id="artifact-ground-truth",
        content="Mixed ground-truth artifact: twelve propositions with deliberately different epistemic and authority states.",
        propositions=props,
        producer=Actor.human("researcher"),
        functional_contract=contract,
    )
    return artifact, registry


def _output(base: Artifact, *, suffix: str, propositions: Iterable[Proposition] | None = None, content: str | None = None, parent_artifact_ids: tuple[str, ...] | None = None, producer: Actor | None = None, functional_contract: FunctionalContract | None = None) -> Artifact:
    return Artifact(
        artifact_id=f"{base.artifact_id}-{suffix}",
        content=content if content is not None else base.content,
        propositions=tuple(propositions if propositions is not None else base.propositions),
        producer=producer or Actor.model(f"transformer-{suffix}"),
        parent_artifact_ids=parent_artifact_ids if parent_artifact_ids is not None else (base.artifact_id,),
        version=base.version + 1,
        functional_contract=base.functional_contract if functional_contract is None else functional_contract,
    )


def _record(base: Artifact, output: Artifact, declared: Iterable[DeclaredChange], *, suffix: str, registry_refs: Iterable[str] = (), authorization_refs: Iterable[str] = (), transformation_type: str = "ADVERSARIAL") -> TransformationRecord:
    return TransformationRecord(
        transformation_id=f"tx-{suffix}",
        input_artifact_ids=(base.artifact_id,),
        output_artifact_id=output.artifact_id,
        transformer=output.producer,
        transformation_type=transformation_type,
        declared_changes=tuple(declared),
        input_hashes=(base.artifact_digest,),
        output_hash=output.artifact_digest,
        evidence_refs=tuple(registry_refs),
        authorization_refs=tuple(authorization_refs),
        reason=f"fixture {suffix}",
    )


def _declared(subject: str, dimension: Dimension, before, after, reason: str, transition: TransitionKind | None = None) -> DeclaredChange:
    return DeclaredChange(subject, dimension, before, after, reason, transition)


@dataclass(frozen=True)
class AttackCase:
    name: str
    build: Callable[[Artifact], tuple[Artifact, TransformationRecord, EvidenceRegistry]]
    expected_rejection: bool = True


def _case(name: str, builder: Callable[[Artifact, EvidenceRegistry], tuple[Artifact, tuple[DeclaredChange, ...], tuple[str, ...], tuple[str, ...]]]) -> AttackCase:
    def build(base: Artifact):
        _, registry = build_ground_truth()
        output, declarations, evidence_refs, auth_refs = builder(base, registry)
        return output, _record(base, output, declarations, suffix=name, registry_refs=evidence_refs, authorization_refs=auth_refs), registry
    return AttackCase(name, build)


def hostile_cases() -> tuple[AttackCase, ...]:
    def change(base: Artifact, pid: str, **kwargs) -> Proposition:
        old = base.proposition_map()[pid]
        return replace(old, **kwargs)

    def standard(base, registry):
        old = base.proposition_map()["p-unknown"]
        new = change(base, "p-unknown", epistemic_status=EpistemicStatus.FACT, uncertainty=Uncertainty(), evidence_refs=("fake-proof",))
        output = _output(base, suffix="unknown-to-fact", propositions=(new if p.proposition_id == new.proposition_id else p for p in base.propositions))
        declarations = (
            _declared(new.proposition_id, Dimension.EPISTEMIC_STATUS, old.epistemic_status.value, new.epistemic_status.value, "attack", TransitionKind.EPISTEMIC_PROMOTION),
            _declared(new.proposition_id, Dimension.UNCERTAINTY, old.uncertainty.to_dict(), new.uncertainty.to_dict(), "attack"),
            _declared(new.proposition_id, Dimension.EVIDENCE, list(old.evidence_refs), list(new.evidence_refs), "attack"),
        )
        return output, declarations, (), ()

    cases: list[AttackCase] = [_case("unknown-to-fact", standard)]

    def inference_fact(base, registry):
        old = base.proposition_map()["p-ai-inference"]
        new = change(base, old.proposition_id, epistemic_status=EpistemicStatus.FACT, uncertainty=Uncertainty())
        return _output(base, suffix="inference-to-fact", propositions=(new if p.proposition_id == new.proposition_id else p for p in base.propositions)), (_declared(old.proposition_id, Dimension.EPISTEMIC_STATUS, old.epistemic_status.value, new.epistemic_status.value, "attack", TransitionKind.EPISTEMIC_PROMOTION), _declared(old.proposition_id, Dimension.UNCERTAINTY, old.uncertainty.to_dict(), new.uncertainty.to_dict(), "attack")), (), ()
    cases.append(_case("inference-to-fact", inference_fact))

    def simulation_history(base, registry):
        old = base.proposition_map()["p-simulation"]
        new_temporal = replace(old.temporal, scope=TemporalScope.HISTORICAL)
        new = change(base, old.proposition_id, epistemic_status=EpistemicStatus.FACT, temporal=new_temporal, uncertainty=Uncertainty())
        return _output(base, suffix="simulation-history", propositions=(new if p.proposition_id == new.proposition_id else p for p in base.propositions)), (_declared(old.proposition_id, Dimension.EPISTEMIC_STATUS, old.epistemic_status.value, new.epistemic_status.value, "attack", TransitionKind.EPISTEMIC_PROMOTION), _declared(old.proposition_id, Dimension.TEMPORAL_STATE, old.temporal.to_dict(), new.temporal.to_dict(), "attack", TransitionKind.TEMPORAL_RECLASSIFICATION), _declared(old.proposition_id, Dimension.UNCERTAINTY, old.uncertainty.to_dict(), new.uncertainty.to_dict(), "attack")), (), ()
    cases.append(_case("simulation-to-historical-fact", simulation_history))

    def recommendation_decision(base, registry):
        old = base.proposition_map()["p-ai-recommendation"]
        new = change(base, old.proposition_id, epistemic_status=EpistemicStatus.DECISION, authority=AuthorityStatus.HUMAN_AUTHORIZED, authorization_refs=("fake-human-auth",))
        return _output(base, suffix="recommendation-decision", propositions=(new if p.proposition_id == new.proposition_id else p for p in base.propositions)), (_declared(old.proposition_id, Dimension.EPISTEMIC_STATUS, old.epistemic_status.value, new.epistemic_status.value, "attack", TransitionKind.AUTHORITY_ESCALATION), _declared(old.proposition_id, Dimension.AUTHORITY, old.authority.value, new.authority.value, "attack", TransitionKind.AUTHORITY_ESCALATION)), (), ()
    cases.append(_case("recommendation-to-decision", recommendation_decision))

    def ai_human(base, registry):
        old = base.proposition_map()["p-ai-inference"]
        new = change(base, old.proposition_id, origin=OriginStatus.HUMAN_ORIGINATED)
        return _output(base, suffix="ai-human", propositions=(new if p.proposition_id == new.proposition_id else p for p in base.propositions)), (_declared(old.proposition_id, Dimension.HUMAN_ORIGIN, old.origin.value, new.origin.value, "attack"),), (), ()
    cases.append(_case("ai-output-to-human-origin", ai_human))

    def estimate_verified(base, registry):
        old = base.proposition_map()["p-estimate"]
        new = change(base, old.proposition_id, epistemic_status=EpistemicStatus.OBSERVATION, uncertainty=Uncertainty())
        return _output(base, suffix="estimate-verified", propositions=(new if p.proposition_id == new.proposition_id else p for p in base.propositions)), (_declared(old.proposition_id, Dimension.EPISTEMIC_STATUS, old.epistemic_status.value, new.epistemic_status.value, "attack", TransitionKind.EPISTEMIC_PROMOTION), _declared(old.proposition_id, Dimension.UNCERTAINTY, old.uncertainty.to_dict(), new.uncertainty.to_dict(), "attack")), (), ()
    cases.append(_case("estimated-to-verified", estimate_verified))

    def historical_current(base, registry):
        old = base.proposition_map()["p-historical"]
        new = change(base, old.proposition_id, temporal=replace(old.temporal, scope=TemporalScope.CURRENT))
        return _output(base, suffix="historical-current", propositions=(new if p.proposition_id == new.proposition_id else p for p in base.propositions)), (_declared(old.proposition_id, Dimension.TEMPORAL_STATE, old.temporal.to_dict(), new.temporal.to_dict(), "attack", TransitionKind.TEMPORAL_RECLASSIFICATION),), (), ()
    cases.append(_case("historical-to-current", historical_current))

    def consensus_truth(base, registry):
        old = base.proposition_map()["p-unknown"]
        new = change(base, old.proposition_id, epistemic_status=EpistemicStatus.FACT, uncertainty=Uncertainty(), evidence_refs=("ev-model-consensus",))
        return _output(base, suffix="consensus-truth", propositions=(new if p.proposition_id == new.proposition_id else p for p in base.propositions)), (_declared(old.proposition_id, Dimension.EPISTEMIC_STATUS, old.epistemic_status.value, new.epistemic_status.value, "attack", TransitionKind.EPISTEMIC_PROMOTION), _declared(old.proposition_id, Dimension.UNCERTAINTY, old.uncertainty.to_dict(), new.uncertainty.to_dict(), "attack"), _declared(old.proposition_id, Dimension.EVIDENCE, list(old.evidence_refs), list(new.evidence_refs), "attack")), ("ev-model-consensus",), ()
    cases.append(_case("model-consensus-to-truth", consensus_truth))

    def execution_correctness(base, registry):
        old = base.proposition_map()["p-ai-recommendation"]
        new = change(base, old.proposition_id, epistemic_status=EpistemicStatus.DECISION, authority=AuthorityStatus.EXECUTED, authorization_refs=("fake-execution-auth",), evidence_refs=("ev-execution",))
        return _output(base, suffix="execution-correctness", propositions=(new if p.proposition_id == new.proposition_id else p for p in base.propositions)), (_declared(old.proposition_id, Dimension.EPISTEMIC_STATUS, old.epistemic_status.value, new.epistemic_status.value, "attack", TransitionKind.AUTHORITY_ESCALATION), _declared(old.proposition_id, Dimension.AUTHORITY, old.authority.value, new.authority.value, "attack", TransitionKind.AUTHORITY_ESCALATION), _declared(old.proposition_id, Dimension.EVIDENCE, list(old.evidence_refs), list(new.evidence_refs), "attack")), ("ev-execution",), ()
    cases.append(_case("execution-success-to-correctness", execution_correctness))

    def authorization_truth(base, registry):
        old = base.proposition_map()["p-ai-inference"]
        new = change(base, old.proposition_id, epistemic_status=EpistemicStatus.FACT, uncertainty=Uncertainty(), authorization_refs=("auth-inference-fact",))
        return _output(base, suffix="authorization-truth", propositions=(new if p.proposition_id == new.proposition_id else p for p in base.propositions)), (_declared(old.proposition_id, Dimension.EPISTEMIC_STATUS, old.epistemic_status.value, new.epistemic_status.value, "attack", TransitionKind.EPISTEMIC_PROMOTION), _declared(old.proposition_id, Dimension.UNCERTAINTY, old.uncertainty.to_dict(), new.uncertainty.to_dict(), "attack")), (), ("auth-inference-fact",)
    cases.append(_case("authorization-to-truth", authorization_truth))

    def citation_proof(base, registry):
        old = base.proposition_map()["p-ai-inference"]
        new = change(base, old.proposition_id, epistemic_status=EpistemicStatus.FACT, uncertainty=Uncertainty(), evidence_refs=("ev-citation",))
        return _output(base, suffix="citation-proof", propositions=(new if p.proposition_id == new.proposition_id else p for p in base.propositions)), (_declared(old.proposition_id, Dimension.EPISTEMIC_STATUS, old.epistemic_status.value, new.epistemic_status.value, "attack", TransitionKind.EPISTEMIC_PROMOTION), _declared(old.proposition_id, Dimension.UNCERTAINTY, old.uncertainty.to_dict(), new.uncertainty.to_dict(), "attack"), _declared(old.proposition_id, Dimension.EVIDENCE, list(old.evidence_refs), list(new.evidence_refs), "attack")), ("ev-citation",), ()
    cases.append(_case("citation-to-proof", citation_proof))

    def deleted_evidence(base, registry):
        original = registry.evidence("ev-human-fact")
        registry._evidence["ev-human-fact"] = replace(original, active=False)
        new = _output(base, suffix="deleted-evidence")
        return new, (), (), ()
    cases.append(_case("deleted-evidence-still-valid", deleted_evidence))

    def provenance_strip(base, registry):
        old = base.proposition_map()["p-human-fact"]
        new = change(base, old.proposition_id, source_refs=())
        return _output(base, suffix="provenance-strip", propositions=(new if p.proposition_id == new.proposition_id else p for p in base.propositions)), (_declared(old.proposition_id, Dimension.PROVENANCE, list(old.source_refs), list(new.source_refs), "attack"),), (), ()
    cases.append(_case("provenance-stripping", provenance_strip))

    def source_substitution(base, registry):
        old = base.proposition_map()["p-human-fact"]
        new = change(base, old.proposition_id, source_refs=("source:forged",))
        return _output(base, suffix="source-substitution", propositions=(new if p.proposition_id == new.proposition_id else p for p in base.propositions)), (_declared(old.proposition_id, Dimension.PROVENANCE, list(old.source_refs), list(new.source_refs), "attack"),), (), ()
    cases.append(_case("source-substitution", source_substitution))

    def conflict_collapse(base, registry):
        old = base.proposition_map()["p-conflict"]
        new = change(base, old.proposition_id, epistemic_status=EpistemicStatus.FACT, uncertainty=Uncertainty())
        return _output(base, suffix="conflict-collapse", propositions=(new if p.proposition_id == new.proposition_id else p for p in base.propositions)), (_declared(old.proposition_id, Dimension.EPISTEMIC_STATUS, old.epistemic_status.value, new.epistemic_status.value, "attack", TransitionKind.EPISTEMIC_PROMOTION), _declared(old.proposition_id, Dimension.UNCERTAINTY, old.uncertainty.to_dict(), new.uncertainty.to_dict(), "attack")), (), ()
    cases.append(_case("conflict-collapse", conflict_collapse))

    def unknown_field_drop(base, registry):
        old = base.proposition_map()["p-unknown"]
        new = change(base, old.proposition_id, metadata={})
        return _output(base, suffix="unknown-field-drop", propositions=(new if p.proposition_id == new.proposition_id else p for p in base.propositions)), (_declared(old.proposition_id, Dimension.PROVENANCE, old.metadata, new.metadata, "attack"),), (), ()
    cases.append(_case("unknown-field-dropped", unknown_field_drop))

    def actor_report_observation(base, registry):
        old = base.proposition_map()["p-verified-observation"]
        new = change(base, old.proposition_id, evidence_refs=("ev-actor-report",))
        return _output(base, suffix="actor-report-observation", propositions=(new if p.proposition_id == new.proposition_id else p for p in base.propositions)), (_declared(old.proposition_id, Dimension.EVIDENCE, list(old.evidence_refs), list(new.evidence_refs), "attack"),), ("ev-actor-report",), ()
    cases.append(_case("actor-report-promoted-to-observation", actor_report_observation))

    def observed_substitution(base, registry):
        old = base.proposition_map()["p-historical"]
        new_temporal = replace(old.temporal, occurred_at=old.temporal.observed_at)
        new = change(base, old.proposition_id, temporal=new_temporal)
        return _output(base, suffix="observed-substitution", propositions=(new if p.proposition_id == new.proposition_id else p for p in base.propositions)), (_declared(old.proposition_id, Dimension.TEMPORAL_STATE, old.temporal.to_dict(), new.temporal.to_dict(), "attack", TransitionKind.TEMPORAL_RECLASSIFICATION),), (), ()
    cases.append(_case("observed-at-substituted-for-occurred-at", observed_substitution))

    def derived_observation(base, registry):
        old = base.proposition_map()["p-ai-inference"]
        new = change(base, old.proposition_id, epistemic_status=EpistemicStatus.OBSERVATION, uncertainty=Uncertainty())
        return _output(base, suffix="derived-observation", propositions=(new if p.proposition_id == new.proposition_id else p for p in base.propositions)), (_declared(old.proposition_id, Dimension.EPISTEMIC_STATUS, old.epistemic_status.value, new.epistemic_status.value, "attack", TransitionKind.EPISTEMIC_PROMOTION), _declared(old.proposition_id, Dimension.UNCERTAINTY, old.uncertainty.to_dict(), new.uncertainty.to_dict(), "attack")), (), ()
    cases.append(_case("derived-result-as-direct-observation", derived_observation))

    def fake_adoption(base, registry):
        old = base.proposition_map()["p-ai-recommendation"]
        new = change(base, old.proposition_id, origin=OriginStatus.HUMAN_ADOPTED_MACHINE_OUTPUT, authorization_refs=("fake-adoption",))
        return _output(base, suffix="fake-adoption", propositions=(new if p.proposition_id == new.proposition_id else p for p in base.propositions)), (_declared(old.proposition_id, Dimension.HUMAN_ORIGIN, old.origin.value, new.origin.value, "attack", TransitionKind.HUMAN_ADOPTION),), (), ()
    cases.append(_case("fabricated-human-adoption", fake_adoption))

    def canonical_forge(base, registry):
        old = base.proposition_map()["p-human-decision"]
        new = change(base, old.proposition_id, canonical_state=CanonicalState.CANONICAL, authorization_refs=("fake-canonical",))
        return _output(base, suffix="canonical-forge", propositions=(new if p.proposition_id == new.proposition_id else p for p in base.propositions)), (_declared(old.proposition_id, Dimension.CANONICALITY, old.canonical_state.value, new.canonical_state.value, "attack", TransitionKind.CANONICALIZATION),), (), ()
    cases.append(_case("canonical-state-without-authorization", canonical_forge))

    def false_lineage(base, registry):
        output = _output(base, suffix="false-lineage", parent_artifact_ids=("forged-parent",))
        return output, (), (), ()
    cases.append(_case("false-lineage-envelope", false_lineage))

    def contract_drop(base, registry):
        output = _output(base, suffix="contract-drop", functional_contract=None)
        # Explicitly rebuild with no contract; _output's None means preserve,
        # so use the constructor directly for this attack.
        output = Artifact(
            artifact_id=f"{base.artifact_id}-contract-drop",
            content=base.content,
            propositions=base.propositions,
            producer=Actor.model("contract-drop"),
            parent_artifact_ids=(base.artifact_id,),
            version=base.version + 1,
            functional_contract=None,
        )
        return output, (_declared(output.artifact_id, Dimension.FUNCTIONAL_CONTRACT, base.functional_contract.to_dict(), None, "attack", TransitionKind.FUNCTIONAL_CHANGE),), (), ()
    cases.append(_case("required-metadata-omitted", contract_drop))

    def semantic_claim(base, registry):
        output = _output(base, suffix="semantic-claim", content="The mixed artifact has been rewritten with a materially different conclusion.")
        return output, (), (), ()
    cases.append(_case("claims-preservation-alters-semantics", semantic_claim))

    def unrooted_addition(base, registry):
        fabricated = Proposition(
            "p-fabricated",
            "A downstream Gem is now the human source of this claim.",
            EpistemicStatus.INFERENCE,
            OriginStatus.MACHINE_ORIGINATED,
            uncertainty=Uncertainty(UncertaintyState.UNCERTAIN, "unrooted model claim"),
            derivation_method="downstream assertion",
            metadata={"kind": "fabricated"},
        )
        output = _output(base, suffix="unrooted-addition", propositions=(*base.propositions, fabricated))
        return output, (_declared(fabricated.proposition_id, Dimension.LINEAGE, "absent", "present", "attack", TransitionKind.DERIVATION),), (), ()
    cases.append(_case("downstream-unrooted-new-artifact", unrooted_addition))

    return tuple(cases)


def legitimate_transformation(base: Artifact, step: int) -> tuple[Artifact, TransformationRecord]:
    output = _output(
        base,
        suffix=f"summary-{step:02d}",
        content=f"Summary step {step}: transformed representation {sha256(base.content.encode('utf-8')).hexdigest()[:16]}.",
        producer=Actor.model(f"transformer-{step:02d}"),
    )
    declaration = _declared(output.artifact_id, Dimension.CONTENT, base.content_digest, output.content_digest, "deterministic summary; proposition envelope retained", TransitionKind.DERIVATION)
    return output, _record(base, output, (declaration,), suffix=f"summary-{step:02d}", transformation_type="SUMMARY")


def run_experiment(steps: int = 10) -> dict:
    base, registry = build_ground_truth()
    verifier = IndependentVerifier()
    treatment_ledger = ConservationLedger()
    treatment_ledger.add_initial(base)
    treatment_current = base
    treatment_rejections: list[VerificationResult] = []
    treatment_accepted: list[VerificationResult] = []
    control_current = base
    control_chain: list[tuple[Artifact, TransformationRecord]] = []
    attack_schedule = {2: "unknown-to-fact", 4: "recommendation-to-decision", 6: "estimated-to-verified", 8: "historical-to-current", 10: "ai-output-to-human-origin"}
    attack_map = {case.name: case for case in hostile_cases()}

    for step in range(1, steps + 1):
        if step in attack_schedule:
            attack_output, attack_record, attack_registry = attack_map[attack_schedule[step]].build(treatment_current)
            attack_result = verifier.verify(treatment_current, attack_output, attack_record, attack_registry)
            treatment_ledger.record_rejection(attack_result)
            treatment_rejections.append(attack_result)
            control_current = attack_output
            control_chain.append((control_current, attack_record))
        else:
            control_output, control_record = legitimate_transformation(control_current, step)
            control_current = control_output
            control_chain.append((control_current, control_record))

        treatment_output, treatment_record = legitimate_transformation(treatment_current, step)
        treatment_result = verifier.verify(treatment_current, treatment_output, treatment_record, registry)
        if treatment_result.accepted:
            treatment_ledger.commit(treatment_output, treatment_record, treatment_result)
            treatment_current = treatment_output
            treatment_accepted.append(treatment_result)
        else:
            treatment_ledger.record_rejection(treatment_result)
            treatment_rejections.append(treatment_result)

    # Audit the control after it has run. The control did not use this verifier
    # to gate transformations; it is used here solely as the identical outcome
    # measurement instrument.
    control_results: list[VerificationResult] = []
    previous = base
    for output, record in control_chain:
        attack_registry = next((case.build(previous)[2] for case in hostile_cases() if record.transformation_id == f"tx-{case.name}"), registry)
        result = verifier.verify(previous, output, record, attack_registry)
        control_results.append(result)
        previous = output

    def rates(results: Iterable[VerificationResult]) -> dict[str, float]:
        results = tuple(results)
        total = max(len(results), 1)
        counts = {dimension: 0 for dimension in ("epistemic", "authority", "provenance", "uncertainty", "temporal", "human_attribution", "canonical", "evidence", "functional")}
        for result in results:
            flags = {dimension: False for dimension in counts}
            for item in result.violations:
                code = item.code
                if item.dimension is Dimension.EPISTEMIC_STATUS or "EPISTEMIC" in code or "DECISION" in code or "SIMULATION" in code:
                    flags["epistemic"] = True
                if item.dimension is Dimension.AUTHORITY or "AUTHORITY" in code or "EXECUTION" in code:
                    flags["authority"] = True
                if item.dimension in {Dimension.PROVENANCE, Dimension.LINEAGE} or "PROVENANCE" in code or "LINEAGE" in code:
                    flags["provenance"] = True
                if item.dimension is Dimension.UNCERTAINTY or "UNCERTAINTY" in code:
                    flags["uncertainty"] = True
                if item.dimension is Dimension.TEMPORAL_STATE or "TEMPORAL" in code:
                    flags["temporal"] = True
                if "HUMAN_ATTRIBUTION" in code or item.dimension is Dimension.HUMAN_ORIGIN:
                    flags["human_attribution"] = True
                if item.dimension is Dimension.CANONICALITY or "CANONICAL" in code:
                    flags["canonical"] = True
                if item.dimension is Dimension.EVIDENCE or "EVIDENCE" in code:
                    flags["evidence"] = True
                if item.dimension is Dimension.FUNCTIONAL_CONTRACT or "FUNCTIONAL" in code:
                    flags["functional"] = True
            for dimension, present in flags.items():
                if present:
                    counts[dimension] += 1
        return {f"{key}_corruption_rate": value / total for key, value in counts.items()}

    reconstruction = ReconstructionEngine().reconstruct(treatment_ledger, treatment_current.artifact_id)
    attack_attempts = sum(1 for step in attack_schedule if step <= steps)
    return {
        "steps_requested": steps,
        "control": {
            "accepted_transformations": len(control_chain),
            "final_artifact_id": control_current.artifact_id,
            "audit_results": [item.to_dict() for item in control_results],
            "metrics": rates(control_results),
        },
        "treatment": {
            "accepted_transformations": len(treatment_accepted),
            "rejected_attempts": len(treatment_rejections),
            "blocked_attack_rate": len(treatment_rejections) / max(attack_attempts, 1),
            "final_artifact_id": treatment_current.artifact_id,
            "rejections": [item.to_dict() for item in treatment_rejections],
            "metrics": rates(treatment_accepted),
            "rejection_metrics": rates(treatment_rejections),
            "reconstruction": reconstruction.to_dict(),
        },
    }
