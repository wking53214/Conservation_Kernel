"""Public Conservation Kernel façade."""

from __future__ import annotations

from collections.abc import Sequence

from .enums import AuthorityStatus, CanonicalState, EpistemicStatus, TransitionKind
from .errors import LedgerError, RootAdmissionError, SnapshotAuthenticityError, SnapshotIntegrityError
from .events import TransformationRecord
from .ledger import ConservationLedger
from .model import Artifact, _digest, canonical_json
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

    version = "0.2.0"

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

    # -- persistence -------------------------------------------------------------

    SNAPSHOT_VERSION = "1.0.0"

    def snapshot(self) -> dict:
        """Everything needed to continue after a restart, plus a digest of it."""
        body = {
            "snapshot_version": self.SNAPSHOT_VERSION,
            "kernel_version": self.version,
            "ledger": self.ledger.snapshot(),
            "registry": self.registry.snapshot(),
        }
        body["snapshot_digest"] = _digest(canonical_json(body))
        return body

    @classmethod
    def from_snapshot(cls, snapshot: dict, *, trusted_humans=None, reverify: bool = True, signer=None) -> "ConservationKernel":
        """A kernel continuing from `snapshot()`.

        The digest is checked first (corruption). Then, with `reverify`, every
        root is re-admitted and every transformation is re-verified against
        the restored registry, so a lineage that was written into the file
        by hand fails the same way it would have failed live. What this does
        not do is authenticate the file: a snapshot that re-verifies is one
        the constitution would have accepted, not one this kernel is known to
        have produced. That needs a signature the deployer holds.
        """
        body = dict(snapshot)
        signature = body.pop("signature", None)
        recorded = body.pop("snapshot_digest", None)
        if recorded is not None and _digest(canonical_json(body)) != recorded:
            raise SnapshotIntegrityError("snapshot digest does not recompute; the file was altered")
        if signer is not None:
            # 0.3.0: a loader that holds a key expects the file to be signed
            # by it. An unsigned file, or one signed by another key, is not
            # this deployment's kernel, however well it re-verifies.
            from .signing import check_signature
            problem = check_signature(signer, recorded or "", signature)
            if problem:
                raise SnapshotAuthenticityError(f"snapshot not authenticated: {problem}")
        registry = EvidenceRegistry.restore(body.get("registry", {}), trusted_humans=trusted_humans)
        ledger = ConservationLedger.restore(body.get("ledger", {}))
        kernel = cls(registry=registry, ledger=ledger)
        if reverify:
            kernel.reverify()
        return kernel

    def reverify(self) -> None:
        """Re-admit every root and re-verify every transformation now in the ledger."""
        for artifact in self.ledger.artifacts():
            if not artifact.parent_artifact_ids:
                reasons = self.admit_root(artifact)
                if reasons:
                    raise SnapshotIntegrityError(f"root {artifact.artifact_id} would not be admitted: " + "; ".join(reasons))
        for record in self.ledger.transformations():
            try:
                inputs = [self.ledger.artifact(i) for i in record.input_artifact_ids]
                output = self.ledger.artifact(record.output_artifact_id)
            except KeyError as e:
                raise SnapshotIntegrityError(f"transformation {record.transformation_id} references an artifact not in the ledger: {e}") from e
            result = self.verifier.verify(inputs, output, record, self.registry)
            if not result.accepted:
                raise SnapshotIntegrityError(
                    f"transformation {record.transformation_id} does not re-verify: "
                    + "; ".join(f"{v.code}" for v in result.violations)
                )

    def save(self, path, *, signer=None) -> None:
        """Write the snapshot; with a signer, sign its digest with the deployer's key."""
        from pathlib import Path
        body = self.snapshot()
        if signer is not None:
            from .signing import signature_block
            body["signature"] = signature_block(signer, body["snapshot_digest"])
        Path(path).write_text(canonical_json(body), encoding="utf-8")

    @classmethod
    def load(cls, path, **kwargs) -> "ConservationKernel":
        import json
        from pathlib import Path
        return cls.from_snapshot(json.loads(Path(path).read_text(encoding="utf-8")), **kwargs)
