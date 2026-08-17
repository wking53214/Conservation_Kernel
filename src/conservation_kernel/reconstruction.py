"""History reconstruction from the ledger, not model memory."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .ledger import ConservationLedger


@dataclass(frozen=True)
class Reconstruction:
    requested_artifact_id: str
    root_artifact_ids: tuple[str, ...]
    artifact_ids_in_order: tuple[str, ...]
    transformation_ids_in_order: tuple[str, ...]
    proposition_histories: dict[str, tuple[dict[str, Any], ...]]
    serialized_bytes: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "requested_artifact_id": self.requested_artifact_id,
            "root_artifact_ids": list(self.root_artifact_ids),
            "artifact_ids_in_order": list(self.artifact_ids_in_order),
            "transformation_ids_in_order": list(self.transformation_ids_in_order),
            "proposition_histories": {
                key: list(value) for key, value in self.proposition_histories.items()
            },
            "serialized_bytes": self.serialized_bytes,
        }


class ReconstructionEngine:
    def reconstruct(self, ledger: ConservationLedger, artifact_id: str) -> Reconstruction:
        ledger.artifact(artifact_id)
        artifacts: list = []
        transformations: list = []
        seen: set[str] = set()

        def walk(current_id: str) -> None:
            if current_id in seen:
                return
            seen.add(current_id)
            current = ledger.artifact(current_id)
            for parent in current.parent_artifact_ids:
                walk(parent)
            artifacts.append(current)
            record = ledger.transformation_for_output(current_id)
            if record is not None:
                transformations.append(record)

        walk(artifact_id)
        roots = tuple(item.artifact_id for item in artifacts if not item.parent_artifact_ids)
        histories: dict[str, list[dict[str, Any]]] = {}
        serialized_bytes = 0
        for artifact in artifacts:
            serialized_bytes += len(artifact.to_json().encode("utf-8"))
            for proposition in artifact.propositions:
                histories.setdefault(proposition.proposition_id, []).append({
                    "artifact_id": artifact.artifact_id,
                    "text": proposition.text,
                    "epistemic_status": proposition.epistemic_status.value,
                    "origin": proposition.origin.value,
                    "authority": proposition.authority.value,
                    "uncertainty": proposition.uncertainty.to_dict(),
                    "temporal": proposition.temporal.to_dict(),
                    "evidence_refs": list(proposition.evidence_refs),
                    "canonical_state": proposition.canonical_state.value,
                })
        return Reconstruction(
            requested_artifact_id=artifact_id,
            root_artifact_ids=roots,
            artifact_ids_in_order=tuple(item.artifact_id for item in artifacts),
            transformation_ids_in_order=tuple(item.transformation_id for item in transformations),
            proposition_histories={key: tuple(value) for key, value in histories.items()},
            serialized_bytes=serialized_bytes,
        )
