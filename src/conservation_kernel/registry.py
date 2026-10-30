"""External evidence and authorization registry used by the verifier."""

from __future__ import annotations

from .errors import InvalidEvent
from .events import AuthorizationEvent, EvidenceRecord, RevocationEvent, instant


class EvidenceRegistry:
    """A deliberately separate witness store.

    A transformation record can name an authorization or evidence ID, but it
    cannot create a valid human event by placing a similarly shaped object in
    its own envelope. In a deployed system this registry is the protocol
    boundary; this in-memory implementation makes that boundary testable.
    """

    def __init__(self, *, trusted_humans: set[str] | frozenset[str] | None = None,
                 require_bounded: bool = False) -> None:
        # ActorKind.HUMAN is a self-declaration on a caller-supplied dataclass:
        # a machine that constructs Actor("agent", kind=HUMAN) mints valid
        # human authorizations (measured 2026-09-08). The kernel cannot know
        # who is human; the deployer can. When `trusted_humans` is given, an
        # authorization is accepted only from an actor id in that set. When
        # it is None the registry behaves as before, and that fact is the
        # trust assumption every downstream "human authorized" claim rests on.
        self.trusted_humans = frozenset(trusted_humans) if trusted_humans is not None else None
        # Off by default, so nothing changes until a deployer asks: with it on, an authorization must say when it
        # stops holding (`valid_until`). An open-ended one is refused, live and on restore.
        self.require_bounded = require_bounded
        self._evidence: dict[str, EvidenceRecord] = {}
        self._authorizations: dict[str, AuthorizationEvent] = {}
        # revocation id -> (the revocation, when the registry recorded it). Recorded time is the deployer's clock,
        # handed in by whoever records it (ConservationKernel.revoke passes its own), never the revoker's claim.
        self._revocations: dict[str, tuple[RevocationEvent, str]] = {}

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
        if self.require_bounded and event.valid_until is None:
            raise InvalidEvent(
                f"authorization {event.authorization_id} has no end (valid_until), and this registry accepts only "
                "authorizations that stop holding at a stated time"
            )
        if event.authorization_id in self._authorizations:
            raise InvalidEvent(f"duplicate authorization ID {event.authorization_id}")
        self._authorizations[event.authorization_id] = event

    def add_revocation(self, event: RevocationEvent, *, recorded_at: str) -> None:
        """Record `event` as of `recorded_at` (ISO 8601 with offset), the recording clock's time.

        The revoker must be a human this registry trusts, where it names them. The authorization need not be here
        yet: a revocation that arrives first still applies when it does. A revocation whose `effective_at` is before
        `recorded_at` is refused, because applying it would re-judge decisions already made under the authorization
        and could leave the kernel unable to reload its own history."""
        recorded = instant(recorded_at, "recorded_at")
        if self.trusted_humans is not None and event.revoked_by.actor_id not in self.trusted_humans:
            raise InvalidEvent(
                f"revocation {event.revocation_id} is by {event.revoked_by.actor_id!r}, "
                "which this registry does not recognise as a human authorizer"
            )
        if event.effective_at is not None and instant(event.effective_at, "effective_at") < recorded:
            raise InvalidEvent(
                f"revocation {event.revocation_id} would take effect at {event.effective_at}, before it was recorded "
                f"at {recorded_at}; a revocation ends an authorization from a moment forward, never backward"
            )
        if event.revocation_id in self._revocations:
            raise InvalidEvent(f"duplicate revocation ID {event.revocation_id}")
        self._revocations[event.revocation_id] = (event, recorded_at)

    def revocations_of(self, authorization_id: str) -> tuple[RevocationEvent, ...]:
        """Every revocation recorded against this authorization, in force or scheduled."""
        return tuple(event for event, _ in self._revocations.values() if event.authorization_id == authorization_id)

    def _revoked_from(self, authorization_id: str) -> list:
        """The moments from which revocations of this authorization take effect."""
        return [instant(event.effective_at or recorded_at, "effective_at")
                for event, recorded_at in self._revocations.values() if event.authorization_id == authorization_id]

    def evidence(self, evidence_id: str) -> EvidenceRecord | None:
        return self._evidence.get(evidence_id)

    def authorization(self, authorization_id: str) -> AuthorizationEvent | None:
        """The authorization with this id, whatever its standing. To decide with it, use `at(as_of)`."""
        return self._authorizations.get(authorization_id)

    def in_force(self, event: AuthorizationEvent, as_of: str | None) -> bool:
        """Whether `event` may be relied on at `as_of`.

        An open-ended, unrevoked authorization holds whenever it is consulted, as every authorization did before
        windows and revocation. Otherwise it holds only inside its window and before any revocation of it takes
        effect, and only if `as_of` is a time this can read: an unknown time (None) or an unreadable one cannot
        show it is in force, so it does not count."""
        revoked_from = self._revoked_from(event.authorization_id)
        if not event.windowed and not revoked_from:
            return True
        if as_of is None:
            return False
        try:
            moment = instant(as_of, "as_of")
        except InvalidEvent:
            return False
        if any(start <= moment for start in revoked_from):
            return False
        return event.holds_at(moment)

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
            # Present only when there are any, so a registry with none keeps its old shape.
            **({"revocations": [{"revocation": event.to_dict(), "recorded_at": recorded_at}
                                for event, recorded_at in self._revocations.values()]}
               if self._revocations else {}),
        }

    @classmethod
    def restore(cls, snapshot: dict, *, trusted_humans=None, require_bounded: bool = False) -> "EvidenceRegistry":
        """A registry rebuilt from `snapshot()`. Authorizations go through
        add_authorization, so a trusted-humans binding and `require_bounded`
        are enforced on restore as they were live."""
        registry = cls(trusted_humans=trusted_humans, require_bounded=require_bounded)
        for item in snapshot.get("evidence", []):
            registry.add_evidence(EvidenceRecord.from_dict(item))
        for item in snapshot.get("authorizations", []):
            registry.add_authorization(AuthorizationEvent.from_dict(item))
        for item in snapshot.get("revocations", []):
            registry.add_revocation(RevocationEvent.from_dict(item["revocation"]), recorded_at=item["recorded_at"])
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
