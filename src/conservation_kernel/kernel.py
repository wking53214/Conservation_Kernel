"""Public Conservation Kernel façade."""

from __future__ import annotations

from collections.abc import Sequence

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

    def register_root(self, artifact: Artifact) -> None:
        self.ledger.add_initial(artifact)

    def submit(
        self,
        input_artifacts: Artifact | Sequence[Artifact],
        output: Artifact,
        record: TransformationRecord,
    ) -> VerificationResult:
        result = self.verifier.verify(input_artifacts, output, record, self.registry)
        if result.accepted:
            self.ledger.commit(output, record, result)
        else:
            self.ledger.record_rejection(result)
        return result

    def reconstruct(self, artifact_id: str) -> Reconstruction:
        return self.reconstruction.reconstruct(self.ledger, artifact_id)
