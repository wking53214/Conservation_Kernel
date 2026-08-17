"""Append-only artifact and verification ledger."""

from __future__ import annotations

from .errors import LedgerError
from .events import TransformationRecord
from .model import Artifact
from .result import VerificationResult


class ConservationLedger:
    """Small in-memory ledger for the first experiment.

    It is append-only at the public API: artifacts and accepted transformation
    records cannot be replaced. Rejected attempts are retained as reports so a
    failed transition is visible rather than disappearing.
    """

    def __init__(self) -> None:
        self._artifacts: dict[str, Artifact] = {}
        self._transformations: dict[str, TransformationRecord] = {}
        self._reports: list[VerificationResult] = []

    def add_initial(self, artifact: Artifact) -> None:
        if artifact.parent_artifact_ids:
            raise LedgerError("an initial artifact cannot already have parents")
        self._add_artifact(artifact)

    def _add_artifact(self, artifact: Artifact) -> None:
        if artifact.artifact_id in self._artifacts:
            raise LedgerError(f"duplicate artifact ID {artifact.artifact_id}")
        self._artifacts[artifact.artifact_id] = artifact

    def commit(self, output: Artifact, record: TransformationRecord, result: VerificationResult) -> None:
        if not result.accepted:
            raise LedgerError("a rejected or unverifiable result cannot be committed")
        if result.output_artifact_id != output.artifact_id:
            raise LedgerError("result and output IDs do not match")
        if output.artifact_id in self._artifacts:
            raise LedgerError(f"duplicate artifact ID {output.artifact_id}")
        for parent in output.parent_artifact_ids:
            if parent not in self._artifacts:
                raise LedgerError(f"parent artifact {parent} is not in the ledger")
        if record.transformation_id in self._transformations:
            raise LedgerError(f"duplicate transformation ID {record.transformation_id}")
        self._add_artifact(output)
        self._transformations[record.transformation_id] = record
        self._reports.append(result)

    def record_rejection(self, result: VerificationResult) -> None:
        self._reports.append(result)

    def artifact(self, artifact_id: str) -> Artifact:
        return self._artifacts[artifact_id]

    def artifacts(self) -> tuple[Artifact, ...]:
        return tuple(self._artifacts.values())

    def transformations(self) -> tuple[TransformationRecord, ...]:
        return tuple(self._transformations.values())

    def reports(self) -> tuple[VerificationResult, ...]:
        return tuple(self._reports)

    def transformation_for_output(self, artifact_id: str) -> TransformationRecord | None:
        return next((item for item in self._transformations.values() if item.output_artifact_id == artifact_id), None)

    def snapshot(self) -> dict:
        return {
            "artifacts": [item.to_dict() for item in self._artifacts.values()],
            "transformations": [item.to_dict() for item in self._transformations.values()],
            "reports": [item.to_dict() for item in self._reports],
        }
