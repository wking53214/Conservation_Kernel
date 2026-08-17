"""Typed immutable artifacts and their conservation envelope.

The artifact is intentionally proposition-oriented.  A whole document can
change wording while each proposition retains an explicit epistemic and
authority state.  The kernel therefore compares both the document payload and
the proposition-level envelope.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
from types import MappingProxyType
from typing import Any, Mapping

from .enums import (
    ActorKind,
    AuthorityStatus,
    CanonicalState,
    EpistemicStatus,
    OriginStatus,
    TemporalScope,
    UncertaintyState,
)
from .errors import InvalidArtifact


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _enum(value: Any, enum_type):
    if isinstance(value, enum_type):
        return value
    try:
        return enum_type(value)
    except (TypeError, ValueError) as exc:
        raise InvalidArtifact(f"invalid {enum_type.__name__}: {value!r}") from exc


def _plain(value: Any) -> Any:
    if isinstance(value, (ActorKind, AuthorityStatus, CanonicalState, EpistemicStatus,
                          OriginStatus, TemporalScope, UncertaintyState)):
        return value.value
    if hasattr(value, "to_dict"):
        return value.to_dict()
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (tuple, list, set)):
        return [_plain(item) for item in value]
    return value


def canonical_json(value: Any) -> str:
    return json.dumps(_plain(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _digest(value: Any) -> str:
    return sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _tuple(values: Any, *, field_name: str, unique: bool = False) -> tuple[Any, ...]:
    if values is None:
        return ()
    if isinstance(values, (str, bytes)):
        raise InvalidArtifact(f"{field_name} must be a sequence, not a string")
    try:
        result = tuple(values)
    except TypeError as exc:
        raise InvalidArtifact(f"{field_name} must be a sequence") from exc
    if any(not isinstance(item, str) or not item.strip() for item in result):
        raise InvalidArtifact(f"{field_name} may contain only non-empty strings")
    if unique and len(result) != len(set(result)):
        raise InvalidArtifact(f"{field_name} may not contain duplicates")
    return result


@dataclass(frozen=True)
class Actor:
    actor_id: str
    kind: ActorKind
    label: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.actor_id, str) or not self.actor_id.strip():
            raise InvalidArtifact("actor_id must be non-empty")
        object.__setattr__(self, "kind", _enum(self.kind, ActorKind))

    @classmethod
    def human(cls, actor_id: str = "human", label: str = "") -> "Actor":
        return cls(actor_id, ActorKind.HUMAN, label)

    @classmethod
    def model(cls, actor_id: str = "model", label: str = "") -> "Actor":
        return cls(actor_id, ActorKind.MODEL, label)

    @classmethod
    def system(cls, actor_id: str = "kernel", label: str = "") -> "Actor":
        return cls(actor_id, ActorKind.SYSTEM, label)

    @classmethod
    def external(cls, actor_id: str = "external", label: str = "") -> "Actor":
        return cls(actor_id, ActorKind.EXTERNAL, label)

    def to_dict(self) -> dict[str, Any]:
        return {"actor_id": self.actor_id, "kind": self.kind.value, "label": self.label}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "Actor":
        try:
            return cls(actor_id=data["actor_id"], kind=data["kind"], label=data.get("label", ""))
        except KeyError as exc:
            raise InvalidArtifact(f"actor missing required field {exc.args[0]!r}") from exc


@dataclass(frozen=True)
class Uncertainty:
    state: UncertaintyState = UncertaintyState.NONE
    reason: str = ""

    def __post_init__(self) -> None:
        state = _enum(self.state, UncertaintyState)
        object.__setattr__(self, "state", state)
        if state is not UncertaintyState.NONE and not self.reason.strip():
            raise InvalidArtifact(f"uncertainty state {state.value} requires a reason")

    def to_dict(self) -> dict[str, Any]:
        return {"state": self.state.value, "reason": self.reason}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "Uncertainty":
        try:
            return cls(state=data["state"], reason=data.get("reason", ""))
        except KeyError as exc:
            raise InvalidArtifact(f"uncertainty missing required field {exc.args[0]!r}") from exc


@dataclass(frozen=True)
class TemporalMetadata:
    scope: TemporalScope = TemporalScope.UNKNOWN
    occurred_at: str | None = None
    observed_at: str | None = None
    valid_from: str | None = None
    valid_until: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "scope", _enum(self.scope, TemporalScope))
        for name in ("occurred_at", "observed_at", "valid_from", "valid_until"):
            value = getattr(self, name)
            if value is not None and (not isinstance(value, str) or not value.strip()):
                raise InvalidArtifact(f"{name} must be a non-empty timestamp string or null")

    def to_dict(self) -> dict[str, Any]:
        return {
            "scope": self.scope.value,
            "occurred_at": self.occurred_at,
            "observed_at": self.observed_at,
            "valid_from": self.valid_from,
            "valid_until": self.valid_until,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "TemporalMetadata":
        try:
            return cls(
                scope=data["scope"],
                occurred_at=data.get("occurred_at"),
                observed_at=data.get("observed_at"),
                valid_from=data.get("valid_from"),
                valid_until=data.get("valid_until"),
            )
        except KeyError as exc:
            raise InvalidArtifact(f"temporal metadata missing required field {exc.args[0]!r}") from exc


@dataclass(frozen=True)
class FunctionalContract:
    contract_id: str
    required_properties: tuple[str, ...]
    validation_method: str

    def __post_init__(self) -> None:
        if not self.contract_id.strip():
            raise InvalidArtifact("functional contract requires contract_id")
        object.__setattr__(self, "required_properties", _tuple(self.required_properties, field_name="required_properties", unique=True))
        if not self.validation_method.strip():
            raise InvalidArtifact("functional contract requires validation_method")

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract_id": self.contract_id,
            "required_properties": list(self.required_properties),
            "validation_method": self.validation_method,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "FunctionalContract":
        try:
            return cls(
                contract_id=data["contract_id"],
                required_properties=data["required_properties"],
                validation_method=data["validation_method"],
            )
        except KeyError as exc:
            raise InvalidArtifact(f"functional contract missing required field {exc.args[0]!r}") from exc


@dataclass(frozen=True)
class Proposition:
    proposition_id: str
    text: str
    epistemic_status: EpistemicStatus
    origin: OriginStatus
    authority: AuthorityStatus = AuthorityStatus.NONE
    uncertainty: Uncertainty = field(default_factory=Uncertainty)
    temporal: TemporalMetadata = field(default_factory=TemporalMetadata)
    evidence_refs: tuple[str, ...] = field(default_factory=tuple)
    authorization_refs: tuple[str, ...] = field(default_factory=tuple)
    canonical_state: CanonicalState = CanonicalState.PROPOSED
    parent_proposition_ids: tuple[str, ...] = field(default_factory=tuple)
    source_refs: tuple[str, ...] = field(default_factory=tuple)
    derivation_method: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.proposition_id, str) or not self.proposition_id.strip():
            raise InvalidArtifact("proposition_id must be non-empty")
        if not isinstance(self.text, str) or not self.text.strip():
            raise InvalidArtifact(f"proposition {self.proposition_id} requires non-empty text")
        object.__setattr__(self, "epistemic_status", _enum(self.epistemic_status, EpistemicStatus))
        object.__setattr__(self, "origin", _enum(self.origin, OriginStatus))
        object.__setattr__(self, "authority", _enum(self.authority, AuthorityStatus))
        object.__setattr__(self, "canonical_state", _enum(self.canonical_state, CanonicalState))
        if not isinstance(self.uncertainty, Uncertainty):
            object.__setattr__(self, "uncertainty", Uncertainty.from_dict(self.uncertainty))
        if not isinstance(self.temporal, TemporalMetadata):
            object.__setattr__(self, "temporal", TemporalMetadata.from_dict(self.temporal))
        for name in ("evidence_refs", "authorization_refs", "parent_proposition_ids", "source_refs"):
            object.__setattr__(self, name, _tuple(getattr(self, name), field_name=name, unique=True))
        metadata = dict(self.metadata or {})
        if self.epistemic_status in {EpistemicStatus.ESTIMATED, EpistemicStatus.SIMULATED} and not str(self.derivation_method or "").strip():
            raise InvalidArtifact(f"{self.epistemic_status.value} proposition requires a named derivation_method")
        if self.origin is OriginStatus.HUMAN_ADOPTED_MACHINE_OUTPUT and not self.authorization_refs:
            raise InvalidArtifact("human-adopted machine output requires authorization_refs")
        if self.authority in {AuthorityStatus.HUMAN_AUTHORIZED, AuthorityStatus.CANONICAL, AuthorityStatus.EXECUTED} and not self.authorization_refs:
            raise InvalidArtifact(f"authority {self.authority.value} requires authorization_refs")
        if self.canonical_state in {CanonicalState.ACCEPTED, CanonicalState.CANONICAL, CanonicalState.SUPERSEDED, CanonicalState.REVOKED, CanonicalState.DELETED} and not self.authorization_refs:
            raise InvalidArtifact(f"canonical state {self.canonical_state.value} requires authorization_refs")
        try:
            json.dumps(metadata, sort_keys=True)
        except (TypeError, ValueError) as exc:
            raise InvalidArtifact(f"metadata for {self.proposition_id} is not JSON serializable") from exc
        object.__setattr__(self, "metadata", MappingProxyType(metadata))

    def to_dict(self) -> dict[str, Any]:
        return {
            "proposition_id": self.proposition_id,
            "text": self.text,
            "epistemic_status": self.epistemic_status.value,
            "origin": self.origin.value,
            "authority": self.authority.value,
            "uncertainty": self.uncertainty.to_dict(),
            "temporal": self.temporal.to_dict(),
            "evidence_refs": list(self.evidence_refs),
            "authorization_refs": list(self.authorization_refs),
            "canonical_state": self.canonical_state.value,
            "parent_proposition_ids": list(self.parent_proposition_ids),
            "source_refs": list(self.source_refs),
            "derivation_method": self.derivation_method,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "Proposition":
        required = ("proposition_id", "text", "epistemic_status", "origin", "authority", "uncertainty", "temporal", "evidence_refs", "authorization_refs", "canonical_state", "parent_proposition_ids", "source_refs", "derivation_method", "metadata")
        for name in required:
            if name not in data:
                raise InvalidArtifact(f"proposition missing required field {name!r}; no silent repair")
        return cls(
            proposition_id=data["proposition_id"],
            text=data["text"],
            epistemic_status=data["epistemic_status"],
            origin=data["origin"],
            authority=data["authority"],
            uncertainty=Uncertainty.from_dict(data["uncertainty"]),
            temporal=TemporalMetadata.from_dict(data["temporal"]),
            evidence_refs=data["evidence_refs"],
            authorization_refs=data["authorization_refs"],
            canonical_state=data["canonical_state"],
            parent_proposition_ids=data["parent_proposition_ids"],
            source_refs=data["source_refs"],
            derivation_method=data["derivation_method"],
            metadata=data["metadata"],
        )


@dataclass(frozen=True)
class Artifact:
    artifact_id: str
    content: str
    propositions: tuple[Proposition, ...]
    producer: Actor
    parent_artifact_ids: tuple[str, ...] = field(default_factory=tuple)
    version: int = 1
    functional_contract: FunctionalContract | None = None
    created_at: str = field(default_factory=utc_now)
    content_digest: str | None = None
    artifact_digest: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.artifact_id, str) or not self.artifact_id.strip():
            raise InvalidArtifact("artifact_id must be non-empty")
        if not isinstance(self.content, str) or not self.content.strip():
            raise InvalidArtifact("artifact content must be a non-empty string")
        if not isinstance(self.producer, Actor):
            raise InvalidArtifact("producer must be an Actor")
        props = tuple(self.propositions)
        if any(not isinstance(item, Proposition) for item in props):
            raise InvalidArtifact("propositions must contain Proposition objects")
        if len({item.proposition_id for item in props}) != len(props):
            raise InvalidArtifact("proposition IDs must be unique within an artifact")
        object.__setattr__(self, "propositions", props)
        object.__setattr__(self, "parent_artifact_ids", _tuple(self.parent_artifact_ids, field_name="parent_artifact_ids", unique=True))
        if self.artifact_id in self.parent_artifact_ids:
            raise InvalidArtifact("an artifact cannot be its own parent")
        if not isinstance(self.version, int) or isinstance(self.version, bool) or self.version < 1:
            raise InvalidArtifact("version must be a positive integer")
        if self.functional_contract is not None and not isinstance(self.functional_contract, FunctionalContract):
            object.__setattr__(self, "functional_contract", FunctionalContract.from_dict(self.functional_contract))
        computed_content = sha256(self.content.encode("utf-8")).hexdigest()
        if self.content_digest is not None and self.content_digest != computed_content:
            raise InvalidArtifact(f"content_digest mismatch for artifact {self.artifact_id}")
        object.__setattr__(self, "content_digest", computed_content)
        computed_artifact = _digest(self._payload_dict())
        if self.artifact_digest is not None and self.artifact_digest != computed_artifact:
            raise InvalidArtifact(f"artifact_digest mismatch for artifact {self.artifact_id}")
        object.__setattr__(self, "artifact_digest", computed_artifact)

    def _payload_dict(self) -> dict[str, Any]:
        return {
            "artifact_id": self.artifact_id,
            "content": self.content,
            "content_digest": self.content_digest,
            "propositions": [item.to_dict() for item in self.propositions],
            "producer": self.producer.to_dict(),
            "parent_artifact_ids": list(self.parent_artifact_ids),
            "version": self.version,
            "functional_contract": self.functional_contract.to_dict() if self.functional_contract else None,
            "created_at": self.created_at,
        }

    def to_dict(self) -> dict[str, Any]:
        result = self._payload_dict()
        result["artifact_digest"] = self.artifact_digest
        return result

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, indent=2)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "Artifact":
        required = ("artifact_id", "content", "content_digest", "propositions", "producer", "parent_artifact_ids", "version", "functional_contract", "created_at", "artifact_digest")
        for name in required:
            if name not in data:
                raise InvalidArtifact(f"artifact missing required field {name!r}; no silent repair")
        return cls(
            artifact_id=data["artifact_id"],
            content=data["content"],
            propositions=tuple(Proposition.from_dict(item) for item in data["propositions"]),
            producer=Actor.from_dict(data["producer"]),
            parent_artifact_ids=data["parent_artifact_ids"],
            version=data["version"],
            functional_contract=FunctionalContract.from_dict(data["functional_contract"]) if data["functional_contract"] is not None else None,
            created_at=data["created_at"],
            content_digest=data["content_digest"],
            artifact_digest=data["artifact_digest"],
        )

    @classmethod
    def from_json(cls, text: str) -> "Artifact":
        try:
            value = json.loads(text)
        except json.JSONDecodeError as exc:
            raise InvalidArtifact("artifact JSON is malformed") from exc
        if not isinstance(value, Mapping):
            raise InvalidArtifact("artifact JSON must contain an object")
        return cls.from_dict(value)

    def proposition_map(self) -> dict[str, Proposition]:
        return {item.proposition_id: item for item in self.propositions}

    def envelope_summary(self) -> dict[str, Any]:
        """Return the machine-readable conservation envelope summary.

        This is derived from typed fields; it is not a second mutable source
        of truth. Transformation declarations and validation reports live in
        their own append-only records.
        """
        origins = sorted({item.origin.value for item in self.propositions})
        epistemic = sorted({item.epistemic_status.value for item in self.propositions})
        authorities = sorted({item.authority.value for item in self.propositions})
        evidence = sorted({ref for item in self.propositions for ref in item.evidence_refs})
        uncertainty = sorted({item.uncertainty.state.value for item in self.propositions})
        canonical = sorted({item.canonical_state.value for item in self.propositions})
        return {
            "artifact_id": self.artifact_id,
            "parent_artifact_ids": list(self.parent_artifact_ids),
            "version": self.version,
            "producer": self.producer.to_dict(),
            "human_or_machine_origin": origins,
            "epistemic_status": epistemic,
            "authority_status": authorities,
            "evidence_refs": evidence,
            "uncertainty": uncertainty,
            "conflict_state": "CONFLICTED" if "CONFLICTED" in uncertainty or "CONFLICTED" in epistemic else "NONE",
            "canonical_state": canonical,
            "temporal_metadata": [item.temporal.to_dict() for item in self.propositions],
            "input_hash": None,
            "output_hash": self.artifact_digest,
            "lineage": list(self.parent_artifact_ids),
            "functional_contract": self.functional_contract.to_dict() if self.functional_contract else None,
        }
