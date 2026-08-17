"""Errors raised for malformed or structurally impossible kernel records."""


class KernelError(Exception):
    """Base class for kernel errors."""


class InvalidArtifact(KernelError):
    """An artifact failed local schema validation."""


class InvalidEvent(KernelError):
    """An evidence, authorization, or transformation event is malformed."""


class LedgerError(KernelError):
    """An append-only ledger operation would violate its contract."""
