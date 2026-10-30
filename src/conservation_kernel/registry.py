"""External evidence and authorization registry used by the verifier."""

from __future__ import annotations

from .errors import InvalidEvent
from .events import AuthorizationEvent, EvidenceRecord


class EvidenceRegistry:
    """A deliberately separate witness store.

    A transformation record can name an authorization or evidence ID, but it
    cannot create a valid human event by placing a similarly shaped object in
    its own envelope. In a deployed system this registry is the protocol
    boundary; this in-memory implementation makes that boundary testable.
    """

    def __init__(self, *, trusted_humans: set[str] | frozenset[str] | None = None) -> None:
        # ActorKind.HUMAN is a self-declaration on a caller-supplied dataclass:
        # a machine that constructs Actor("agent", kind=HUMAN) mints valid
        # human authorizations (measured 2026-09-08). The kernel cannot know
        # who is human; the deployer can. When `trusted_humans` is given, an
        # authorization is accepted only from an actor id in that set. When
        # it is None the registry behaves as before, and that fact is the
        # trust assumption every downstream "human authorized" claim rests on.
        self.trusted_humans = frozenset(trusted_humans) if trusted_humans is not None else None
        self._evidence: dict[str, EvidenceRecord] = {}
        self._authorizations: dict[str, AuthorizationEvent] = {}

    def add_evidence(self, record: EvidenceRecord) -> None:
        if record.evidence_id in self._evidence:
            raise InvalidEvent(f"duplicate evidence ID {record.evidence_id}")
        self._evidence[record.evidence_id] = record

    def add_authorization(self, event: AuthorizationEvent) -> None:
        if self.trusted_humans is not None and event.authorized_by.actor_id not in self.trusted_humans:
            raise InvalidEvent(
                f"authorization {event.authorization_id} is by {event.authorized_by.actor_id!r}, "
                "which this registry does not recognise as a human authorizer"
            )
        if event.authorization_id in self._authorizations:
            raise InvalidEvent(f"duplicate authorization ID {event.authorization_id}")
        self._authorizations[event.authorization_id] = event

    def evidence(self, evidence_id: str) -> EvidenceRecord | None:
        return self._evidence.get(evidence_id)

    def authorization(self, authorization_id: str) -> AuthorizationEvent | None:
        """The authorization with this id, whatever its standing. To decide with it, use `at(as_of)`."""
        return self._authorizations.get(authorization_id)

    def in_force(self, event: AuthorizationEvent, as_of: str | None) -> bool:
        """Whether `event` may be relied on at `as_of`."""
        return True

    def at(self, as_of: str | None) -> "RegistryAt":
        """This registry as of one moment: an authorization counts only if it is in force then.

        The verifier and the kernel decide through this view, so no check can consult an authorization
        without its time being applied. `as_of` None means the time is unknown."""
        return RegistryAt(self, as_of)

    def has_active_evidence(
        self,
        refs: tuple[str, ...] | list[str],
        *,
        subject_ids: set[str],
        kinds: set,
        independent: bool | None = None,
    ) -> bool:
        for ref in refs:
            item = self._evidence.get(ref)
            if item is None or not item.active:
                continue
            # A wildcard subject counts only where the caller explicitly allows
            # it (the functional-validation check does). Before this a single
            # `subject_id="*"` record satisfied every strong claim for every
            # subject (measured 2026-09-08).
            if item.subject_id not in subject_ids:
                continue
            if item.kind not in kinds:
                continue
            if independent is not None and item.independent is not independent:
                continue
            return True
        return False

    def inactive_refs(self, refs: tuple[str, ...] | list[str]) -> tuple[str, ...]:
        return tuple(ref for ref in refs if ref in self._evidence and not self._evidence[ref].active)

    def missing_refs(self, refs: tuple[str, ...] | list[str]) -> tuple[str, ...]:
        return tuple(ref for ref in refs if ref not in self._evidence)

    def has_authorization(
        self,
        refs: tuple[str, ...] | list[str],
        *,
        subject_id: str,
        transition_kind,
        from_value,
        to_value,
        as_of: str | None = None,
    ) -> bool:
        for ref in refs:
            event = self._authorizations.get(ref)
            if event is None or not self.in_force(event, as_of):
                continue
            if event.subject_id != subject_id:
                continue
            if event.transition_kind is not transition_kind:
                continue
            if event.from_value != from_value or event.to_value != to_value:
                continue
            return True
        return False

    def snapshot(self) -> dict:
        return {
            "evidence": [item.to_dict() for item in self._evidence.values()],
            "authorizations": [item.to_dict() for item in self._authorizations.values()],
        }

    @classmethod
    def restore(cls, snapshot: dict, *, trusted_humans=None) -> "EvidenceRegistry":
        """A registry rebuilt from `snapshot()`. Authorizations go through
        add_authorization, so a trusted-humans binding is enforced on
        restore as it was live."""
        registry = cls(trusted_humans=trusted_humans)
        for item in snapshot.get("evidence", []):
            registry.add_evidence(EvidenceRecord.from_dict(item))
        for item in snapshot.get("authorizations", []):
            registry.add_authorization(AuthorizationEvent.from_dict(item))
        return registry


class RegistryAt:
    """An `EvidenceRegistry` seen as of one moment (see `EvidenceRegistry.at`).

    Evidence lookups pass straight through. Authorization lookups return only what is in force at
    `as_of`, so a caller holding this view cannot reach an expired or revoked authorization by mistake."""

    def __init__(self, registry: EvidenceRegistry, as_of: str | None) -> None:
        self.registry = registry
        self.as_of = as_of

    def at(self, as_of: str | None) -> "RegistryAt":
        return RegistryAt(self.registry, as_of)

    def evidence(self, evidence_id: str):
        return self.registry.evidence(evidence_id)

    def has_active_evidence(self, refs, **kwargs) -> bool:
        return self.registry.has_active_evidence(refs, **kwargs)

    def inactive_refs(self, refs):
        return self.registry.inactive_refs(refs)

    def missing_refs(self, refs):
        return self.registry.missing_refs(refs)

    def authorization(self, authorization_id: str) -> AuthorizationEvent | None:
        event = self.registry.authorization(authorization_id)
        return event if event is not None and self.registry.in_force(event, self.as_of) else None

    def has_authorization(self, refs, **kwargs) -> bool:
        return self.registry.has_authorization(refs, as_of=self.as_of, **kwargs)
