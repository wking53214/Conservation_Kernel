"""Public Conservation Kernel façade."""

from __future__ import annotations

from collections.abc import Sequence

from .enums import AuthorityStatus, CanonicalState, EpistemicStatus, TransitionKind
from .errors import LedgerError, RootAdmissionError
from .events import TransformationRecord
from .ledger import ConservationLedger
from .model import Artifact
from .reconstruction import Reconstruction, ReconstructionEngine
from .registry import EvidenceRegistry
from .result import VerificationResult
from .verifier import IndependentVerifier


class ConservationKernel:
    """Compose the verifier, external registry, and append-only ledger.

    This class is intentionally thin. The verifier remains independently
    callable so an experiment can audit a control pipeline without using the
    kernel as its gate.
    """

    version = "0.1.0"

    def __init__(
        self,
        *,
        registry: EvidenceRegistry | None = None,
        verifier: IndependentVerifier | None = None,
        ledger: ConservationLedger | None = None,
    ) -> None:
        self.registry = registry or EvidenceRegistry()
        self.verifier = verifier or IndependentVerifier()
        self.ledger = ledger or ConservationLedger()
        self.reconstruction = ReconstructionEngine()

    STRONG_EPISTEMIC = frozenset({EpistemicStatus.FACT, EpistemicStatus.OBSERVATION})
    AUTHORITATIVE = frozenset({AuthorityStatus.HUMAN_AUTHORIZED, AuthorityStatus.CANONICAL, AuthorityStatus.EXECUTED})
    CANONICAL_STATES = frozenset({CanonicalState.ACCEPTED, CanonicalState.CANONICAL, CanonicalState.SUPERSEDED,
                                  CanonicalState.REVOKED, CanonicalState.DELETED})

    def admit_root(self, artifact: Artifact) -> tuple[str, ...]:
        """Reasons this artifact may not be registered as a root; empty if it may.

        The constitution constrains transitions, so a root is asserted. But an
        assertion that cites a registry must be backed by it: a reference that
        does not exist, an authoritative or canonical claim with no
        authorization for that proposition, or a fact with no source, is a
        forged origin story, and everything derived from it would inherit
        verified ancestry it never had.
        """
        reasons: list[str] = []
        for prop in artifact.propositions:
            missing = self.registry.missing_refs(prop.evidence_refs)
            if missing:
                reasons.append(f"{prop.proposition_id}: evidence_refs not in registry: {list(missing)}")
            dangling = tuple(ref for ref in prop.authorization_refs if self.registry.authorization(ref) is None)
            if dangling:
                reasons.append(f"{prop.proposition_id}: authorization_refs not in registry: {list(dangling)}")
            if prop.authority in self.AUTHORITATIVE and not self._authorized(
                    prop.authorization_refs, prop.proposition_id, TransitionKind.AUTHORITY_ESCALATION, prop.authority.value):
                reasons.append(f"{prop.proposition_id}: authority {prop.authority.value} has no authorization for this proposition")
            if prop.canonical_state in self.CANONICAL_STATES and not self._authorized(
                    prop.authorization_refs, prop.proposition_id, TransitionKind.CANONICALIZATION, prop.canonical_state.value):
                reasons.append(f"{prop.proposition_id}: canonical state {prop.canonical_state.value} has no canonicalization for this proposition")
            if prop.epistemic_status in self.STRONG_EPISTEMIC and not (prop.source_refs or prop.evidence_refs):
                reasons.append(f"{prop.proposition_id}: a root {prop.epistemic_status.value} must cite a source or evidence")
        return tuple(reasons)

    def _authorized(self, refs, subject_id: str, kind: TransitionKind, to_value: str) -> bool:
        for ref in refs:
            event = self.registry.authorization(ref)
            if event is None:
                continue
            if event.subject_id == subject_id and event.transition_kind is kind and event.to_value == to_value:
                return True
        return False

    def register_root(self, artifact: Artifact) -> None:
        reasons = self.admit_root(artifact)
        if reasons:
            raise RootAdmissionError("root refused: " + "; ".join(reasons))
        self.ledger.add_initial(artifact)

    def submit(
        self,
        input_artifacts: Artifact | Sequence[Artifact],
        output: Artifact,
        record: TransformationRecord,
    ) -> VerificationResult:
        result = self.verifier.verify(input_artifacts, output, record, self.registry)
        if result.accepted:
            try:
                self.ledger.commit(output, record, result)
            except LedgerError:
                # The verification happened and was accepted; the ledger could
                # not take it (unregistered parent, duplicate id). Before this
                # the accepted result vanished with the exception (measured
                # 2026-09-08), so a verification that occurred left no trace.
                # Keep the report, then let the caller see the ledger's refusal.
                self.ledger.record_rejection(result)
                raise
        else:
            self.ledger.record_rejection(result)
        return result

    def reconstruct(self, artifact_id: str) -> Reconstruction:
        return self.reconstruction.reconstruct(self.ledger, artifact_id)
