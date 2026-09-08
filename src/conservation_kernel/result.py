"""Machine-readable verification results."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .enums import Dimension, VerificationStatus


@dataclass(frozen=True)
class ObservedChange:
    subject_id: str
    dimension: Dimension
    before: Any
    after: Any

    def to_dict(self) -> dict[str, Any]:
        return {
            "subject_id": self.subject_id,
            "dimension": self.dimension.value,
            "before": self.before,
            "after": self.after,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ObservedChange":
        return cls(subject_id=data["subject_id"], dimension=Dimension(data["dimension"]),
                   before=data["before"], after=data["after"])


@dataclass(frozen=True)
class Violation:
    code: str
    dimension: Dimension | None
    subject_id: str | None
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "dimension": self.dimension.value if self.dimension else None,
            "subject_id": self.subject_id,
            "detail": self.detail,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Violation":
        return cls(code=data["code"], dimension=Dimension(data["dimension"]) if data.get("dimension") else None,
                   subject_id=data.get("subject_id"), detail=data["detail"])


@dataclass(frozen=True)
class VerificationResult:
    transformation_id: str
    input_artifact_ids: tuple[str, ...]
    output_artifact_id: str
    status: VerificationStatus
    observed_changes: tuple[ObservedChange, ...] = field(default_factory=tuple)
    violations: tuple[Violation, ...] = field(default_factory=tuple)
    unverifiable_properties: tuple[str, ...] = field(default_factory=tuple)
    checked_dimensions: tuple[Dimension, ...] = field(default_factory=tuple)

    @property
    def accepted(self) -> bool:
        return self.status in {VerificationStatus.PASS, VerificationStatus.PASS_WITH_DECLARED_TRANSFORMATION}

    def to_dict(self) -> dict[str, Any]:
        return {
            "transformation_id": self.transformation_id,
            "input_artifact_ids": list(self.input_artifact_ids),
            "output_artifact_id": self.output_artifact_id,
            "status": self.status.value,
            "observed_changes": [item.to_dict() for item in self.observed_changes],
            "violations": [item.to_dict() for item in self.violations],
            "unverifiable_properties": list(self.unverifiable_properties),
            "checked_dimensions": [item.value for item in self.checked_dimensions],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "VerificationResult":
        return cls(
            transformation_id=data["transformation_id"],
            input_artifact_ids=tuple(data["input_artifact_ids"]),
            output_artifact_id=data["output_artifact_id"],
            status=VerificationStatus(data["status"]),
            observed_changes=tuple(ObservedChange.from_dict(item) for item in data.get("observed_changes", [])),
            violations=tuple(Violation.from_dict(item) for item in data.get("violations", [])),
            unverifiable_properties=tuple(data.get("unverifiable_properties", [])),
            checked_dimensions=tuple(Dimension(item) for item in data.get("checked_dimensions", [])),
        )
