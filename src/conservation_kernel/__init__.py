"""Conservation Kernel v0.1.

This package verifies structural conservation claims across artifact
transformations.  It does not determine whether a proposition is true in the
external world.
"""

from .enums import (
    ActorKind,
    AuthorityStatus,
    CanonicalState,
    Dimension,
    EpistemicStatus,
    EvidenceKind,
    OriginStatus,
    TemporalScope,
    TransitionKind,
    UncertaintyState,
    VerificationStatus,
)
from .events import (
    AuthorizationEvent,
    DeclaredChange,
    EvidenceRecord,
    TransformationRecord,
)
from .ledger import ConservationLedger
from .kernel import ConservationKernel
from .model import Artifact, Actor, FunctionalContract, Proposition, TemporalMetadata, Uncertainty
from .registry import EvidenceRegistry
from .result import ObservedChange, VerificationResult, Violation
from .verifier import IndependentVerifier

__all__ = [
    "Actor",
    "ActorKind",
    "Artifact",
    "AuthorizationEvent",
    "AuthorityStatus",
    "CanonicalState",
    "ConservationLedger",
    "ConservationKernel",
    "DeclaredChange",
    "Dimension",
    "EpistemicStatus",
    "EvidenceKind",
    "EvidenceRecord",
    "EvidenceRegistry",
    "FunctionalContract",
    "IndependentVerifier",
    "ObservedChange",
    "OriginStatus",
    "Proposition",
    "TemporalMetadata",
    "TemporalScope",
    "TransformationRecord",
    "TransitionKind",
    "Uncertainty",
    "UncertaintyState",
    "VerificationResult",
    "VerificationStatus",
    "Violation",
]
