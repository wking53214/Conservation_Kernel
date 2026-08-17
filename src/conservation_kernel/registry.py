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

    def __init__(self) -> None:
        self._evidence: dict[str, EvidenceRecord] = {}
        self._authorizations: dict[str, AuthorizationEvent] = {}

    def add_evidence(self, record: EvidenceRecord) -> None:
        if record.evidence_id in self._evidence:
            raise InvalidEvent(f"duplicate evidence ID {record.evidence_id}")
        self._evidence[record.evidence_id] = record

    def add_authorization(self, event: AuthorizationEvent) -> None:
        if event.authorization_id in self._authorizations:
            raise InvalidEvent(f"duplicate authorization ID {event.authorization_id}")
        self._authorizations[event.authorization_id] = event

    def evidence(self, evidence_id: str) -> EvidenceRecord | None:
        return self._evidence.get(evidence_id)

    def authorization(self, authorization_id: str) -> AuthorizationEvent | None:
        return self._authorizations.get(authorization_id)

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
            if item.subject_id not in subject_ids and item.subject_id != "*":
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
    ) -> bool:
        for ref in refs:
            event = self._authorizations.get(ref)
            if event is None:
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
