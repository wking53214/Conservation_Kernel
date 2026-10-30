"""Append-only records supplied alongside transformations.

The transformer may declare a change, but declarations are not evidence.  The
verifier recomputes observed changes from input and output artifacts and only
consults authorization/evidence records that exist in the external registry.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
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


def instant(value: Any, name: str) -> datetime:
    """`value` as a moment in time: an ISO 8601 string that names its UTC offset.

    A timestamp with no offset is refused, because whether a window is open depends on whose
    midnight it means."""
    if not isinstance(value, str) or not value.strip():
        raise InvalidEvent(f"{name} must be an ISO 8601 timestamp string")
    try:
        moment = datetime.fromisoformat(value)
    except ValueError as exc:
        raise InvalidEvent(f"{name} is not an ISO 8601 timestamp: {value!r}") from exc
    if moment.tzinfo is None or moment.utcoffset() is None:
        raise InvalidEvent(f"{name} must state its UTC offset: {value!r}")
    return moment


def _check_window(valid_from: str | None, valid_until: str | None, label: str) -> None:
    opens = instant(valid_from, "valid_from") if valid_from is not None else None
    closes = instant(valid_until, "valid_until") if valid_until is not None else None
    if opens is not None and closes is not None and not opens < closes:
        raise InvalidEvent(f"{label} must open before it closes")


class _Window:
    """A half-open window, [`valid_from`, `valid_until`), on an authorization or a delegation."""

    valid_from: str | None
    valid_until: str | None

    @property
    def windowed(self) -> bool:
        """Whether this holds only for a window."""
        return self.valid_from is not None or self.valid_until is not None

    def holds_at(self, moment: datetime) -> bool:
        """Whether `moment` is inside the window."""
        if self.valid_from is not None and moment < instant(self.valid_from, "valid_from"):
            return False
        if self.valid_until is not None and moment >= instant(self.valid_until, "valid_until"):
            return False
        return True


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
class AuthorizationEvent(_Window):
    authorization_id: str
    authorized_by: Actor
    subject_id: str
    transition_kind: TransitionKind
    from_value: Any
    to_value: Any
    reason: str
    evidence_refs: tuple[str, ...] = field(default_factory=tuple)
    created_at: str = field(default_factory=utc_now)
    #: The window this authorization holds for, half-open: from `valid_from` (inclusive) to `valid_until`
    #: (exclusive). Either may be None for no bound; with neither it holds whenever it is consulted, as every
    #: authorization did before windows. Judged against the deciding kernel's clock, never `created_at`.
    valid_from: str | None = None
    valid_until: str | None = None
    #: The delegation this was issued under, when its author holds the power to authorize by delegation rather than
    #: by being trusted directly. It counts only while every link of that delegation's chain is in force and covers it.
    under_delegation: str | None = None
    #: What this authorization is about: the `Proposition.canonical_digest` of the words the human approved. When set,
    #: the authorization counts only for a proposition with that digest, so one approval of "Refund customer $10." cannot
    #: stand in for "Refund customer $10,000,000.". Optional, so an authorization without one is judged as it always was;
    #: a registry built with `require_content_bound` refuses one without.
    subject_digest: str | None = None

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
        _check_window(self.valid_from, self.valid_until, f"authorization {self.authorization_id}")
        if self.under_delegation is not None and (not isinstance(self.under_delegation, str)
                                                  or not self.under_delegation.strip()):
            raise InvalidEvent("under_delegation must be a delegation id or None")
        if self.subject_digest is not None and (not isinstance(self.subject_digest, str)
                                                or not self.subject_digest.strip()):
            raise InvalidEvent("subject_digest must be a proposition digest or None")

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
            # Present only when set, so an open-ended authorization (and every digest over it) keeps its old shape.
            **({"valid_from": self.valid_from} if self.valid_from is not None else {}),
            **({"valid_until": self.valid_until} if self.valid_until is not None else {}),
            **({"under_delegation": self.under_delegation} if self.under_delegation is not None else {}),
            **({"subject_digest": self.subject_digest} if self.subject_digest is not None else {}),
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
            valid_from=data.get("valid_from"),
            valid_until=data.get("valid_until"),
            under_delegation=data.get("under_delegation"),
            subject_digest=data.get("subject_digest"),
        )


@dataclass(frozen=True)
class DelegationEvent(_Window):
    """A human letting a named delegate issue authorizations, within a stated scope.

    The scope is three explicit lists: the subjects (by id, one by one; there is no pattern or wildcard), the kinds
    of change, and the target values an authorization under it may carry. It holds for its own window and until it
    is revoked (a `RevocationEvent` naming its `delegation_id`). The delegate may pass on part of it only if
    `may_redelegate` is set; the child names this one as `parent_delegation_id`, must be issued by this one's
    delegate, and may only narrow the scope. The chain must start at a human the registry trusts."""

    delegation_id: str
    delegator: Actor
    delegate_id: str
    subject_ids: tuple[str, ...]
    transition_kinds: tuple[TransitionKind, ...]
    to_values: tuple[Any, ...]
    reason: str
    parent_delegation_id: str | None = None
    may_redelegate: bool = False
    valid_from: str | None = None
    valid_until: str | None = None
    created_at: str = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        for name in ("delegation_id", "delegate_id", "reason"):
            if not isinstance(getattr(self, name), str) or not getattr(self, name).strip():
                raise InvalidEvent(f"delegation requires {name}")
        if not isinstance(self.delegator, Actor):
            raise InvalidEvent("delegation requires a delegator Actor")
        if self.delegator.kind is not ActorKind.HUMAN:
            raise InvalidEvent("only a human actor can delegate the power to authorize")
        if self.delegate_id == self.delegator.actor_id:
            raise InvalidEvent("a delegation must be to someone else")
        object.__setattr__(self, "subject_ids", _tuple(self.subject_ids, "delegation subject_ids"))
        if isinstance(self.transition_kinds, (str, bytes)):
            raise InvalidEvent("delegation transition_kinds must be a sequence")
        object.__setattr__(self, "transition_kinds", tuple(_enum(kind, TransitionKind) for kind in self.transition_kinds))
        if isinstance(self.to_values, (str, bytes)):
            raise InvalidEvent("delegation to_values must be a sequence")
        object.__setattr__(self, "to_values", tuple(_jsonable(value) for value in self.to_values))
        for name in ("subject_ids", "transition_kinds", "to_values"):
            if not getattr(self, name):
                raise InvalidEvent(f"a delegation must name at least one of its {name}; it has no open-ended scope")
        try:
            json.dumps(list(self.to_values), sort_keys=True)
        except (TypeError, ValueError) as exc:
            raise InvalidEvent("delegation to_values must be JSON serializable") from exc
        if self.parent_delegation_id is not None and (not isinstance(self.parent_delegation_id, str)
                                                      or not self.parent_delegation_id.strip()):
            raise InvalidEvent("parent_delegation_id must be a delegation id or None")
        if not isinstance(self.may_redelegate, bool):
            raise InvalidEvent("may_redelegate must be true or false")
        _check_window(self.valid_from, self.valid_until, f"delegation {self.delegation_id}")

    def covers(self, subject_id: str, transition_kind: TransitionKind, to_value: Any) -> bool:
        """Whether an authorization of this change falls inside this delegation's scope."""
        return (subject_id in self.subject_ids and transition_kind in self.transition_kinds
                and to_value in self.to_values)

    def to_dict(self) -> dict[str, Any]:
        return {
            "delegation_id": self.delegation_id,
            "delegator": self.delegator.to_dict(),
            "delegate_id": self.delegate_id,
            "subject_ids": list(self.subject_ids),
            "transition_kinds": [kind.value for kind in self.transition_kinds],
            "to_values": list(self.to_values),
            "reason": self.reason,
            "parent_delegation_id": self.parent_delegation_id,
            "may_redelegate": self.may_redelegate,
            "valid_from": self.valid_from,
            "valid_until": self.valid_until,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "DelegationEvent":
        required = ("delegation_id", "delegator", "delegate_id", "subject_ids", "transition_kinds", "to_values",
                    "reason", "parent_delegation_id", "may_redelegate", "valid_from", "valid_until", "created_at")
        for name in required:
            if name not in data:
                raise InvalidEvent(f"delegation missing required field {name!r}")
        return cls(
            delegation_id=data["delegation_id"],
            delegator=Actor.from_dict(data["delegator"]),
            delegate_id=data["delegate_id"],
            subject_ids=data["subject_ids"],
            transition_kinds=data["transition_kinds"],
            to_values=data["to_values"],
            reason=data["reason"],
            parent_delegation_id=data["parent_delegation_id"],
            may_redelegate=data["may_redelegate"],
            valid_from=data["valid_from"],
            valid_until=data["valid_until"],
            created_at=data["created_at"],
        )


@dataclass(frozen=True)
class RevocationEvent:
    """A human ending an authorization, or a delegation (`authorization_id` names either), from a moment forward.

    It takes effect when the deciding kernel records it, or at the later `effective_at` if one is given, and from
    then on the authorization it names does not count. It never reaches back: `EvidenceRegistry.add_revocation`
    refuses one whose `effective_at` is before the moment it is recorded, so a decision made while the
    authorization held stays valid and still re-verifies. Any human the registry trusts may revoke: ending an
    authorization can only take power away."""

    revocation_id: str
    authorization_id: str
    revoked_by: Actor
    reason: str
    effective_at: str | None = None
    created_at: str = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        if not isinstance(self.revocation_id, str) or not self.revocation_id.strip():
            raise InvalidEvent("revocation requires revocation_id")
        if not isinstance(self.authorization_id, str) or not self.authorization_id.strip():
            raise InvalidEvent("revocation requires the authorization_id it ends")
        if not isinstance(self.revoked_by, Actor):
            raise InvalidEvent("revocation requires an Actor")
        if self.revoked_by.kind is not ActorKind.HUMAN:
            raise InvalidEvent("only a human actor can revoke an authorization")
        if not isinstance(self.reason, str) or not self.reason.strip():
            raise InvalidEvent("revocation requires a reason")
        if self.effective_at is not None:
            instant(self.effective_at, "effective_at")

    def to_dict(self) -> dict[str, Any]:
        return {
            "revocation_id": self.revocation_id,
            "authorization_id": self.authorization_id,
            "revoked_by": self.revoked_by.to_dict(),
            "reason": self.reason,
            "effective_at": self.effective_at,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "RevocationEvent":
        required = ("revocation_id", "authorization_id", "revoked_by", "reason", "effective_at", "created_at")
        for name in required:
            if name not in data:
                raise InvalidEvent(f"revocation missing required field {name!r}")
        return cls(
            revocation_id=data["revocation_id"],
            authorization_id=data["authorization_id"],
            revoked_by=Actor.from_dict(data["revoked_by"]),
            reason=data["reason"],
            effective_at=data["effective_at"],
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
