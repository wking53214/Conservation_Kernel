"""Independent structural verification of artifact transformations."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from .enums import (
    ActorKind,
    AuthorityStatus,
    CanonicalState,
    Dimension,
    EpistemicStatus,
    EvidenceKind,
    OriginStatus,
    TransitionKind,
    UncertaintyState,
    VerificationStatus,
)
from .events import TransformationRecord
from .model import Artifact, Proposition, canonical_json
from .registry import EvidenceRegistry
from .result import ObservedChange, VerificationResult, Violation


AUTHORITY_ORDER = {
    AuthorityStatus.NONE: 0,
    AuthorityStatus.PROPOSED: 1,
    AuthorityStatus.HUMAN_AUTHORIZED: 2,
    AuthorityStatus.CANONICAL: 3,
    AuthorityStatus.EXECUTED: 4,
}

STRONG_EPISTEMIC = frozenset({EpistemicStatus.FACT, EpistemicStatus.OBSERVATION})


def _plain(value: Any) -> Any:
    if hasattr(value, "value"):
        return value.value
    if hasattr(value, "to_dict"):
        return value.to_dict()
    if isinstance(value, dict):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (tuple, list, set)):
        return [_plain(item) for item in value]
    return value


def _same(left: Any, right: Any) -> bool:
    return canonical_json(_plain(left)) == canonical_json(_plain(right))


class IndependentVerifier:
    """Compare artifacts without trusting transformer assertions.

    The verifier reads only:

    * immutable input and output artifact fields;
    * the transformation's declarations, used as claims to check; and
    * authorization/evidence records already present in ``EvidenceRegistry``.

    ``claimed_validation_results`` is intentionally never consulted.
    """

    def verify(
        self,
        input_artifacts: Artifact | Sequence[Artifact],
        output: Artifact,
        record: TransformationRecord,
        registry: EvidenceRegistry,
    ) -> VerificationResult:
        inputs = (input_artifacts,) if isinstance(input_artifacts, Artifact) else tuple(input_artifacts)
        violations: list[Violation] = []
        unknown: list[str] = []
        changes: list[ObservedChange] = []

        def violation(code: str, dimension: Dimension | None, subject: str | None, detail: str) -> None:
            violations.append(Violation(code, dimension, subject, detail))

        if not inputs:
            violation("NO_INPUT_ARTIFACT", Dimension.LINEAGE, None, "a transformation must identify at least one input artifact")
        if record.output_artifact_id != output.artifact_id:
            violation("OUTPUT_ID_MISMATCH", Dimension.LINEAGE, output.artifact_id, "record output_artifact_id does not match output artifact")
        if tuple(record.input_artifact_ids) != tuple(item.artifact_id for item in inputs):
            violation("INPUT_ID_MISMATCH", Dimension.LINEAGE, output.artifact_id, "record input IDs do not match verifier inputs")
        if tuple(record.input_hashes) != tuple(item.artifact_digest for item in inputs):
            violation("INPUT_HASH_MISMATCH", Dimension.LINEAGE, output.artifact_id, "record input hashes do not match recomputed artifact digests")
        if record.output_hash != output.artifact_digest:
            violation("OUTPUT_HASH_MISMATCH", Dimension.LINEAGE, output.artifact_id, "record output hash does not match recomputed artifact digest")
        if output.artifact_id in {item.artifact_id for item in inputs}:
            violation("IDENTITY_REUSE", Dimension.LINEAGE, output.artifact_id, "a transformation must create a new artifact identity")
        if set(output.parent_artifact_ids) != {item.artifact_id for item in inputs}:
            violation("FALSE_LINEAGE", Dimension.LINEAGE, output.artifact_id, "output parents must be exactly the declared input artifacts")

        input_props: dict[str, Proposition] = {}
        prop_sources: dict[str, set[str]] = {}
        for artifact in inputs:
            for prop in artifact.propositions:
                if prop.proposition_id in input_props:
                    violation("DUPLICATE_INPUT_PROPOSITION", Dimension.LINEAGE, prop.proposition_id, "the same proposition ID appears in multiple inputs")
                input_props[prop.proposition_id] = prop
                prop_sources.setdefault(prop.proposition_id, set()).add(artifact.artifact_id)
        output_props = output.proposition_map()

        if len(output_props) != len(output.propositions):
            violation("DUPLICATE_OUTPUT_PROPOSITION", Dimension.LINEAGE, output.artifact_id, "output proposition IDs are not unique")

        # Artifact-level payload and functional contract.
        if len(inputs) == 1 and inputs[0].content_digest != output.content_digest:
            changes.append(ObservedChange(output.artifact_id, Dimension.CONTENT, inputs[0].content_digest, output.content_digest))
        if len(inputs) == 1:
            old_contract = inputs[0].functional_contract.to_dict() if inputs[0].functional_contract else None
            new_contract = output.functional_contract.to_dict() if output.functional_contract else None
            if not _same(old_contract, new_contract):
                changes.append(ObservedChange(output.artifact_id, Dimension.FUNCTIONAL_CONTRACT, old_contract, new_contract))

        # Proposition additions, removals, and field-by-field changes.
        for proposition_id, old in input_props.items():
            if proposition_id not in output_props:
                changes.append(ObservedChange(proposition_id, Dimension.LINEAGE, "present", "absent"))
                continue
            new = output_props[proposition_id]
            if old.text != new.text:
                from hashlib import sha256
                changes.append(ObservedChange(
                    proposition_id,
                    Dimension.CONTENT,
                    sha256(old.text.encode("utf-8")).hexdigest(),
                    sha256(new.text.encode("utf-8")).hexdigest(),
                ))
            fields = (
                (Dimension.EPISTEMIC_STATUS, old.epistemic_status.value, new.epistemic_status.value),
                (Dimension.HUMAN_ORIGIN, old.origin.value, new.origin.value),
                (Dimension.AUTHORITY, old.authority.value, new.authority.value),
                (Dimension.UNCERTAINTY, old.uncertainty.to_dict(), new.uncertainty.to_dict()),
                (Dimension.TEMPORAL_STATE, old.temporal.to_dict(), new.temporal.to_dict()),
                (Dimension.EVIDENCE, list(old.evidence_refs), list(new.evidence_refs)),
                (Dimension.CANONICALITY, old.canonical_state.value, new.canonical_state.value),
                (Dimension.LINEAGE, list(old.parent_proposition_ids), list(new.parent_proposition_ids)),
                (Dimension.PROVENANCE, list(old.source_refs), list(new.source_refs)),
                (Dimension.PROVENANCE, old.metadata, new.metadata),
                (Dimension.EPISTEMIC_STATUS, old.derivation_method, new.derivation_method),
            )
            for dimension, before, after in fields:
                if not _same(before, after):
                    changes.append(ObservedChange(proposition_id, dimension, before, after))

        for proposition_id, new in output_props.items():
            if proposition_id not in input_props:
                changes.append(ObservedChange(proposition_id, Dimension.LINEAGE, "absent", "present"))

        # Every observed change must be declared, and declarations must match
        # observed before/after values. Declarations are claims, not proof.
        for change in changes:
            matches = [
                declared for declared in record.declared_changes
                if declared.subject_id == change.subject_id and declared.dimension is change.dimension
            ]
            if not matches:
                violation("UNDECLARED_CHANGE", change.dimension, change.subject_id, "output changed a protected dimension without declaring it")
            elif not any(_same(item.from_value, change.before) and _same(item.to_value, change.after) for item in matches):
                violation("DECLARATION_MISMATCH", change.dimension, change.subject_id, "declared before/after values do not match the independently observed change")

        for declared in record.declared_changes:
            if not any(item.subject_id == declared.subject_id and item.dimension is declared.dimension for item in changes):
                violation("DECLARED_CHANGE_NOT_OBSERVED", declared.dimension, declared.subject_id, "transformer declared a change the verifier could not observe")

        # Cross-artifact functional invariants.
        if len(inputs) == 1:
            self._check_functional(inputs[0], output, record, registry, violation, unknown)

        # Existing proposition transitions.
        for proposition_id, old in input_props.items():
            new = output_props.get(proposition_id)
            if new is None:
                self._check_removed(old, output, record, registry, violation)
                continue
            refs = tuple(dict.fromkeys((*new.evidence_refs, *record.evidence_refs)))
            auth_refs = tuple(dict.fromkeys((*new.authorization_refs, *record.authorization_refs)))
            subject_ids = {proposition_id, *new.parent_proposition_ids}
            self._check_evidence_refs(new, refs, registry, violation)
            self._check_origin(old, new, auth_refs, record, registry, violation)
            self._check_epistemic(old, new, refs, auth_refs, subject_ids, record, registry, violation)
            self._check_authority(old, new, refs, auth_refs, subject_ids, record, registry, violation)
            self._check_uncertainty(old, new, refs, auth_refs, subject_ids, record, registry, violation)
            self._check_temporal(old, new, auth_refs, record, registry, violation)
            self._check_evidence_change(old, new, refs, auth_refs, record, registry, violation, unknown)
            self._check_canonical(old, new, refs, auth_refs, subject_ids, record, registry, violation)
            self._check_provenance(old, new, refs, registry, violation, unknown)
            self._check_lineage(old, new, input_props, violation)

        # New propositions must have a derivation path; a model cannot invent
        # a human-originated fact by choosing a convenient label.
        for proposition_id, new in output_props.items():
            if proposition_id in input_props:
                continue
            self._check_new_proposition(new, output, input_props, record, registry, violation, unknown)

        # Content transformation is deliberately not called semantic proof.
        if any(change.dimension is Dimension.CONTENT for change in changes):
            unknown.append("semantic_content_equivalence")

        if violations:
            status = VerificationStatus.REJECT
        elif unknown and not changes:
            status = VerificationStatus.UNVERIFIABLE
        elif unknown:
            status = VerificationStatus.PASS_WITH_DECLARED_TRANSFORMATION
        elif changes:
            status = VerificationStatus.PASS_WITH_DECLARED_TRANSFORMATION
        else:
            status = VerificationStatus.PASS

        return VerificationResult(
            transformation_id=record.transformation_id,
            input_artifact_ids=tuple(item.artifact_id for item in inputs),
            output_artifact_id=output.artifact_id,
            status=status,
            observed_changes=tuple(changes),
            violations=tuple(violations),
            unverifiable_properties=tuple(dict.fromkeys(unknown)),
            checked_dimensions=tuple(Dimension),
        )

    def _check_evidence_refs(self, proposition: Proposition, refs: tuple[str, ...], registry: EvidenceRegistry, violation) -> None:
        missing = registry.missing_refs(refs)
        if missing:
            violation("MISSING_EVIDENCE", Dimension.EVIDENCE, proposition.proposition_id, f"evidence references are not present in the external registry: {missing}")
        inactive = registry.inactive_refs(refs)
        if inactive and (proposition.epistemic_status in STRONG_EPISTEMIC or proposition.authority is not AuthorityStatus.NONE or proposition.canonical_state is CanonicalState.CANONICAL):
            violation("INACTIVE_EVIDENCE", Dimension.EVIDENCE, proposition.proposition_id, f"strong/canonical proposition retains inactive evidence: {inactive}")

    def _check_removed(self, old: Proposition, output: Artifact, record: TransformationRecord, registry: EvidenceRegistry, violation) -> None:
        refs = tuple(dict.fromkeys((*record.authorization_refs, *old.authorization_refs)))
        authorized = registry.has_authorization(
            refs,
            subject_id=old.proposition_id,
            transition_kind=TransitionKind.EVIDENCE_REDACTION,
            from_value="present",
            to_value="absent",
        )
        if not authorized:
            violation("PROPOSITION_DROPPED", Dimension.LINEAGE, old.proposition_id, "an input proposition disappeared without a verified redaction authorization")

    def _check_origin(self, old: Proposition, new: Proposition, auth_refs: tuple[str, ...], record: TransformationRecord, registry: EvidenceRegistry, violation) -> None:
        if old.origin is new.origin:
            return
        if new.origin is OriginStatus.HUMAN_ORIGINATED and old.origin in {OriginStatus.MACHINE_ORIGINATED, OriginStatus.HUMAN_ADOPTED_MACHINE_OUTPUT}:
            violation("FALSE_HUMAN_ATTRIBUTION", Dimension.HUMAN_ORIGIN, new.proposition_id, "machine-originated content cannot become human-originated")
            return
        if new.origin is OriginStatus.HUMAN_ADOPTED_MACHINE_OUTPUT and old.origin is OriginStatus.MACHINE_ORIGINATED:
            if not registry.has_authorization(
                auth_refs,
                subject_id=new.proposition_id,
                transition_kind=TransitionKind.HUMAN_ADOPTION,
                from_value=old.origin.value,
                to_value=new.origin.value,
            ):
                violation("MISSING_HUMAN_ADOPTION", Dimension.HUMAN_ORIGIN, new.proposition_id, "human adoption requires an external human authorization event")
            return
        violation("ORIGIN_MUTATION", Dimension.HUMAN_ORIGIN, new.proposition_id, "origin changes are not silently inferred")

    def _check_epistemic(self, old: Proposition, new: Proposition, refs: tuple[str, ...], auth_refs: tuple[str, ...], subject_ids: set[str], record: TransformationRecord, registry: EvidenceRegistry, violation) -> None:
        if old.epistemic_status is new.epistemic_status:
            return
        target = new.epistemic_status
        if old.epistemic_status is EpistemicStatus.SIMULATED and target in {EpistemicStatus.FACT, EpistemicStatus.OBSERVATION}:
            violation("SIMULATION_TO_HISTORY", Dimension.EPISTEMIC_STATUS, new.proposition_id, "a simulation cannot be relabelled as a historical fact or observation")
            return
        if old.epistemic_status is EpistemicStatus.UNKNOWN and target is EpistemicStatus.INFERENCE:
            if not new.derivation_method:
                violation("INFERENCE_WITHOUT_METHOD", Dimension.EPISTEMIC_STATUS, new.proposition_id, "UNKNOWN to INFERENCE requires a named derivation method")
            if not registry.has_active_evidence(
                refs,
                subject_ids=subject_ids,
                kinds={EvidenceKind.SOURCE_OBSERVATION, EvidenceKind.CITATION, EvidenceKind.INDEPENDENT_VERIFICATION},
            ):
                violation("INFERENCE_WITHOUT_SUPPORT", Dimension.EVIDENCE, new.proposition_id, "UNKNOWN to INFERENCE requires active non-consensus support")
            return
        if target in STRONG_EPISTEMIC:
            if not registry.has_active_evidence(
                refs,
                subject_ids=subject_ids,
                kinds={EvidenceKind.INDEPENDENT_VERIFICATION},
                independent=True,
            ):
                violation("NO_INDEPENDENT_VERIFICATION", Dimension.EPISTEMIC_STATUS, new.proposition_id, "promotion to fact/observation requires independently supplied verification")
            if old.epistemic_status is not EpistemicStatus.OBSERVATION and not registry.has_authorization(
                auth_refs,
                subject_id=new.proposition_id,
                transition_kind=TransitionKind.EPISTEMIC_PROMOTION,
                from_value=old.epistemic_status.value,
                to_value=target.value,
            ):
                violation("MISSING_EPISTEMIC_AUTHORIZATION", Dimension.EPISTEMIC_STATUS, new.proposition_id, "promotion into strong epistemic status requires a matching human authorization")
            return
        if old.epistemic_status is EpistemicStatus.RECOMMENDATION and target is EpistemicStatus.DECISION:
            if not registry.has_authorization(
                auth_refs,
                subject_id=new.proposition_id,
                transition_kind=TransitionKind.AUTHORITY_ESCALATION,
                from_value=old.epistemic_status.value,
                to_value=target.value,
            ):
                violation("RECOMMENDATION_TO_DECISION_UNAUTHORIZED", Dimension.EPISTEMIC_STATUS, new.proposition_id, "a recommendation cannot become a decision without an external human authorization")
            return
        if target is EpistemicStatus.DECISION and not registry.has_authorization(
            auth_refs,
            subject_id=new.proposition_id,
            transition_kind=TransitionKind.AUTHORITY_ESCALATION,
            from_value=old.epistemic_status.value,
            to_value=target.value,
        ):
            violation("DECISION_WITHOUT_AUTHORIZATION", Dimension.EPISTEMIC_STATUS, new.proposition_id, "decision status requires an external authorization event")

    def _check_authority(self, old: Proposition, new: Proposition, refs: tuple[str, ...], auth_refs: tuple[str, ...], subject_ids: set[str], record: TransformationRecord, registry: EvidenceRegistry, violation) -> None:
        if old.authority is new.authority:
            return
        increasing = AUTHORITY_ORDER[new.authority] > AUTHORITY_ORDER[old.authority]
        if increasing and not registry.has_authorization(
            auth_refs,
            subject_id=new.proposition_id,
            transition_kind=TransitionKind.AUTHORITY_ESCALATION,
            from_value=old.authority.value,
            to_value=new.authority.value,
        ):
            violation("UNAUTHORIZED_AUTHORITY_ESCALATION", Dimension.AUTHORITY, new.proposition_id, "authority increased without a matching human authorization event")
        if new.authority is AuthorityStatus.CANONICAL and not registry.has_active_evidence(
            refs,
            subject_ids=subject_ids,
            kinds={EvidenceKind.SOURCE_OBSERVATION, EvidenceKind.INDEPENDENT_VERIFICATION, EvidenceKind.CITATION},
        ):
            violation("CANONICAL_WITHOUT_SUPPORT", Dimension.AUTHORITY, new.proposition_id, "canonical authority requires active supporting evidence")
        if new.authority is AuthorityStatus.EXECUTED and not registry.has_active_evidence(
            refs,
            subject_ids=subject_ids,
            kinds={EvidenceKind.EXECUTION_RECORD},
        ):
            violation("EXECUTION_NOT_EVIDENCE", Dimension.AUTHORITY, new.proposition_id, "execution authority requires a separate execution record; execution alone does not prove truth")
        if not increasing and old.authority in {AuthorityStatus.CANONICAL, AuthorityStatus.EXECUTED} and not registry.has_authorization(
            auth_refs,
            subject_id=new.proposition_id,
            transition_kind=TransitionKind.AUTHORITY_ESCALATION,
            from_value=old.authority.value,
            to_value=new.authority.value,
        ):
            violation("UNAUTHORIZED_AUTHORITY_REVOCATION", Dimension.AUTHORITY, new.proposition_id, "canonical/executed authority cannot be silently rewritten")

    def _check_uncertainty(self, old: Proposition, new: Proposition, refs: tuple[str, ...], auth_refs: tuple[str, ...], subject_ids: set[str], record: TransformationRecord, registry: EvidenceRegistry, violation) -> None:
        if old.uncertainty == new.uncertainty:
            return
        if old.uncertainty.state is not UncertaintyState.NONE and new.uncertainty.state is UncertaintyState.NONE:
            independently_verified = registry.has_active_evidence(
                refs,
                subject_ids=subject_ids,
                kinds={EvidenceKind.INDEPENDENT_VERIFICATION},
                independent=True,
            )
            if not independently_verified:
                violation("UNCERTAINTY_COLLAPSE", Dimension.UNCERTAINTY, new.proposition_id, "uncertainty cannot disappear without independent verification")

    def _check_temporal(self, old: Proposition, new: Proposition, auth_refs: tuple[str, ...], record: TransformationRecord, registry: EvidenceRegistry, violation) -> None:
        if old.temporal == new.temporal:
            return
        if not registry.has_authorization(
            auth_refs,
            subject_id=new.proposition_id,
            transition_kind=TransitionKind.TEMPORAL_RECLASSIFICATION,
            from_value=old.temporal.to_dict(),
            to_value=new.temporal.to_dict(),
        ):
            violation("UNAUTHORIZED_TEMPORAL_CHANGE", Dimension.TEMPORAL_STATE, new.proposition_id, "occurred_at, observed_at, or temporal scope changed without an explicit temporal transition")

    def _check_evidence_change(self, old: Proposition, new: Proposition, refs: tuple[str, ...], auth_refs: tuple[str, ...], record: TransformationRecord, registry: EvidenceRegistry, violation, unknown: list[str]) -> None:
        old_refs = set(old.evidence_refs)
        new_refs = set(new.evidence_refs)
        removed = old_refs - new_refs
        if removed:
            authorized = registry.has_authorization(
                auth_refs,
                subject_id=new.proposition_id,
                transition_kind=TransitionKind.EVIDENCE_REDACTION,
                from_value=sorted(old_refs),
                to_value=sorted(new_refs),
            )
            if not authorized:
                violation("EVIDENCE_LOSS", Dimension.EVIDENCE, new.proposition_id, f"evidence refs disappeared without explicit redaction authorization: {sorted(removed)}")
            else:
                unknown.append("continued_support_after_authorized_evidence_redaction")
        if new_refs - old_refs:
            missing = registry.missing_refs(tuple(new_refs - old_refs))
            if missing:
                violation("ADDED_EVIDENCE_NOT_REGISTERED", Dimension.EVIDENCE, new.proposition_id, f"new evidence refs are not in the external registry: {missing}")
        if new.epistemic_status in STRONG_EPISTEMIC:
            active_records = [registry.evidence(ref) for ref in new.evidence_refs]
            active_records = [item for item in active_records if item is not None and item.active]
            if active_records and all(item.kind in {EvidenceKind.ACTOR_REPORT, EvidenceKind.MODEL_CONSENSUS} for item in active_records):
                violation("ACTOR_REPORT_NOT_OBSERVATION", Dimension.EVIDENCE, new.proposition_id, "an actor's self-report or model consensus cannot support an observation")

    def _check_provenance(self, old: Proposition, new: Proposition, refs: tuple[str, ...], registry: EvidenceRegistry, violation, unknown: list[str]) -> None:
        if old.source_refs == new.source_refs and old.metadata == new.metadata:
            return
        if set(new.source_refs) < set(old.source_refs):
            violation("PROVENANCE_STRIPPED", Dimension.PROVENANCE, new.proposition_id, "source provenance was removed from the transformed proposition")
            return
        if set(old.source_refs) != set(new.source_refs):
            # A source locator is not itself proof of source identity. The
            # first kernel has no external source-identity protocol, so even a
            # plausible replacement is rejected rather than accepted on the
            # strength of a citation-shaped field.
            violation("SOURCE_SUBSTITUTION_UNVERIFIED", Dimension.PROVENANCE, new.proposition_id, "source references changed but this kernel has no independent source-identity protocol")
        if old.metadata != new.metadata:
            # Metadata is not allowed to smuggle a status assertion around the
            # typed envelope. A changed metadata map is observable, but its
            # semantics are not independently known.
            if set(old.metadata) - set(new.metadata):
                violation("METADATA_LOSS", Dimension.PROVENANCE, new.proposition_id, "metadata fields were dropped from the transformed proposition")
            else:
                unknown.append("metadata_semantics")

    def _check_canonical(self, old: Proposition, new: Proposition, refs: tuple[str, ...], auth_refs: tuple[str, ...], subject_ids: set[str], record: TransformationRecord, registry: EvidenceRegistry, violation) -> None:
        if old.canonical_state is new.canonical_state:
            return
        if not registry.has_authorization(
            auth_refs,
            subject_id=new.proposition_id,
            transition_kind=TransitionKind.CANONICALIZATION,
            from_value=old.canonical_state.value,
            to_value=new.canonical_state.value,
        ):
            violation("UNAUTHORIZED_CANONICAL_CHANGE", Dimension.CANONICALITY, new.proposition_id, "canonical state changes require an external human event")
        if new.canonical_state is CanonicalState.CANONICAL and not registry.has_active_evidence(
            refs,
            subject_ids=subject_ids,
            kinds={EvidenceKind.SOURCE_OBSERVATION, EvidenceKind.INDEPENDENT_VERIFICATION, EvidenceKind.CITATION},
        ):
            violation("CANONICAL_WITHOUT_EVIDENCE", Dimension.CANONICALITY, new.proposition_id, "canonicalization requires active support")

    def _check_lineage(self, old: Proposition, new: Proposition, input_props: dict[str, Proposition], violation) -> None:
        unknown_parents = [parent for parent in new.parent_proposition_ids if parent not in input_props and parent != new.proposition_id]
        if unknown_parents:
            violation("FALSE_PROPOSITION_LINEAGE", Dimension.LINEAGE, new.proposition_id, f"proposition cites parents absent from the input: {unknown_parents}")

    def _check_new_proposition(self, new: Proposition, output: Artifact, input_props: dict[str, Proposition], record: TransformationRecord, registry: EvidenceRegistry, violation, unknown: list[str]) -> None:
        if not new.parent_proposition_ids:
            violation("UNROOTED_NEW_PROPOSITION", Dimension.LINEAGE, new.proposition_id, "a transformed artifact may not add a proposition without a parent or explicit external source")
        if any(parent not in input_props for parent in new.parent_proposition_ids):
            violation("FALSE_NEW_PROPOSITION_LINEAGE", Dimension.LINEAGE, new.proposition_id, "new proposition references a parent not present in the input")
        if new.origin is OriginStatus.HUMAN_ORIGINATED and output.producer.kind is not ActorKind.HUMAN:
            violation("FALSE_HUMAN_ATTRIBUTION", Dimension.HUMAN_ORIGIN, new.proposition_id, "a non-human transformer cannot create a human-originated proposition")
        refs = tuple(dict.fromkeys((*new.evidence_refs, *record.evidence_refs)))
        subject_ids = {new.proposition_id, *new.parent_proposition_ids}
        self._check_evidence_refs(new, refs, registry, violation)
        if new.epistemic_status in STRONG_EPISTEMIC:
            if not registry.has_active_evidence(refs, subject_ids=subject_ids, kinds={EvidenceKind.INDEPENDENT_VERIFICATION}, independent=True):
                violation("NEW_STRONG_CLAIM_UNVERIFIED", Dimension.EPISTEMIC_STATUS, new.proposition_id, "new fact/observation requires independent verification")
        if new.authority in {AuthorityStatus.HUMAN_AUTHORIZED, AuthorityStatus.CANONICAL, AuthorityStatus.EXECUTED}:
            auth_refs = tuple(dict.fromkeys((*new.authorization_refs, *record.authorization_refs)))
            if not any(registry.authorization(ref) for ref in auth_refs):
                violation("NEW_AUTHORITY_UNVERIFIED", Dimension.AUTHORITY, new.proposition_id, "new authoritative proposition has no registry-backed authorization")
        if new.canonical_state is CanonicalState.CANONICAL:
            unknown.append("semantic_validity_of_new_canonical_claim")

    def _check_functional(self, old: Artifact, new: Artifact, record: TransformationRecord, registry: EvidenceRegistry, violation, unknown: list[str]) -> None:
        old_contract = old.functional_contract
        new_contract = new.functional_contract
        if old_contract is None and new_contract is None:
            return
        if old_contract is not None and new_contract is None:
            violation("FUNCTIONAL_CONTRACT_DROPPED", Dimension.FUNCTIONAL_CONTRACT, new.artifact_id, "output omitted an input functional contract")
            return
        if old_contract is None or new_contract is None:
            unknown.append("functional_contract_introduced_without_baseline")
            return
        if old_contract.contract_id != new_contract.contract_id or old_contract.required_properties != new_contract.required_properties:
            refs = tuple(dict.fromkeys((*record.evidence_refs,)))
            if not registry.has_active_evidence(refs, subject_ids={new.artifact_id, old.artifact_id, "*"}, kinds={EvidenceKind.FUNCTIONAL_VALIDATION}):
                violation("FUNCTIONAL_CONTRACT_CHANGED", Dimension.FUNCTIONAL_CONTRACT, new.artifact_id, "required functional properties changed without independent functional validation")
