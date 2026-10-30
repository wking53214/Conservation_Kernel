"""External evidence and authorization registry used by the verifier."""

from __future__ import annotations

import secrets
from collections.abc import Callable

from .errors import InvalidEvent
from .events import AuthorizationEvent, DelegationEvent, EvidenceRecord, RevocationEvent, instant

#: The longest chain of delegations: one a trusted human issues, plus up to this many minus one re-delegations.
MAX_DELEGATION_DEPTH = 3


class EvidenceRegistry:
    """A deliberately separate witness store.

    A transformation record can name an authorization or evidence ID, but it
    cannot create a valid human event by placing a similarly shaped object in
    its own envelope. In a deployed system this registry is the protocol
    boundary; this in-memory implementation makes that boundary testable.
    """

    def __init__(self, *, trusted_humans: set[str] | frozenset[str] | None = None,
                 require_bounded: bool = False,
                 evidence_guard: Callable[[EvidenceRecord], bool] | None = None) -> None:
        """`evidence_guard`, if given, is asked before any evidence record is added, and the record is added only if it
        answers exactly True. It is the caller's own permission check (the kernel imports nothing to supply one); a
        guard that raises or answers anything else refuses, and a refused record leaves the registry as it was. It is
        asked after the registry has refused what it refuses itself (a duplicate id), so a one-use permission is not
        spent on a record that could never go in. Rebuilding a registry from a snapshot does not ask it. With none
        (the default) any caller may add evidence, as before."""
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
        self._evidence_guard = evidence_guard
        # Names this registry in the proof on a verification result, so a verdict reached against some other registry
        # cannot be passed off as this one's. Random per instance and never written to a snapshot.
        self._issuer = secrets.token_hex(16)
        self._evidence: dict[str, EvidenceRecord] = {}
        self._authorizations: dict[str, AuthorizationEvent] = {}
        self._delegations: dict[str, DelegationEvent] = {}
        # revocation id -> (the revocation, when the registry recorded it). Recorded time is the deployer's clock,
        # handed in by whoever records it (ConservationKernel.revoke passes its own), never the revoker's claim.
        self._revocations: dict[str, tuple[RevocationEvent, str]] = {}

    @property
    def has_evidence_guard(self) -> bool:
        """Whether adding evidence depends on a guard. Says nothing about what the guard will answer."""
        return self._evidence_guard is not None

    @property
    def issuer(self) -> str:
        """The name this registry puts on the verdicts reached against it (see `VerificationResult.proof`)."""
        return self._issuer

    def add_evidence(self, record: EvidenceRecord) -> None:
        if record.evidence_id in self._evidence:
            raise InvalidEvent(f"duplicate evidence ID {record.evidence_id}")
        if self._evidence_guard is not None:
            try:
                permitted = self._evidence_guard(record) is True
            except Exception:  # a guard that cannot answer never permits
                permitted = False
            if not permitted:
                raise InvalidEvent(f"evidence {record.evidence_id} refused: the evidence guard did not authorize this record")
        self._evidence[record.evidence_id] = record

    def add_authorization(self, event: AuthorizationEvent) -> None:
        if event.under_delegation is not None:
            # Its author's power comes from the delegation, not from being trusted directly. Whether the chain is in
            # force and covers this authorization is decided when it is used (`in_force`); who may cite it is decided here.
            delegation = self._delegations.get(event.under_delegation)
            if delegation is None:
                raise InvalidEvent(f"authorization {event.authorization_id} cites delegation {event.under_delegation}, "
                                   "which this registry does not hold")
            if delegation.delegate_id != event.authorized_by.actor_id:
                raise InvalidEvent(f"authorization {event.authorization_id} is by {event.authorized_by.actor_id!r}, but "
                                   f"delegation {delegation.delegation_id} is delegated to {delegation.delegate_id!r}")
        elif self.trusted_humans is not None and event.authorized_by.actor_id not in self.trusted_humans:
            raise InvalidEvent(
                f"authorization {event.authorization_id} is by {event.authorized_by.actor_id!r}, "
                "which this registry does not recognise as a human authorizer"
            )
        if self.require_bounded and event.valid_until is None:
            raise InvalidEvent(
                f"authorization {event.authorization_id} has no end (valid_until), and this registry accepts only "
                "authorizations that stop holding at a stated time"
            )
        if event.authorization_id in self._authorizations or event.authorization_id in self._delegations:
            raise InvalidEvent(f"duplicate authorization ID {event.authorization_id}")
        self._authorizations[event.authorization_id] = event

    def add_delegation(self, event: DelegationEvent) -> None:
        """Record a delegation of the power to authorize (see `DelegationEvent`).

        A delegation with no parent must be issued by a human this registry trusts, where it names them. One with a
        parent must cite a delegation already here that allows re-delegation, be issued by that delegation's
        delegate, stay inside its scope, and keep the chain within `MAX_DELEGATION_DEPTH`. Because a parent must
        already be here, a chain cannot loop. Ids are unique across authorizations and delegations, so a revocation
        names exactly one of them."""
        if self.require_bounded and event.valid_until is None:
            raise InvalidEvent(
                f"delegation {event.delegation_id} has no end (valid_until), and this registry accepts only "
                "delegations that stop holding at a stated time"
            )
        if event.delegation_id in self._delegations or event.delegation_id in self._authorizations:
            raise InvalidEvent(f"duplicate delegation ID {event.delegation_id}")
        if event.parent_delegation_id is None:
            if self.trusted_humans is not None and event.delegator.actor_id not in self.trusted_humans:
                raise InvalidEvent(
                    f"delegation {event.delegation_id} is by {event.delegator.actor_id!r}, "
                    "which this registry does not recognise as a human authorizer"
                )
        else:
            parent = self._delegations.get(event.parent_delegation_id)
            if parent is None:
                raise InvalidEvent(f"delegation {event.delegation_id} cites parent {event.parent_delegation_id}, "
                                   "which this registry does not hold")
            if not parent.may_redelegate:
                raise InvalidEvent(f"delegation {parent.delegation_id} does not allow re-delegating it")
            if event.delegator.actor_id != parent.delegate_id:
                raise InvalidEvent(f"delegation {event.delegation_id} is by {event.delegator.actor_id!r}, but "
                                   f"delegation {parent.delegation_id} is delegated to {parent.delegate_id!r}")
            wider = [name for name in ("subject_ids", "transition_kinds", "to_values")
                     if any(item not in getattr(parent, name) for item in getattr(event, name))]
            if wider:
                raise InvalidEvent(f"delegation {event.delegation_id} is wider than its parent in: {', '.join(wider)}")
            if len(self._chain(parent.delegation_id)) + 1 > MAX_DELEGATION_DEPTH:
                raise InvalidEvent(f"delegation {event.delegation_id} would make a chain deeper than "
                                   f"{MAX_DELEGATION_DEPTH}")
        self._delegations[event.delegation_id] = event

    def delegation(self, delegation_id: str) -> DelegationEvent | None:
        return self._delegations.get(delegation_id)

    def _chain(self, delegation_id: str) -> list[DelegationEvent]:
        """The delegation and its ancestors, nearest first."""
        chain: list[DelegationEvent] = []
        current = self._delegations.get(delegation_id)
        while current is not None and len(chain) <= MAX_DELEGATION_DEPTH:
            chain.append(current)
            current = self._delegations.get(current.parent_delegation_id) if current.parent_delegation_id else None
        return chain

    def add_revocation(self, event: RevocationEvent, *, recorded_at: str) -> None:
        """Record `event` as of `recorded_at` (ISO 8601 with offset), the recording clock's time.

        `recorded_at` is trusted as given, like everything else written to this registry: whoever can write it is
        the deployer. A recording time set earlier than the truth would let a revocation reach back over decisions
        already made. Record through `ConservationKernel.revoke`, which uses the kernel's own clock.

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
        show it is in force, so it does not count. One issued under a delegation also needs every link of that
        delegation's chain to cover it and, by the same rules, to be in force at `as_of`."""
        links: list = [(event, event.authorization_id)]
        if event.under_delegation is not None:
            chain = self._chain(event.under_delegation)
            if not chain or chain[0].delegation_id != event.under_delegation:
                return False
            # Every link must cover this very change; re-delegation only narrows, but each link is checked anyway.
            if not all(link.covers(event.subject_id, event.transition_kind, event.to_value) for link in chain):
                return False
            links += [(link, link.delegation_id) for link in chain]
        revoked = {link_id: self._revoked_from(link_id) for _, link_id in links}
        if not any(link.windowed or revoked[link_id] for link, link_id in links):
            return True
        if as_of is None:
            return False
        try:
            moment = instant(as_of, "as_of")
        except InvalidEvent:
            return False
        return all(link.holds_at(moment) and not any(start <= moment for start in revoked[link_id])
                   for link, link_id in links)

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
            **({"delegations": [item.to_dict() for item in self._delegations.values()]} if self._delegations else {}),
            # Present only when there are any, so a registry with none keeps its old shape.
            **({"revocations": [{"revocation": event.to_dict(), "recorded_at": recorded_at}
                                for event, recorded_at in self._revocations.values()]}
               if self._revocations else {}),
        }

    @classmethod
    def restore(cls, snapshot: dict, *, trusted_humans=None, require_bounded: bool = False,
                evidence_guard: Callable[[EvidenceRecord], bool] | None = None) -> "EvidenceRegistry":
        """A registry rebuilt from `snapshot()`. Authorizations go through
        add_authorization, so a trusted-humans binding and `require_bounded`
        are enforced on restore as they were live. The evidence in the snapshot is not put to `evidence_guard`
        (it was guarded, or not, when first added); the guard governs evidence added after."""
        registry = cls(trusted_humans=trusted_humans, require_bounded=require_bounded)
        for item in snapshot.get("evidence", []):
            registry.add_evidence(EvidenceRecord.from_dict(item))
        for item in snapshot.get("delegations", []):             # before the authorizations that cite them
            registry.add_delegation(DelegationEvent.from_dict(item))
        for item in snapshot.get("authorizations", []):
            registry.add_authorization(AuthorizationEvent.from_dict(item))
        for item in snapshot.get("revocations", []):
            registry.add_revocation(RevocationEvent.from_dict(item["revocation"]), recorded_at=item["recorded_at"])
        registry._evidence_guard = evidence_guard
        return registry


class RegistryAt:
    """An `EvidenceRegistry` seen as of one moment (see `EvidenceRegistry.at`).

    Evidence lookups pass straight through. Authorization lookups return only what is in force at
    `as_of`, so a caller holding this view cannot reach an expired or revoked authorization by mistake."""

    def __init__(self, registry: EvidenceRegistry, as_of: str | None) -> None:
        self.registry = registry
        self.as_of = as_of

    # Read-only settings and records, so a verifier written against the registry can still read them.
    @property
    def trusted_humans(self):
        return self.registry.trusted_humans

    @property
    def require_bounded(self) -> bool:
        return self.registry.require_bounded

    @property
    def issuer(self) -> str:
        return self.registry.issuer

    def snapshot(self) -> dict:
        return self.registry.snapshot()

    def revocations_of(self, authorization_id: str):
        return self.registry.revocations_of(authorization_id)

    def delegation(self, delegation_id: str):
        return self.registry.delegation(delegation_id)

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
