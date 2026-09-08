"""Errors raised for malformed or structurally impossible kernel records."""


class KernelError(Exception):
    """Base class for kernel errors."""


class InvalidArtifact(KernelError):
    """An artifact failed local schema validation."""


class InvalidEvent(KernelError):
    """An evidence, authorization, or transformation event is malformed."""


class LedgerError(KernelError):
    """An append-only ledger operation would violate its contract."""


class RootAdmissionError(LedgerError):
    """A root artifact asserted something the registry does not back.

    Roots are asserted, not verified: the constitution constrains
    transitions. Measured 2026-09-08, that let a root claim FACT,
    HUMAN_ORIGINATED, EXECUTED and CANONICAL with a dangling authorization
    reference and become legitimate ancestry for everything downstream.
    Admission now requires that every reference a root cites exists, that
    an authoritative or canonical claim is backed by an authorization for
    that proposition, and that a fact or observation names a source.
    """


class SnapshotIntegrityError(LedgerError):
    """A restored snapshot does not re-verify.

    A restart used to lose everything (the ledger was in memory only), and
    a hand-written ledger would have been indistinguishable from a verified
    one. On restore every root is re-admitted and every transformation is
    re-verified against the restored registry; a snapshot that fails either
    is refused whole.
    """
