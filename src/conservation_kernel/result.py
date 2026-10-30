"""Machine-readable verification results."""

from __future__ import annotations

import hmac
import secrets
from dataclasses import dataclass, field, replace
from hashlib import sha256
from typing import Any

from .enums import Dimension, VerificationStatus
from .model import _digest, canonical_json

# Held by this process only and never written out. It is what makes a result the verifier produced different from one
# a caller typed: only code in this package asks for a proof, so a hand-built result, or a real one edited afterwards,
# has none that checks. It guards against misuse of the public API, not against code that reads private module state.
_PROOF_KEY = secrets.token_bytes(32)


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
    #: When the deciding kernel judged this, by its own clock (ISO 8601 with offset). None when the verifier
    #: was called without a time. Authorizations that expire or can be revoked are judged as of this moment,
    #: and a restore re-verifies as of it, so history is not re-judged against a later day.
    verified_at: str | None = None
    #: (issuer, mac): set by `IndependentVerifier.verify` and by nothing else, so the ledger can tell a result the
    #: verifier produced from one written by hand. It covers every field above, the record and the output verified,
    #: and the registry (`issuer`) the verdict was reached against. Never serialized and never compared.
    proof: tuple[str, str] | None = field(default=None, repr=False, compare=False)

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
            # Present only when stamped, so a result's shape (and every digest over it) is unchanged without one.
            **({"verified_at": self.verified_at} if self.verified_at is not None else {}),
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
            verified_at=data.get("verified_at"),
        )


def _mac(result: "VerificationResult", record: Any, output: Any, issuer: str) -> str:
    body = canonical_json({"result": result.to_dict(), "record": _digest(record.to_dict()),
                           "output": output.artifact_digest, "issuer": issuer})
    return hmac.new(_PROOF_KEY, body.encode("utf-8"), sha256).hexdigest()


def _issue_proof(result: VerificationResult, record: Any, output: Any, issuer: str | None) -> VerificationResult:
    """`result` with a proof that the verifier produced it, for this record and output, against registry `issuer`."""
    if issuer is None:
        return result
    return replace(result, proof=(issuer, _mac(result, record, output, issuer)))


def _proof_issuer(result: VerificationResult, record: Any, output: Any) -> str | None:
    """The registry this result was verified against, if its proof checks for exactly this record and output; None
    if it carries no proof or the proof does not match (the result, record or output was written or changed by hand)."""
    if result.proof is None:
        return None
    issuer, mac = result.proof
    return issuer if hmac.compare_digest(mac, _mac(result, record, output, issuer)) else None
