"""Append-only records supplied alongside transformations.

The transformer may declare a change, but declarations are not evidence.  The
verifier recomputes observed changes from input and output artifacts and only
consults authorization/evidence records that exist in the external registry.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Mapping

from .enums import ActorKind, Dimension, EvidenceKind, TransitionKind
from .errors import InvalidEvent
from .model import Actor, canonical_json, utc_now


def _enum(value: Any, enum_type):
    if isinstance(value, enum_type):
        return value
    try:
        return enum_type(value)
    except (TypeError, ValueError) as exc:
        raise InvalidEvent(f"invalid {enum_type.__name__}: {value!r}") from exc


def _tuple(values: Any, name: str) -> tuple[str, ...]:
    if values is None:
        return ()
    if isinstance(values, (str, bytes)):
        raise InvalidEvent(f"{name} must be a sequence")
    result = tuple(values)
    if any(not isinstance(item, str) or not item.strip() for item in result):
        raise InvalidEvent(f"{name} may contain only non-empty strings")
    if len(set(result)) != len(result):
        raise InvalidEvent(f"{name} may not contain duplicates")
    return result


def _jsonable(value: Any) -> Any:
    if hasattr(value, "value"):
        return value.value
    if hasattr(value, "to_dict"):
        return value.to_dict()
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list, set)):
        return [_jsonable(item) for item in value]
    return value


@dataclass(frozen=True)
class DeclaredChange:
    subject_id: str
    dimension: Dimension
    from_value: Any
    to_value: Any
    reason: str
    transition_kind: TransitionKind | None = None

    def __post_init__(self) -> None:
        if not self.subject_id.strip():
            raise InvalidEvent("declared change requires subject_id")
        object.__setattr__(self, "dimension", _enum(self.dimension, Dimension))
        if not self.reason.strip():
            raise InvalidEvent("declared change requires a reason")
        if self.transition_kind is not None:
            object.__setattr__(self, "transition_kind", _enum(self.transition_kind, TransitionKind))
        object.__setattr__(self, "from_value", _jsonable(self.from_value))
        object.__setattr__(self, "to_value", _jsonable(self.to_value))
        try:
            json.dumps(self.from_value, sort_keys=True)
            json.dumps(self.to_value, sort_keys=True)
        except (TypeError, ValueError) as exc:
            raise InvalidEvent("declared change values must be JSON serializable") from exc

    def to_dict(self) -> dict[str, Any]:
        return {
            "subject_id": self.subject_id,
            "dimension": self.dimension.value,
            "from_value": self.from_value,
            "to_value": self.to_value,
            "reason": self.reason,
            "transition_kind": self.transition_kind.value if self.transition_kind else None,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "DeclaredChange":
        required = ("subject_id", "dimension", "from_value", "to_value", "reason", "transition_kind")
        for name in required:
            if name not in data:
                raise InvalidEvent(f"declared change missing required field {name!r}")
        return cls(
            subject_id=data["subject_id"],
            dimension=data["dimension"],
            from_value=data["from_value"],
            to_value=data["to_value"],
            reason=data["reason"],
            transition_kind=data["transition_kind"],
        )


@dataclass(frozen=True)
class AuthorizationEvent:
    authorization_id: str
    authorized_by: Actor
    subject_id: str
    transition_kind: TransitionKind
    from_value: Any
    to_value: Any
    reason: str
    evidence_refs: tuple[str, ...] = field(default_factory=tuple)
    created_at: str = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        if not self.authorization_id.strip():
            raise InvalidEvent("authorization requires authorization_id")
        if not isinstance(self.authorized_by, Actor):
            raise InvalidEvent("authorization requires an Actor")
        if self.authorized_by.kind is not ActorKind.HUMAN:
            raise InvalidEvent("only a human actor can create an authorization event")
        if not self.subject_id.strip() or not self.reason.strip():
            raise InvalidEvent("authorization requires subject_id and reason")
        object.__setattr__(self, "transition_kind", _enum(self.transition_kind, TransitionKind))
        object.__setattr__(self, "from_value", _jsonable(self.from_value))
        object.__setattr__(self, "to_value", _jsonable(self.to_value))
        object.__setattr__(self, "evidence_refs", _tuple(self.evidence_refs, "authorization evidence_refs"))
        try:
            json.dumps(self.from_value, sort_keys=True)
            json.dumps(self.to_value, sort_keys=True)
        except (TypeError, ValueError) as exc:
            raise InvalidEvent("authorization values must be JSON serializable") from exc

    def to_dict(self) -> dict[str, Any]:
        return {
            "authorization_id": self.authorization_id,
            "authorized_by": self.authorized_by.to_dict(),
            "subject_id": self.subject_id,
            "transition_kind": self.transition_kind.value,
            "from_value": self.from_value,
            "to_value": self.to_value,
            "reason": self.reason,
            "evidence_refs": list(self.evidence_refs),
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "AuthorizationEvent":
        required = ("authorization_id", "authorized_by", "subject_id", "transition_kind", "from_value", "to_value", "reason", "evidence_refs", "created_at")
        for name in required:
            if name not in data:
                raise InvalidEvent(f"authorization missing required field {name!r}")
        return cls(
            authorization_id=data["authorization_id"],
            authorized_by=Actor.from_dict(data["authorized_by"]),
            subject_id=data["subject_id"],
            transition_kind=data["transition_kind"],
            from_value=data["from_value"],
            to_value=data["to_value"],
            reason=data["reason"],
            evidence_refs=data["evidence_refs"],
            created_at=data["created_at"],
        )


@dataclass(frozen=True)
class EvidenceRecord:
    evidence_id: str
    subject_id: str
    kind: EvidenceKind
    provided_by: Actor
    independent: bool = False
    active: bool = True
    detail: Mapping[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        if not self.evidence_id.strip() or not self.subject_id.strip():
            raise InvalidEvent("evidence requires evidence_id and subject_id")
        if not isinstance(self.provided_by, Actor):
            raise InvalidEvent("evidence requires a provider Actor")
        object.__setattr__(self, "kind", _enum(self.kind, EvidenceKind))
        if self.kind is EvidenceKind.MODEL_CONSENSUS and self.independent:
            raise InvalidEvent("model consensus cannot be marked independent")
        if self.independent and self.provided_by.kind is ActorKind.MODEL:
            raise InvalidEvent("a model cannot provide independent verification")
        detail = dict(self.detail or {})
        try:
            json.dumps(detail, sort_keys=True)
        except (TypeError, ValueError) as exc:
            raise InvalidEvent("evidence detail must be JSON serializable") from exc
        object.__setattr__(self, "detail", MappingProxyType(detail))

    def to_dict(self) -> dict[str, Any]:
        return {
            "evidence_id": self.evidence_id,
            "subject_id": self.subject_id,
            "kind": self.kind.value,
            "provided_by": self.provided_by.to_dict(),
            "independent": self.independent,
            "active": self.active,
            "detail": dict(self.detail),
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "EvidenceRecord":
        required = ("evidence_id", "subject_id", "kind", "provided_by", "independent", "active", "detail", "created_at")
        for name in required:
            if name not in data:
                raise InvalidEvent(f"evidence missing required field {name!r}")
        return cls(
            evidence_id=data["evidence_id"],
            subject_id=data["subject_id"],
            kind=data["kind"],
            provided_by=Actor.from_dict(data["provided_by"]),
            independent=data["independent"],
            active=data["active"],
            detail=data["detail"],
            created_at=data["created_at"],
        )


@dataclass(frozen=True)
class TransformationRecord:
    transformation_id: str
    input_artifact_ids: tuple[str, ...]
    output_artifact_id: str
    transformer: Actor
    transformation_type: str
    declared_changes: tuple[DeclaredChange, ...]
    input_hashes: tuple[str, ...]
    output_hash: str
    authorization_refs: tuple[str, ...] = field(default_factory=tuple)
    evidence_refs: tuple[str, ...] = field(default_factory=tuple)
    reason: str = ""
    claimed_validation_results: tuple[str, ...] = field(default_factory=tuple)
    created_at: str = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        for name in ("transformation_id", "output_artifact_id", "transformation_type", "output_hash"):
            if not isinstance(getattr(self, name), str) or not getattr(self, name).strip():
                raise InvalidEvent(f"transformation requires non-empty {name}")
        if not isinstance(self.transformer, Actor):
            raise InvalidEvent("transformation requires transformer Actor")
        object.__setattr__(self, "input_artifact_ids", _tuple(self.input_artifact_ids, "input_artifact_ids"))
        object.__setattr__(self, "input_hashes", _tuple(self.input_hashes, "input_hashes"))
        if len(self.input_artifact_ids) != len(self.input_hashes):
            raise InvalidEvent("input_artifact_ids and input_hashes must have equal length")
        object.__setattr__(self, "declared_changes", tuple(self.declared_changes))
        if any(not isinstance(item, DeclaredChange) for item in self.declared_changes):
            raise InvalidEvent("declared_changes must contain DeclaredChange objects")
        for name in ("authorization_refs", "evidence_refs", "claimed_validation_results"):
            object.__setattr__(self, name, _tuple(getattr(self, name), name))

    def to_dict(self) -> dict[str, Any]:
        return {
            "transformation_id": self.transformation_id,
            "input_artifact_ids": list(self.input_artifact_ids),
            "output_artifact_id": self.output_artifact_id,
            "transformer": self.transformer.to_dict(),
            "transformation_type": self.transformation_type,
            "declared_changes": [item.to_dict() for item in self.declared_changes],
            "input_hashes": list(self.input_hashes),
            "output_hash": self.output_hash,
            "authorization_refs": list(self.authorization_refs),
            "evidence_refs": list(self.evidence_refs),
            "reason": self.reason,
            "claimed_validation_results": list(self.claimed_validation_results),
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "TransformationRecord":
        required = ("transformation_id", "input_artifact_ids", "output_artifact_id", "transformer", "transformation_type", "declared_changes", "input_hashes", "output_hash", "authorization_refs", "evidence_refs", "reason", "claimed_validation_results", "created_at")
        for name in required:
            if name not in data:
                raise InvalidEvent(f"transformation missing required field {name!r}")
        return cls(
            transformation_id=data["transformation_id"],
            input_artifact_ids=data["input_artifact_ids"],
            output_artifact_id=data["output_artifact_id"],
            transformer=Actor.from_dict(data["transformer"]),
            transformation_type=data["transformation_type"],
            declared_changes=tuple(DeclaredChange.from_dict(item) for item in data["declared_changes"]),
            input_hashes=data["input_hashes"],
            output_hash=data["output_hash"],
            authorization_refs=data["authorization_refs"],
            evidence_refs=data["evidence_refs"],
            reason=data["reason"],
            claimed_validation_results=data["claimed_validation_results"],
            created_at=data["created_at"],
        )

    def canonical_digest(self) -> str:
        from hashlib import sha256
        return sha256(canonical_json(self.to_dict()).encode("utf-8")).hexdigest()
